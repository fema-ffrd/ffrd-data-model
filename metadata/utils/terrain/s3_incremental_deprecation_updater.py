#!/usr/bin/env python3
"""Run 2 deprecation updater for an incremental STAC release."""

from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import quote, unquote, urlparse


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


def s3_https_uri(bucket: str, key: str) -> str:
    normalized_key = key.lstrip("/")
    return f"https://{bucket}.s3.amazonaws.com/{quote(normalized_key, safe='/')}"


def parse_s3_href_to_bucket_key(href: str) -> tuple[str, str]:
    parsed = urlparse(href)
    if parsed.scheme == "s3":
        return parsed.netloc, unquote(parsed.path.lstrip("/"))

    if parsed.scheme in {"http", "https"}:
        host = parsed.netloc
        path = parsed.path.lstrip("/")
        vh_match = re.fullmatch(r"([^.]+)\.s3\.amazonaws\.com", host)
        if vh_match:
            return vh_match.group(1), unquote(path)
        if host == "s3.amazonaws.com":
            parts = path.split("/", 1)
            if len(parts) == 2:
                return parts[0], unquote(parts[1])

    raise ValueError(f"Unsupported S3 href format: {href}")


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


def normalize_to_major_minor(version: str | None) -> str | None:
    if not version:
        return None
    raw = str(version).strip()
    match_xy = re.fullmatch(r"(\d+)\.(\d+)", raw)
    if match_xy:
        return raw
    match_xyz = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", raw)
    if match_xyz:
        return f"{match_xyz.group(1)}.{match_xyz.group(2)}"
    return None


def infer_predecessor_collection_href(bucket: str, key: str, version: str | None) -> str | None:
    normalized = normalize_to_major_minor(version)
    if not normalized:
        return None
    match = re.fullmatch(r"(\d+)\.(\d+)", normalized)
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2))
    if minor <= 0:
        return None
    predecessor_version = f"{major}.{minor - 1}"
    if normalized not in key:
        return None
    predecessor_key = key.replace(normalized, predecessor_version)
    return s3_https_uri(bucket, predecessor_key)


def try_load_collection_from_s3(s3, bucket: str, key: str) -> dict | None:
    try:
        payload = load_json_from_s3(s3, bucket, key)
    except Exception:
        return None
    if payload.get("type") != "Collection":
        return None
    return payload


def discover_previous_collection_chain(
    s3,
    start_bucket: str,
    start_key: str,
    start_doc: dict,
    start_version: str | None,
) -> list[dict]:
    """Discover older collection versions by following predecessor links, then key/version inference."""
    chain_newest_to_oldest: list[dict] = []
    visited: set[tuple[str, str]] = set()

    current_bucket = start_bucket
    current_key = start_key
    current_doc = start_doc
    current_version = normalize_to_major_minor(start_version or str(start_doc.get("version") or ""))

    for _ in range(100):
        marker = (current_bucket, current_key)
        if marker in visited:
            break
        visited.add(marker)

        chain_newest_to_oldest.append(
            {
                "bucket": current_bucket,
                "key": current_key,
                "href": s3_https_uri(current_bucket, current_key),
                "doc": current_doc,
                "version": current_version,
            }
        )

        predecessor_href = get_link_href(current_doc.get("links", []), "predecessor-version")
        predecessor_bucket = None
        predecessor_key = None

        if predecessor_href:
            try:
                predecessor_bucket, predecessor_key = parse_s3_href_to_bucket_key(predecessor_href)
            except Exception:
                predecessor_bucket, predecessor_key = None, None

        if not predecessor_bucket or not predecessor_key:
            inferred_href = infer_predecessor_collection_href(current_bucket, current_key, current_version)
            if inferred_href:
                try:
                    predecessor_bucket, predecessor_key = parse_s3_href_to_bucket_key(inferred_href)
                except Exception:
                    predecessor_bucket, predecessor_key = None, None

        if not predecessor_bucket or not predecessor_key:
            break

        predecessor_doc = try_load_collection_from_s3(s3, predecessor_bucket, predecessor_key)
        if not predecessor_doc:
            break

        current_bucket = predecessor_bucket
        current_key = predecessor_key
        current_doc = predecessor_doc
        current_version = normalize_to_major_minor(str(current_doc.get("version") or ""))

    return list(reversed(chain_newest_to_oldest))


def reconcile_collection_chain_links(
    collection: dict,
    *,
    predecessor_href: str | None,
    successor_href: str | None,
    latest_href: str,
) -> bool:
    links = collection.setdefault("links", [])
    before = json.dumps(links, sort_keys=True)

    # Normalize chain links to a deterministic position before item links.
    chain_rels = {"predecessor-version", "successor-version", "latest-version"}
    retained_links = [
        link for link in links
        if isinstance(link, dict) and link.get("rel") not in chain_rels
    ]

    chain_links: list[dict] = []
    if predecessor_href:
        chain_links.append({"rel": "predecessor-version", "href": predecessor_href, "type": "application/json"})
    if successor_href:
        chain_links.append({"rel": "successor-version", "href": successor_href, "type": "application/json"})
    chain_links.append({"rel": "latest-version", "href": latest_href, "type": "application/json"})

    insert_at = next((i for i, link in enumerate(retained_links) if link.get("rel") == "item"), len(retained_links))
    normalized_links = retained_links[:insert_at] + chain_links + retained_links[insert_at:]
    collection["links"] = normalized_links

    after = json.dumps(collection["links"], sort_keys=True)

    changed = before != after
    if changed:
        collection["updated"] = iso_z_now()
    return changed


def load_json_from_s3(s3, bucket: str, key: str) -> dict:
    response = s3.get_object(Bucket=bucket, Key=key)
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


def patch_deprecated_item(item: dict, *, successor_href: str | None, latest_href: str | None, reason: str) -> dict:
    item_props = item.setdefault("properties", {})
    item_props["deprecated"] = True
    item_props["updated"] = iso_z_now()
    item_props["deprecated_at"] = iso_z_now()

    links = item.setdefault("links", [])
    if successor_href:
        upsert_link(links, "successor-version", successor_href, "application/geo+json")
    else:
        remove_link(links, "successor-version")

    if latest_href:
        upsert_link(links, "latest-version", latest_href, "application/geo+json")

    item_props["deprecation_reason"] = reason
    return item


def patch_deprecated_collection(
    collection: dict,
    *,
    predecessor_href: str | None,
    successor_href: str,
    latest_href: str,
) -> dict:
    collection["deprecated"] = True
    collection["updated"] = iso_z_now()
    collection["deprecated_at"] = iso_z_now()
    collection["deprecation_reason"] = "superseded"

    links = collection.setdefault("links", [])
    if predecessor_href:
        upsert_link(links, "predecessor-version", predecessor_href, "application/json")
    else:
        remove_link(links, "predecessor-version")
    upsert_link(links, "successor-version", successor_href, "application/json")
    upsert_link(links, "latest-version", latest_href, "application/json")
    return collection


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply run-2 deprecations from an incremental change report")
    parser.add_argument("--stac-bucket", required=True, help="Bucket containing STAC metadata and change report")
    parser.add_argument("--change-report-key", required=True, help="S3 key to change-report.json from run 1")
    parser.add_argument("--dry-run", action="store_true", help="Show planned updates without writing")
    parser.add_argument("--s3-profile", help="Optional AWS profile")
    args = parser.parse_args()

    s3 = maybe_get_s3_client(args.s3_profile)

    report = load_json_from_s3(s3, args.stac_bucket, args.change_report_key.strip("/"))
    previous_collection = report.get("previous_collection") or report.get("source_collection") or {}
    new_collection = report.get("new_collection") or report.get("target_collection") or {}

    if not previous_collection or not new_collection:
        raise ValueError("Change report is missing previous_collection or new_collection")

    prev_bucket = str(previous_collection.get("bucket") or args.stac_bucket)
    prev_key = str(previous_collection["key"])
    prev_version = str(previous_collection.get("version") or "").strip() or None

    new_bucket = str(new_collection.get("bucket") or "").strip()
    new_key = str(new_collection.get("key") or "").strip().strip("/")
    if (not new_bucket or not new_key) and new_collection.get("href"):
        parsed_bucket, parsed_key = parse_s3_href_to_bucket_key(str(new_collection["href"]))
        new_bucket = new_bucket or parsed_bucket
        new_key = new_key or parsed_key

    if not new_bucket:
        new_bucket = args.stac_bucket
    if not new_key:
        raise ValueError("Change report is missing new collection key/href")

    new_href = s3_https_uri(new_bucket, new_key)

    current_collection_doc = load_json_from_s3(s3, prev_bucket, prev_key)
    original_previous_collection_doc = deepcopy(current_collection_doc)
    report_predecessor_href = previous_collection.get("predecessor_href") or (report.get("source_collection") or {}).get("predecessor_href")
    existing_predecessor_href = get_link_href(current_collection_doc.get("links", []), "predecessor-version")
    inferred_predecessor_href = infer_predecessor_collection_href(prev_bucket, prev_key, prev_version)
    predecessor_href = str(report_predecessor_href or existing_predecessor_href or inferred_predecessor_href or "").strip() or None

    current_collection_doc = patch_deprecated_collection(
        current_collection_doc,
        predecessor_href=predecessor_href,
        successor_href=new_href,
        latest_href=new_href,
    )

    chain = discover_previous_collection_chain(
        s3,
        start_bucket=prev_bucket,
        start_key=prev_key,
        start_doc=current_collection_doc,
        start_version=prev_version,
    )

    new_collection_doc = try_load_collection_from_s3(s3, new_bucket, new_key)
    if not new_collection_doc:
        raise ValueError(f"Unable to load new collection: s3://{new_bucket}/{new_key}")

    chain.append(
        {
            "bucket": new_bucket,
            "key": new_key,
            "href": new_href,
            "doc": new_collection_doc,
            "version": normalize_to_major_minor(str(new_collection_doc.get("version") or "")),
        }
    )

    latest_collection_href = chain[-1]["href"]
    updated_collections: list[dict] = []

    for i, entry in enumerate(chain):
        pred_href = chain[i - 1]["href"] if i > 0 else None
        succ_href = chain[i + 1]["href"] if i < len(chain) - 1 else None
        changed = reconcile_collection_chain_links(
            entry["doc"],
            predecessor_href=pred_href,
            successor_href=succ_href,
            latest_href=latest_collection_href,
        )

        # For the previous collection, include deprecated-state mutation in change reporting.
        if entry["bucket"] == prev_bucket and entry["key"] == prev_key:
            previous_before = json.dumps(original_previous_collection_doc, sort_keys=True)
            previous_after = json.dumps(entry["doc"], sort_keys=True)
            changed = previous_before != previous_after

        updated_collections.append(
            {
                "bucket": entry["bucket"],
                "key": entry["key"],
                "href": entry["href"],
                "predecessor_href": pred_href,
                "successor_href": succ_href,
                "latest_href": latest_collection_href,
                "changed": changed,
            }
        )

        if not args.dry_run and changed:
            put_json_to_s3(s3, entry["bucket"], entry["key"], entry["doc"])

    updated_items = []
    for row in report.get("planned_deprecations", []):
        old_item_bucket = row.get("old_item_bucket")
        old_item_key = row.get("old_item_key")
        old_item_href = row.get("old_item_href")

        if (not old_item_bucket or not old_item_key) and old_item_href:
            old_item_bucket, old_item_key = parse_s3_href_to_bucket_key(str(old_item_href))

        if not old_item_bucket or not old_item_key:
            continue

        raw_reason = str(row.get("reason") or "").strip().lower()
        reason = "removed" if raw_reason == "removed" else "superseded"
        successor_href = row.get("new_item_href")
        latest_href = successor_href
        if not latest_href:
            latest_href = str(old_item_href or s3_https_uri(str(old_item_bucket), str(old_item_key)))

        item_doc = load_json_from_s3(s3, str(old_item_bucket), str(old_item_key))
        item_doc = patch_deprecated_item(
            item_doc,
            successor_href=str(successor_href) if successor_href else None,
            latest_href=str(latest_href) if latest_href else None,
            reason=reason,
        )

        updated_items.append(
            {
                "bucket": str(old_item_bucket),
                "key": str(old_item_key),
                "successor_href": successor_href,
                "latest_href": latest_href,
                "reason": row.get("reason"),
            }
        )

        if not args.dry_run:
            put_json_to_s3(s3, str(old_item_bucket), str(old_item_key), item_doc)

    summary = {
        "updated_collection": {
            "bucket": prev_bucket,
            "key": prev_key,
            "href": s3_https_uri(prev_bucket, prev_key),
        },
        "validated_collections": updated_collections,
        "validated_collection_count": len(updated_collections),
        "updated_items": len(updated_items),
        "dry_run": bool(args.dry_run),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
