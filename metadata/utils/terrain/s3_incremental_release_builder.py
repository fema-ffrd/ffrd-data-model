#!/usr/bin/env python3
"""Build an incremental S3 STAC release by reusing unchanged items and regenerating changed/new items."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from stac_item_shared import build_stac_item


def maybe_get_s3_client(profile: str | None):
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required for S3 mode. Install with: pip install boto3") from exc

    if profile:
        session = boto3.Session(profile_name=profile)
        return session.client("s3")
    return boto3.client("s3")


def iso_z_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def s3_https_uri(bucket: str, key: str) -> str:
    normalized_key = key.lstrip("/")
    return f"https://{bucket}.s3.amazonaws.com/{quote(normalized_key, safe='/')}"


def default_catalog_href(bucket: str, collection_key: str) -> str:
    catalog_key = (Path(collection_key).parent.parent / "catalog.json").as_posix()
    return s3_https_uri(bucket, catalog_key)


def parse_semver_major_minor(version: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)", version.strip())
    if not match:
        raise ValueError(f"Version must match X.Y, got: {version}")
    major = int(match.group(1))
    minor = int(match.group(2))
    return major, minor


def normalize_to_major_minor(version: str) -> str:
    """Normalize version to X.Y, accepting legacy X.Y.Z by dropping patch."""
    raw = version.strip()
    match_xy = re.fullmatch(r"(\d+)\.(\d+)", raw)
    if match_xy:
        return raw

    match_xyz = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", raw)
    if match_xyz:
        return f"{match_xyz.group(1)}.{match_xyz.group(2)}"

    raise ValueError(f"Version must match X.Y, got: {version}")


def bump_minor(version: str) -> str:
    major, minor = parse_semver_major_minor(version)
    return f"{major}.{minor + 1}"


def normalize_etag(value: str | None) -> str | None:
    if value is None:
        return None
    return str(value).strip().strip('"')


def parse_s3_href_to_bucket_key(href: str) -> tuple[str, str]:
    parsed = urlparse(href)
    if parsed.scheme == "s3":
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if not bucket or not key:
            raise ValueError(f"Invalid s3 href: {href}")
        return bucket, unquote(key)

    if parsed.scheme in {"http", "https"}:
        host = parsed.netloc
        path = parsed.path.lstrip("/")

        # Virtual-hosted style: <bucket>.s3.amazonaws.com/<key>
        vh_match = re.fullmatch(r"([^.]+)\.s3\.amazonaws\.com", host)
        if vh_match:
            bucket = vh_match.group(1)
            if not path:
                raise ValueError(f"Missing key in href: {href}")
            return bucket, unquote(path)

        # Path-style: s3.amazonaws.com/<bucket>/<key>
        if host == "s3.amazonaws.com":
            parts = path.split("/", 1)
            if len(parts) != 2:
                raise ValueError(f"Expected s3 path-style href with bucket/key: {href}")
            return parts[0], unquote(parts[1])

    raise ValueError(f"Unsupported S3 href format: {href}")


def resolve_bucket_and_key(default_bucket: str, raw_key_or_href: str) -> tuple[str, str]:
    """Allow either plain key or fully-qualified s3/http href for S3 locations."""
    value = raw_key_or_href.strip()
    if value.startswith("s3://") or value.startswith("http://") or value.startswith("https://"):
        return parse_s3_href_to_bucket_key(value)
    return default_bucket, value.strip("/")


def upsert_link(links: list[dict], rel: str, href: str, media_type: str) -> None:
    for link in links:
        if link.get("rel") == rel:
            link["href"] = href
            link["type"] = media_type
            return
    links.append({"rel": rel, "href": href, "type": media_type})


def remove_link(links: list[dict], rel: str) -> None:
    links[:] = [link for link in links if link.get("rel") != rel]


def get_link_href(links: list[dict] | None, rel: str) -> str | None:
    if not links:
        return None
    for link in links:
        if isinstance(link, dict) and link.get("rel") == rel and link.get("href"):
            return str(link["href"])
    return None


def collection_link_title(rel: str, href: str) -> str:
    if rel == "self":
        return "Collection JSON"
    if rel == "root":
        return "Root Catalog"
    if rel == "parent":
        return "Parent Catalog"
    if rel == "item":
        return Path(href).name
    return rel.replace("-", " ").title()


def load_json_from_s3(s3, bucket: str, key: str) -> dict:
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
    except Exception as exc:
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            code = str(response.get("Error", {}).get("Code", ""))
            if code == "NoSuchBucket":
                raise ValueError(
                    f"Bucket not found: {bucket}. While reading key: {key}. "
                    "If your metadata lives in a prefix of another bucket, pass that real bucket to --stac-bucket "
                    "and include the prefix in --current-collection-key."
                ) from exc
            if code in {"NoSuchKey", "404", "NotFound"}:
                raise ValueError(f"Key not found: s3://{bucket}/{key}") from exc
        raise
    payload = response["Body"].read().decode("utf-8")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object for s3://{bucket}/{key}")
    return data


def put_json_to_s3(s3, bucket: str, key: str, payload: dict) -> None:
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, indent=2).encode("utf-8"),
        ContentType="application/json",
    )


def s3_key_exists(s3, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except Exception as exc:
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            code = str(response.get("Error", {}).get("Code", ""))
            status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
                return False
        raise


def list_tif_objects(s3, bucket: str, prefix: str, recursive: bool) -> dict[str, dict]:
    normalized_prefix = prefix.strip("/")
    if normalized_prefix:
        normalized_prefix += "/"

    paginator = s3.get_paginator("list_objects_v2")
    objects: dict[str, dict] = {}
    for page in paginator.paginate(Bucket=bucket, Prefix=normalized_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            rel = key[len(normalized_prefix):] if normalized_prefix and key.startswith(normalized_prefix) else key
            if not recursive and "/" in rel:
                continue
            if not rel.lower().endswith((".tif", ".tiff")):
                continue
            objects[key] = {
                "key": key,
                "etag": normalize_etag(obj.get("ETag")),
                "size": int(obj.get("Size", 0)),
                "last_modified": iso_z(obj["LastModified"]),
            }
    return dict(sorted(objects.items()))


def collect_item_extensions(items: list[dict]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for item in items:
        for ext in item.get("stac_extensions", []):
            if ext not in seen:
                seen.add(ext)
                ordered.append(ext)
    return ordered


def collect_crs_summaries(items: list[dict]) -> dict:
    codes: list[str] = []
    code_seen: set[str] = set()
    wkts: list[str] = []
    wkt_seen: set[str] = set()

    for item in items:
        props = item.get("properties", {})
        code = props.get("proj:code")
        wkt = props.get("proj:wkt2")
        if code and code not in code_seen:
            code_seen.add(code)
            codes.append(code)
        if wkt and wkt not in wkt_seen:
            wkt_seen.add(wkt)
            wkts.append(wkt)

    if codes:
        return {"proj:code": codes}
    if wkts:
        return {"proj:wkt2": wkts}
    return {}


def merge_bboxes(items: list[dict]) -> list[float]:
    bboxes = [item.get("bbox") for item in items if item.get("bbox")]
    if not bboxes:
        raise ValueError("No item bbox values available to build collection extent")
    minx = min(b[0] for b in bboxes)
    miny = min(b[1] for b in bboxes)
    maxx = max(b[2] for b in bboxes)
    maxy = max(b[3] for b in bboxes)
    return [minx, miny, maxx, maxy]


def collect_datetimes(items: list[dict]) -> tuple[str | None, str | None]:
    values = []
    for item in items:
        dt = item.get("properties", {}).get("datetime")
        if dt:
            values.append(dt)
    if not values:
        return None, None
    return min(values), max(values)


def try_load_manifest(s3, bucket: str, key: str | None) -> dict | None:
    if not key:
        return None
    try:
        return load_json_from_s3(s3, bucket, key)
    except Exception:
        return None


def derive_new_collection_key(current_collection_key: str, old_version: str, new_version: str) -> str:
    if old_version in current_collection_key:
        return current_collection_key.replace(old_version, new_version)
    raise ValueError(
        "Unable to derive new collection key from current key. "
        "Pass --new-collection-key explicitly."
    )


def derive_new_collection_id(current_collection_id: str, old_version: str, new_version: str) -> str:
    if old_version in current_collection_id:
        return current_collection_id.replace(old_version, new_version)
    return f"{current_collection_id}-v{new_version}"


def compare_source_against_previous(
    current_obj: dict,
    previous_item_etag: str | None,
    previous_manifest_entry: dict | None,
) -> tuple[str, str]:
    # Change detection policy:
    # 1) Historical manifest size+last_modified snapshot
    # 2) Historical manifest etag (when size+time are equal)
    # 3) Previous item etag fallback
    current_etag = normalize_etag(current_obj.get("etag"))
    prev_etag = normalize_etag(previous_item_etag)

    if previous_manifest_entry:
        prev_size = previous_manifest_entry.get("size")
        prev_last_modified = previous_manifest_entry.get("last_modified")
        if prev_size is not None and prev_last_modified:
            same_size = int(current_obj.get("size", -1)) == int(prev_size)
            same_last_modified = str(current_obj.get("last_modified")) == str(prev_last_modified)
            if not (same_size and same_last_modified):
                return "changed", "size_last_modified"

            manifest_etag = normalize_etag(previous_manifest_entry.get("etag"))
            if current_etag and manifest_etag:
                if current_etag == manifest_etag:
                    return "unchanged", "size_last_modified+etag"
                return "changed", "size_last_modified+etag"

            return "unchanged", "size_last_modified"

    if current_etag and prev_etag:
        if current_etag == prev_etag:
            return "unchanged", "etag"
        return "changed", "etag"

    return "changed", "missing_comparison_data"


def build_item_from_source_tif(
    s3,
    source_bucket: str,
    source_key: str,
    stac_bucket: str,
    output_key: str,
    *,
    collection_id: str,
    collection_href: str,
    catalog_href: str,
    item_version: str,
    predecessor_href: str | None,
    write_output: bool,
) -> dict:
    source_head = s3.head_object(Bucket=source_bucket, Key=source_key)
    source_etag = normalize_etag(source_head.get("ETag"))
    source_updated = iso_z(source_head["LastModified"])

    with tempfile.TemporaryDirectory(prefix="stac_incremental_item_") as td:
        temp_dir = Path(td)
        local_tif = temp_dir / Path(source_key).name
        s3.download_file(source_bucket, source_key, str(local_tif))

        item = build_stac_item(
            local_tif,
            item_version=item_version,
            deprecated=False,
            source_etag=source_etag,
            source_created=source_updated,
            source_updated=source_updated,
        )

    item["collection"] = collection_id
    item_href = s3_https_uri(stac_bucket, output_key)
    item["assets"]["data"]["href"] = s3_https_uri(source_bucket, source_key)

    links = item.setdefault("links", [])
    upsert_link(links, "self", item_href, "application/geo+json")
    upsert_link(links, "collection", collection_href, "application/json")
    upsert_link(links, "parent", collection_href, "application/json")
    upsert_link(links, "root", catalog_href, "application/json")

    if predecessor_href:
        upsert_link(links, "predecessor-version", predecessor_href, "application/geo+json")
    else:
        remove_link(links, "predecessor-version")
    remove_link(links, "successor-version")
    upsert_link(links, "latest-version", item_href, "application/geo+json")

    if write_output:
        put_json_to_s3(s3, stac_bucket, output_key, item)
    return item


def copy_unchanged_item_for_new_release(
    s3,
    stac_bucket: str,
    old_item_key: str,
    new_item_key: str,
    *,
    collection_id: str,
    collection_href: str,
    catalog_href: str,
) -> dict:
    item = load_json_from_s3(s3, stac_bucket, old_item_key)
    item = deepcopy(item)

    item["collection"] = collection_id
    item_props = item.setdefault("properties", {})
    item_props["deprecated"] = False

    new_item_href = s3_https_uri(stac_bucket, new_item_key)
    links = item.setdefault("links", [])
    upsert_link(links, "self", new_item_href, "application/geo+json")
    upsert_link(links, "collection", collection_href, "application/json")
    upsert_link(links, "parent", collection_href, "application/json")
    upsert_link(links, "root", catalog_href, "application/json")
    remove_link(links, "successor-version")
    upsert_link(links, "latest-version", new_item_href, "application/geo+json")

    put_json_to_s3(s3, stac_bucket, new_item_key, item)
    return item


def build_collection_document(
    template_collection: dict,
    items: list[dict],
    item_hrefs: list[str],
    *,
    new_collection_id: str,
    new_collection_href: str,
    predecessor_collection_href: str | None,
    catalog_href: str,
    new_version: str,
    title_override: str | None,
    description_override: str | None,
) -> dict:
    collection = deepcopy(template_collection)

    collection["id"] = new_collection_id
    collection["version"] = new_version
    collection["deprecated"] = False
    collection["updated"] = iso_z_now()
    if title_override:
        collection["title"] = title_override
    if description_override:
        collection["description"] = description_override

    merged_bbox = merge_bboxes(items)
    dt_start, dt_end = collect_datetimes(items)

    collection.setdefault("extent", {})
    collection["extent"]["spatial"] = {"bbox": [merged_bbox]}
    collection["extent"]["temporal"] = {"interval": [[dt_start, dt_end]]}

    summaries = collection.get("summaries", {}) if isinstance(collection.get("summaries"), dict) else {}
    summaries.pop("proj:epsg", None)
    summaries.update(collect_crs_summaries(items))
    if summaries:
        collection["summaries"] = summaries

    collection["stac_extensions"] = collect_item_extensions(items)

    links = [
        {
            "rel": "self",
            "href": new_collection_href,
            "type": "application/json",
            "title": collection_link_title("self", new_collection_href),
        },
        {
            "rel": "root",
            "href": catalog_href,
            "type": "application/json",
            "title": collection_link_title("root", catalog_href),
        },
        {
            "rel": "parent",
            "href": catalog_href,
            "type": "application/json",
            "title": collection_link_title("parent", catalog_href),
        },
    ]
    if predecessor_collection_href:
        links.append(
            {
                "rel": "predecessor-version",
                "href": predecessor_collection_href,
                "type": "application/json",
                "title": collection_link_title("predecessor-version", predecessor_collection_href),
            }
        )
    links.append(
        {
            "rel": "latest-version",
            "href": new_collection_href,
            "type": "application/json",
            "title": collection_link_title("latest-version", new_collection_href),
        }
    )
    for href in item_hrefs:
        links.append(
            {
                "rel": "item",
                "href": href,
                "type": "application/geo+json",
                "title": collection_link_title("item", href),
            }
        )

    collection["links"] = links
    return collection


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an incremental STAC release from S3 TIFF changes")
    parser.add_argument("--source-bucket", required=True, help="Bucket containing source TIFFs")
    parser.add_argument("--source-prefix", required=True, help="Prefix containing source TIFFs")
    parser.add_argument("--stac-bucket", required=True, help="Bucket containing STAC metadata")
    parser.add_argument("--current-collection-key", required=True, help="S3 key to current release collection.json")
    parser.add_argument("--new-collection-key", help="S3 key to new release collection.json")
    parser.add_argument("--current-manifest-key", help="S3 key to current release manifest JSON (optional)")
    parser.add_argument("--new-manifest-key", help="S3 key for newly generated manifest JSON")
    parser.add_argument("--change-report-key", help="S3 key for machine-readable change report JSON")
    parser.add_argument("--new-version", help="Explicit new release version (X.Y). If omitted, Minor version is incremented.")
    parser.add_argument("--new-collection-id", help="Explicit new collection id. If omitted, derived from current id/version.")
    parser.add_argument("--root-href", help="Override root/parent catalog href for the new collection")
    parser.add_argument("--recursive", action="store_true", help="Scan source-prefix recursively")
    parser.add_argument("--title", help="Optional title override for new collection")
    parser.add_argument("--description", help="Optional description override for new collection")
    parser.add_argument("--force-new-release", action="store_true", help="Create a new release even if no changes are detected")
    parser.add_argument("--dry-run", action="store_true", help="Compute diff and planned outputs without writing")
    parser.add_argument("--s3-profile", help="Optional AWS profile")
    args = parser.parse_args()

    s3 = maybe_get_s3_client(args.s3_profile)

    stac_bucket, current_collection_key = resolve_bucket_and_key(args.stac_bucket, args.current_collection_key)
    current_collection = load_json_from_s3(s3, stac_bucket, current_collection_key)
    if current_collection.get("type") != "Collection":
        raise ValueError("Current collection JSON is not a STAC Collection")

    current_version = normalize_to_major_minor(str(current_collection.get("version", "1.0")))
    new_version = args.new_version or bump_minor(current_version)
    new_version = normalize_to_major_minor(new_version)
    parse_semver_major_minor(new_version)

    new_collection_key = (
        args.new_collection_key.strip("/")
        if args.new_collection_key
        else derive_new_collection_key(current_collection_key, current_version, new_version)
    )
    new_collection_href = s3_https_uri(stac_bucket, new_collection_key)
    current_collection_href = s3_https_uri(stac_bucket, current_collection_key)
    current_collection_predecessor_href = get_link_href(current_collection.get("links", []), "predecessor-version")
    catalog_href = args.root_href or default_catalog_href(stac_bucket, new_collection_key)

    current_collection_id = str(current_collection.get("id", "collection"))
    new_collection_id = args.new_collection_id or derive_new_collection_id(current_collection_id, current_version, new_version)

    new_collection_folder = Path(new_collection_key).parent.as_posix()

    if args.new_manifest_key:
        manifest_bucket, new_manifest_key = resolve_bucket_and_key(stac_bucket, args.new_manifest_key)
        if manifest_bucket != stac_bucket:
            raise ValueError("--new-manifest-key must target the same bucket as --stac-bucket")
    else:
        new_manifest_key = f"{new_collection_folder}/manifest.json" if new_collection_folder else "manifest.json"

    if args.change_report_key:
        report_bucket, change_report_key = resolve_bucket_and_key(stac_bucket, args.change_report_key)
        if report_bucket != stac_bucket:
            raise ValueError("--change-report-key must target the same bucket as --stac-bucket")
    else:
        change_report_key = f"{new_collection_folder}/change-report.json" if new_collection_folder else "change-report.json"

    previous_manifest_key: str | None = None
    previous_manifest_bucket = stac_bucket
    if args.current_manifest_key:
        previous_manifest_bucket, previous_manifest_key = resolve_bucket_and_key(stac_bucket, args.current_manifest_key)

    previous_manifest = try_load_manifest(s3, previous_manifest_bucket, previous_manifest_key)
    previous_manifest_entries: dict[str, dict] = {}
    if isinstance(previous_manifest, dict):
        for entry in previous_manifest.get("items", []):
            tif_key = entry.get("tif_key")
            if tif_key:
                previous_manifest_entries[str(tif_key)] = entry

    previous_item_links = [
        link for link in current_collection.get("links", [])
        if isinstance(link, dict) and link.get("rel") == "item" and link.get("href")
    ]

    previous_by_tif_key: dict[str, dict] = {}
    for link in previous_item_links:
        item_href = str(link["href"])
        item_bucket, item_key = parse_s3_href_to_bucket_key(item_href)
        item_doc = load_json_from_s3(s3, item_bucket, item_key)

        data_href = item_doc.get("assets", {}).get("data", {}).get("href")
        if not data_href:
            continue
        data_bucket, data_key = parse_s3_href_to_bucket_key(str(data_href))
        if data_bucket != args.source_bucket:
            continue

        previous_by_tif_key[data_key] = {
            "item_bucket": item_bucket,
            "item_key": item_key,
            "item_href": item_href,
            "item_version": item_doc.get("properties", {}).get("version"),
            "etag": normalize_etag(item_doc.get("etag")),
        }

    current_source_objects = list_tif_objects(s3, args.source_bucket, args.source_prefix, args.recursive)
    current_keys = set(current_source_objects.keys())
    previous_keys = set(previous_by_tif_key.keys())

    removed_keys = sorted(previous_keys - current_keys)

    unchanged_rows: list[dict] = []
    changed_rows: list[dict] = []
    new_rows: list[dict] = []

    for tif_key, obj in current_source_objects.items():
        previous = previous_by_tif_key.get(tif_key)
        if previous is None:
            new_rows.append({
                "tif_key": tif_key,
                "status": "new",
                "detection_method": "missing_previous_item",
                "current": obj,
            })
            continue

        prev_manifest_entry = previous_manifest_entries.get(tif_key)
        status, method = compare_source_against_previous(
            obj,
            previous.get("etag"),
            prev_manifest_entry,
        )
        row = {
            "tif_key": tif_key,
            "status": status,
            "detection_method": method,
            "current": obj,
            "previous": {
                "item_href": previous.get("item_href"),
                "item_key": previous.get("item_key"),
                "item_version": previous.get("item_version"),
                "etag": previous.get("etag"),
            },
        }
        if status == "unchanged":
            unchanged_rows.append(row)
        else:
            changed_rows.append(row)

    has_content_changes = bool(changed_rows or new_rows or removed_keys)
    forced_release = bool(args.new_version and not has_content_changes)
    should_release = bool(has_content_changes or args.force_new_release or forced_release)

    if not args.dry_run and should_release and s3_key_exists(s3, stac_bucket, new_collection_key):
        raise FileExistsError(
            f"Refusing to overwrite existing key: s3://{stac_bucket}/{new_collection_key}. "
            "Use a different --new-collection-key."
        )

    # Create no-op report for auditability when nothing changes and release is not forced.
    if not should_release:
        report = {
            "report_version": "1.0",
            "generated_at": iso_z_now(),
            "mode": "no-op",
            "reason": "No changed/new/removed TIFF objects detected.",
            "source": {
                "bucket": args.source_bucket,
                "prefix": args.source_prefix,
            },
            "stac": {
                "bucket": stac_bucket,
                "current_collection_key": current_collection_key,
            },
            "summary": {
                "total_current_tifs": len(current_source_objects),
                "unchanged": len(unchanged_rows),
                "changed": len(changed_rows),
                "new": len(new_rows),
                "removed": len(removed_keys),
            },
            "forced_release": False,
            "classification": {
                "unchanged": unchanged_rows,
                "changed": changed_rows,
                "new": new_rows,
                "removed": [{"tif_key": key} for key in removed_keys],
            },
        }
        print(json.dumps(report["summary"], indent=2))
        if not args.dry_run:
            put_json_to_s3(s3, stac_bucket, change_report_key, report)
            print(f"Wrote no-op change report: {s3_https_uri(stac_bucket, change_report_key)}")
        else:
            print("Dry run: no files written")
        return

    item_docs_for_collection: list[dict] = []
    item_hrefs_for_collection: list[str] = []
    planned_deprecations: list[dict] = []
    manifest_items: list[dict] = []

    # Copy unchanged items into the new release folder and repoint links to new release context.
    for row in unchanged_rows:
        tif_key = row["tif_key"]
        old_item_key = str(row["previous"]["item_key"])
        new_item_key = f"{new_collection_folder}/{Path(old_item_key).name}" if new_collection_folder else Path(old_item_key).name
        new_item_href = s3_https_uri(stac_bucket, new_item_key)

        if args.dry_run:
            item_doc = load_json_from_s3(s3, stac_bucket, old_item_key)
            item_doc = deepcopy(item_doc)
            item_doc["collection"] = new_collection_id
            props = item_doc.setdefault("properties", {})
            props["deprecated"] = False
            links = item_doc.setdefault("links", [])
            upsert_link(links, "self", new_item_href, "application/geo+json")
            upsert_link(links, "collection", new_collection_href, "application/json")
            upsert_link(links, "parent", new_collection_href, "application/json")
            upsert_link(links, "root", catalog_href, "application/json")
            remove_link(links, "successor-version")
            upsert_link(links, "latest-version", new_item_href, "application/geo+json")
        else:
            item_doc = copy_unchanged_item_for_new_release(
                s3,
                stac_bucket,
                
                old_item_key,
                new_item_key,
                collection_id=new_collection_id,
                collection_href=new_collection_href,
                catalog_href=catalog_href,
            )

        item_docs_for_collection.append(item_doc)
        item_hrefs_for_collection.append(new_item_href)
        manifest_items.append(
            {
                "logical_id": item_doc.get("id"),
                "tif_key": tif_key,
                "etag": row["current"].get("etag"),
                "size": row["current"].get("size"),
                "last_modified": row["current"].get("last_modified"),
                "status": "unchanged",
                "item_version": item_doc.get("properties", {}).get("version"),
                "item_key": new_item_key,
                "item_href": new_item_href,
                "detection_method": row["detection_method"],
            }
        )

    # Regenerate changed and new items for the new release.
    for row in changed_rows + new_rows:
        tif_key = row["tif_key"]
        item_name = f"{Path(tif_key).stem}.json"
        new_item_key = f"{new_collection_folder}/{item_name}" if new_collection_folder else item_name
        predecessor_href = row.get("previous", {}).get("item_href")

        item_doc = build_item_from_source_tif(
            s3,
            args.source_bucket,
            tif_key,
            stac_bucket,
            new_item_key,
            collection_id=new_collection_id,
            collection_href=new_collection_href,
            catalog_href=catalog_href,
            item_version=new_version,
            predecessor_href=predecessor_href,
            write_output=not args.dry_run,
        )

        new_item_href = s3_https_uri(stac_bucket, new_item_key)
        status = row["status"]

        item_docs_for_collection.append(item_doc)
        item_hrefs_for_collection.append(new_item_href)
        manifest_items.append(
            {
                "logical_id": item_doc.get("id"),
                "tif_key": tif_key,
                "etag": row["current"].get("etag"),
                "size": row["current"].get("size"),
                "last_modified": row["current"].get("last_modified"),
                "status": status,
                "item_version": new_version,
                "item_key": new_item_key,
                "item_href": new_item_href,
                "detection_method": row["detection_method"],
            }
        )

        if status == "changed" and predecessor_href:
            prev_bucket, prev_key = parse_s3_href_to_bucket_key(predecessor_href)
            planned_deprecations.append(
                {
                    "reason": "superseded",
                    "tif_key": tif_key,
                    "old_item_bucket": prev_bucket,
                    "old_item_key": prev_key,
                    "old_item_href": predecessor_href,
                    "new_item_bucket": stac_bucket,
                    "new_item_key": new_item_key,
                    "new_item_href": new_item_href,
                }
            )

    for tif_key in removed_keys:
        previous = previous_by_tif_key[tif_key]
        planned_deprecations.append(
            {
                "reason": "removed",
                "tif_key": tif_key,
                "old_item_bucket": previous["item_bucket"],
                "old_item_key": previous["item_key"],
                "old_item_href": previous["item_href"],
                "new_item_bucket": None,
                "new_item_key": None,
                "new_item_href": None,
            }
        )

    collection_doc = build_collection_document(
        current_collection,
        item_docs_for_collection,
        sorted(item_hrefs_for_collection),
        new_collection_id=new_collection_id,
        new_collection_href=new_collection_href,
        predecessor_collection_href=current_collection_href,
        catalog_href=catalog_href,
        new_version=new_version,
        title_override=args.title,
        description_override=args.description,
    )

    manifest = {
        "manifest_version": "1.0",
        "generated_at": iso_z_now(),
        "dataset_id": new_collection_id,
        "release_version": new_version,
        "source": {
            "bucket": args.source_bucket,
            "prefix": args.source_prefix,
        },
        "stac": {
            "bucket": stac_bucket,
            
            "collection_key": new_collection_key,
            "collection_href": new_collection_href,
            "catalog_href": catalog_href,
            "collection_id": new_collection_id,
        },
        "policy": {
            "change_detection_primary": "size_last_modified",
            "change_detection_fallback": "etag",
            "copy_unchanged_items": True,
            "deprecation_strategy": "two_run",
        },
        "summary": {
            "total_current_tifs": len(current_source_objects),
            "unchanged": len(unchanged_rows),
            "changed": len(changed_rows),
            "new": len(new_rows),
            "removed": len(removed_keys),
        },
        "items": sorted(manifest_items, key=lambda row: str(row.get("tif_key", ""))),
    }

    report = {
        "report_version": "1.0",
        "generated_at": iso_z_now(),
        "mode": "release",
        "source_collection": {
            "bucket": stac_bucket,
            "key": current_collection_key,
            "href": current_collection_href,
            "predecessor_href": current_collection_predecessor_href,
            "id": current_collection_id,
            "version": current_version,
        },
        "target_collection": {
            "bucket": stac_bucket,
            "key": new_collection_key,
            "href": new_collection_href,
            "id": new_collection_id,
            "version": new_version,
        },
        "new_version": new_version,
        "forced_release": forced_release,
        "source": {
            "bucket": args.source_bucket,
            "prefix": args.source_prefix,
        },
        "previous_collection": {
            "bucket": stac_bucket,
            "key": current_collection_key,
            "href": current_collection_href,
            "predecessor_href": current_collection_predecessor_href,
            "id": current_collection_id,
            "version": current_version,
        },
        "new_collection": {
            "bucket": stac_bucket,
            
            "key": new_collection_key,
            "href": new_collection_href,
            "id": new_collection_id,
            "version": new_version,
        },
        "summary": manifest["summary"],
        "classification": {
            "unchanged": unchanged_rows,
            "changed": changed_rows,
            "new": new_rows,
            "removed": [{"tif_key": key} for key in removed_keys],
        },
        "planned_deprecations": planned_deprecations,
        "outputs": {
            "new_collection_key": new_collection_key,
            "new_manifest_key": new_manifest_key,
            "change_report_key": change_report_key,
        },
    }

    print(json.dumps(report["summary"], indent=2))

    if args.dry_run:
        print("Dry run: no files written")
        return

    put_json_to_s3(s3, stac_bucket, new_collection_key, collection_doc)
    put_json_to_s3(s3, stac_bucket, new_manifest_key, manifest)
    put_json_to_s3(s3, stac_bucket, change_report_key, report)

    print(f"Wrote new collection: {new_collection_href}")
    print(f"Wrote manifest: {s3_https_uri(stac_bucket, new_manifest_key)}")
    print(f"Wrote change report: {s3_https_uri(stac_bucket, change_report_key)}")
    print("Run 2 reminder: apply planned deprecations with s3_incremental_deprecation_updater.py")


if __name__ == "__main__":
    main()
