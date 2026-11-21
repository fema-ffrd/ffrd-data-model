#!/usr/bin/env python3
"""Create a STAC Collection from TIFF and VRT files in a directory."""

from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from stac_item_shared import build_stac_item


def parse_json_arg(raw: str, arg_name: str, expected_type: type):
    """Parse and type-check JSON passed through a CLI argument."""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for {arg_name}: {exc}") from exc
    if not isinstance(value, expected_type):
        raise ValueError(f"{arg_name} must be valid JSON {expected_type.__name__}")
    return value


def normalize_keywords(raw_keywords: list[str] | None) -> list[str]:
    """Flatten repeated/comma-separated keyword inputs into a unique ordered list."""
    if not raw_keywords:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for chunk in raw_keywords:
        for token in chunk.split(","):
            value = token.strip()
            if value and value not in seen:
                seen.add(value)
                normalized.append(value)
    return normalized


def parse_semver(value: str) -> tuple[int, int]:
    """Validate Major.Minor-like X.Y and return integer components."""
    match = re.fullmatch(r"(\d+)\.(\d+)", value)
    if not match:
        raise ValueError(f"Version must match X.Y, got: {value}")
    return int(match.group(1)), int(match.group(2))


def parse_bool_arg(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"Expected boolean true/false value, got: {value}")


def render_lineage_href(template: str, context: dict[str, str | int]) -> str:
    """Render lineage href from a user template and item context."""
    try:
        return str(template.format(**context))
    except KeyError as exc:
        raise ValueError(f"Unknown template field in lineage template: {exc}") from exc


def s3_uri(bucket: str, key: str) -> str:
    normalized_key = key.lstrip("/")
    return f"https://{bucket}.s3.amazonaws.com/{quote(normalized_key, safe='/')}"


def default_s3_catalog_href(bucket: str, collection_key: str) -> str:
    """Return the catalog href one folder above the collection key's folder."""
    collection_folder = Path(collection_key).parent
    catalog_key = (collection_folder.parent / "catalog.json").as_posix()
    return s3_uri(bucket, catalog_key)


def maybe_get_s3_client(profile: str | None):
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required for S3 mode. Install with: pip install boto3") from exc

    if profile:
        session = boto3.Session(profile_name=profile)
        return session.client("s3")
    return boto3.client("s3")


def load_s3_item_builder():
    """Load item builder helper from sibling script with a hyphen in its filename."""
    script_path = Path(__file__).with_name("s3-stac_item_from_tiff.py")
    spec = importlib.util.spec_from_file_location("s3_stac_item_from_tiff_script", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module spec from {script_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    build_fn = getattr(module, "build_and_upload_item_from_s3", None)
    if build_fn is None:
        raise RuntimeError("Expected build_and_upload_item_from_s3 in s3-stac_item_from_tiff.py")
    return build_fn


def posix_relpath(target: Path, start: Path) -> str:
    """Return POSIX-style relative path from start to target."""
    return Path(os.path.relpath(target, start)).as_posix()


def upsert_link(links: list[dict], rel: str, href: str, media_type: str) -> None:
    for link in links:
        if link.get("rel") == rel:
            link["href"] = href
            link["type"] = media_type
            return
    links.append({"rel": rel, "href": href, "type": media_type})


def collection_link_title(rel: str, href: str) -> str:
    """Create a readable title for collection links."""
    if rel == "self":
        return "Collection JSON"
    if rel == "root":
        return "Root Catalog"
    if rel == "parent":
        return "Parent Catalog"
    if rel == "item":
        return Path(href).name
    return rel.replace("-", " ").title()


def upsert_asset(assets: dict, key: str, asset: dict) -> None:
    """Insert an asset using a unique key if collisions occur."""
    if key not in assets:
        assets[key] = asset
        return

    idx = 2
    while f"{key}_{idx}" in assets:
        idx += 1
    assets[f"{key}_{idx}"] = asset


def sanitize_asset_key(value: str) -> str:
    """Normalize an asset key to alphanumeric/underscore characters."""
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return cleaned or "asset"


def quote_sql_identifier(identifier: str) -> str:
    """Quote a SQLite identifier safely."""
    return f'"{identifier.replace("\"", "\"\"")}"'


def read_gpkg_tables(gpkg_path: Path) -> list[dict]:
    """Read table-level metadata from a GeoPackage file."""
    if not gpkg_path.exists() or not gpkg_path.is_file():
        raise FileNotFoundError(f"GeoPackage not found: {gpkg_path}")

    with sqlite3.connect(gpkg_path) as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT
                c.table_name,
                c.data_type,
                c.identifier,
                c.description,
                c.srs_id,
                c.min_x,
                c.min_y,
                c.max_x,
                c.max_y,
                gc.column_name AS geometry_column,
                gc.geometry_type_name,
                s.organization,
                s.organization_coordsys_id
            FROM gpkg_contents c
            LEFT JOIN gpkg_geometry_columns gc ON c.table_name = gc.table_name
            LEFT JOIN gpkg_spatial_ref_sys s ON c.srs_id = s.srs_id
            ORDER BY c.table_name
            """
        ).fetchall()

        tables: list[dict] = []
        for row in rows:
            table_name = str(row["table_name"])
            row_count = conn.execute(
                f"SELECT COUNT(*) FROM {quote_sql_identifier(table_name)}"
            ).fetchone()[0]

            col_rows = conn.execute(
                f"PRAGMA table_info({quote_sql_identifier(table_name)})"
            ).fetchall()
            columns = [
                {
                    "name": col["name"],
                    "type": col["type"],
                    "not_null": bool(col["notnull"]),
                    "primary_key": bool(col["pk"]),
                }
                for col in col_rows
            ]

            bbox = None
            if all(row[k] is not None for k in ("min_x", "min_y", "max_x", "max_y")):
                bbox = [row["min_x"], row["min_y"], row["max_x"], row["max_y"]]

            crs = None
            if row["organization"] and row["organization_coordsys_id"] is not None:
                crs = f"{row['organization']}:{row['organization_coordsys_id']}"

            tables.append(
                {
                    "table_name": table_name,
                    "data_type": row["data_type"],
                    "identifier": row["identifier"],
                    "description": row["description"],
                    "srs_id": row["srs_id"],
                    "crs": crs,
                    "geometry_column": row["geometry_column"],
                    "geometry_type": row["geometry_type_name"],
                    "row_count": row_count,
                    "bbox": bbox,
                    "columns": columns,
                }
            )

        return tables


def add_gpkg_rollup_asset(assets: dict, gpkg_href: str, gpkg_name: str, tables: list[dict]) -> tuple[int, int]:
    """Add a single GeoPackage asset with nested per-table metadata."""
    rollup_tables: list[dict] = []
    total_rows = 0
    data_types: set[str] = set()

    for meta in tables:
        table_entry = {
            "name": meta.get("table_name"),
            "data_type": meta.get("data_type"),
            "row_count": meta.get("row_count"),
            "columns": meta.get("columns", []),
        }
        if meta.get("identifier"):
            table_entry["identifier"] = meta["identifier"]
        if meta.get("description"):
            table_entry["description"] = meta["description"]
        if meta.get("geometry_column"):
            table_entry["geometry_column"] = meta["geometry_column"]
        if meta.get("geometry_type"):
            table_entry["geometry_type"] = meta["geometry_type"]
        if meta.get("crs"):
            table_entry["crs"] = meta["crs"]
        if meta.get("bbox"):
            table_entry["bbox"] = meta["bbox"]

        rollup_tables.append(table_entry)
        if isinstance(meta.get("row_count"), int):
            total_rows += int(meta["row_count"])
        if meta.get("data_type"):
            data_types.add(str(meta["data_type"]))

    asset_key = sanitize_asset_key(Path(gpkg_name).stem)
    asset = {
        "href": gpkg_href,
        "type": "application/geopackage+sqlite3",
        "roles": ["data", "metadata"],
        "title": gpkg_name,
        "gpkg:name": gpkg_name,
        "gpkg:table_count": len(rollup_tables),
        "gpkg:row_count_total": total_rows,
        "gpkg:data_types": sorted(data_types),
        "gpkg:tables": rollup_tables,
    }
    upsert_asset(assets, asset_key, asset)
    return 1, len(rollup_tables)


def cleanup_temp_dir_with_retries(temp_dir: Path, retries: int = 20, delay_seconds: float = 0.5) -> bool:
    """Best-effort cleanup for Windows where transient file locks can block deletion."""
    for _ in range(retries):
        try:
            if not temp_dir.exists():
                return True
            # Encourage timely finalization of sqlite-related objects before delete.
            gc.collect()
            shutil.rmtree(temp_dir)
            return True
        except PermissionError:
            time.sleep(delay_seconds)

    return not temp_dir.exists()


def merge_bboxes(bboxes: list[list[float]]) -> list[float]:
    """Merge multiple [minx, miny, maxx, maxy] boxes into one bbox."""
    minx = min(b[0] for b in bboxes)
    miny = min(b[1] for b in bboxes)
    maxx = max(b[2] for b in bboxes)
    maxy = max(b[3] for b in bboxes)
    return [minx, miny, maxx, maxy]


def collect_datetimes(items: list[dict]) -> tuple[str | None, str | None]:
    """Return min/max datetime values found across items."""
    values = []
    for item in items:
        dt = item.get("properties", {}).get("datetime")
        if dt:
            values.append(dt)
    if not values:
        return None, None
    return min(values), max(values)


def find_files(base_dir: Path, patterns: tuple[str, ...], recursive: bool) -> list[Path]:
    """Find files matching one or more glob patterns."""
    found: list[Path] = []
    for pattern in patterns:
        matches = base_dir.rglob(pattern) if recursive else base_dir.glob(pattern)
        found.extend([p for p in matches if p.is_file()])
    return sorted(set(p.resolve() for p in found))


def list_s3_keys(s3, bucket: str, prefix: str, recursive: bool, suffixes: tuple[str, ...]) -> list[str]:
    """List S3 object keys under prefix filtered by suffix and recursion mode."""
    normalized_prefix = prefix.strip("/")
    if normalized_prefix:
        normalized_prefix += "/"

    paginator = s3.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=normalized_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            rel = key[len(normalized_prefix):] if normalized_prefix and key.startswith(normalized_prefix) else key
            if not recursive and "/" in rel:
                continue
            if rel.lower().endswith(suffixes):
                keys.append(key)
    return sorted(keys)


def iso_z(dt) -> str:
    """Format a datetime-like value as UTC ISO-8601 with a trailing Z."""
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso_z_now() -> str:
    """Return current UTC time in ISO-8601 with trailing Z."""
    return iso_z(datetime.now(timezone.utc))


def get_s3_object_snapshot(s3, bucket: str, key: str) -> dict:
    """Return size/last_modified/etag snapshot for an S3 object."""
    response = s3.head_object(Bucket=bucket, Key=key)
    etag = response.get("ETag")
    return {
        "size": int(response.get("ContentLength", 0)),
        "last_modified": iso_z(response["LastModified"]),
        "etag": str(etag).strip('"') if etag else None,
    }


def s3_object_exists(s3, bucket: str, key: str) -> bool:
    """Return True when object exists, False for not-found responses."""
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except Exception as exc:
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            code = str(response.get("Error", {}).get("Code", ""))
            if code in {"NoSuchKey", "404", "NotFound"}:
                return False
        raise


def collect_item_extensions(items: list[dict]) -> list[str]:
    """Return an ordered de-duplicated list of item stac_extensions."""
    ordered: list[str] = []
    seen: set[str] = set()
    for item in items:
        for ext in item.get("stac_extensions", []):
            if ext not in seen:
                seen.add(ext)
                ordered.append(ext)
    return ordered


def collect_crs_summaries(items: list[dict]) -> dict:
    """Collect CRS representation from item properties for collection summaries."""
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a STAC Collection JSON from all TIFF files in a directory")
    parser.add_argument("directory", nargs="?", type=Path, help="Directory to scan for TIFF and VRT files (local mode)")
    parser.add_argument("-o", "--output", type=Path, help="Output Collection path (default: directory/collection.json)")
    parser.add_argument("--collection-id", help="Collection id (default: directory name)")
    parser.add_argument("--title", help="Collection title")
    parser.add_argument("--description", default="Collection generated from TIFF and VRT files.", help="Collection description")
    parser.add_argument("--license", default="proprietary", help="Collection license")
    parser.add_argument("--item-version", default="1.0", help="Version for all generated items (Major.Minor X.Y)")
    parser.add_argument("--deprecated", default="false", help="Whether generated items are deprecated: true|false")
    parser.add_argument(
        "--predecessor-template",
        help="Template for predecessor-version href (required for non-initial versions), e.g. ../v1/{item_json}",
    )
    parser.add_argument(
        "--successor-template",
        help="Optional template for successor-version href, e.g. ../v2/{item_json}",
    )
    parser.add_argument(
        "--latest-template",
        required=True,
        help="Template for latest-version href, e.g. {item_json}",
    )
    parser.add_argument(
        "--providers-json",
        help="JSON array for collection providers, e.g. '[{\"name\":\"FEMA\",\"roles\":[\"producer\"]}]'",
    )
    parser.add_argument(
        "--keywords",
        action="append",
        help="Collection keywords (repeatable and/or comma-separated), e.g. --keywords flood,dem --keywords terrain",
    )
    parser.add_argument(
        "--summaries-json",
        help="JSON object for collection summaries, e.g. '{\"gsd\":[96],\"platform\":[\"airborne\"]}'",
    )
    parser.add_argument("--root-href", help="Optional root catalog href from collection (for root/parent links)")
    parser.add_argument("--recursive", action="store_true", help="Scan subdirectories recursively")
    parser.add_argument("--s3-bucket", help="S3 bucket for input/output mode")
    parser.add_argument("--s3-prefix", help="S3 prefix to scan for TIFF/VRT files")
    parser.add_argument("--s3-output-key", help="S3 key for output collection JSON (default: <s3-prefix>/collection.json)")
    parser.add_argument("--s3-manifest-key", help="Optional S3 key for output manifest JSON (default: <collection-folder>/manifest.json)")
    parser.add_argument("--s3-gpkg-key", help="Optional S3 key for a GeoPackage; adds one collection asset per table")
    parser.add_argument(
        "--gpkg",
        type=Path,
        help="Optional local GeoPackage file. Adds one collection asset per table with table metadata.",
    )
    parser.add_argument("--s3-profile", help="Optional AWS profile name for boto3 session")
    args = parser.parse_args()

    s3_mode = args.s3_bucket is not None or args.s3_prefix is not None or args.s3_output_key is not None

    if s3_mode and not args.s3_bucket:
        raise ValueError("--s3-bucket is required when using S3 mode")
    if s3_mode and not args.s3_prefix:
        raise ValueError("--s3-prefix is required when using S3 mode")
    if not s3_mode and args.directory is None:
        raise ValueError("directory is required in local mode")
    if s3_mode and args.gpkg:
        raise ValueError("--gpkg is only supported in local mode. Use --s3-gpkg-key in S3 mode.")

    major, minor = parse_semver(args.item_version)
    is_initial_version = (major, minor) == (1, 0)
    if not is_initial_version and not args.predecessor_template:
        raise ValueError("--predecessor-template is required when --item-version is not 1.0")
    deprecated = parse_bool_arg(args.deprecated)
    providers = parse_json_arg(args.providers_json, "--providers-json", list) if args.providers_json else None
    summaries = parse_json_arg(args.summaries_json, "--summaries-json", dict) if args.summaries_json else {}
    keywords = normalize_keywords(args.keywords)

    items: list[dict] = []
    item_hrefs_for_collection: list[str] = []

    if s3_mode:
        s3 = maybe_get_s3_client(args.s3_profile)
        bucket = args.s3_bucket
        prefix = args.s3_prefix.strip("/")
        collection_key = args.s3_output_key.strip("/") if args.s3_output_key else f"{prefix}/collection.json"
        collection_folder = Path(collection_key).parent.as_posix()
        manifest_key = args.s3_manifest_key.strip("/") if args.s3_manifest_key else (
            f"{collection_folder}/manifest.json" if collection_folder else "manifest.json"
        )
        catalog_href = args.root_href or default_s3_catalog_href(bucket, collection_key)

        collection_id = args.collection_id or Path(prefix).name
        title = args.title or collection_id.replace("-", " ").replace("_", " ").title()

        tif_keys = list_s3_keys(s3, bucket, prefix, args.recursive, (".tif", ".tiff"))
        if not tif_keys:
            raise ValueError(f"No TIFF files found in https://{bucket}.s3.amazonaws.com/{quote(prefix, safe='/')}")

        vrt_keys = list_s3_keys(s3, bucket, prefix, args.recursive, (".vrt",))

        build_item_from_s3 = load_s3_item_builder()
        manifest_items: list[dict] = []

        temp_root = Path(tempfile.mkdtemp(prefix="stac_s3_"))
        try:

            for tif_key in tif_keys:
                item_name = f"{Path(tif_key).stem}.json"
                item_key = f"{collection_folder}/{item_name}" if collection_folder else item_name
                item_self_href = s3_uri(bucket, item_key)
                collection_href = s3_uri(bucket, collection_key)
                lineage_context = {
                    "item_json": Path(item_key).name,
                    "item_href": item_self_href,
                    "version": args.item_version,
                    "major": major,
                    "minor": minor,
                }

                predecessor_href = render_lineage_href(args.predecessor_template, lineage_context) if args.predecessor_template else None
                successor_href = render_lineage_href(args.successor_template, lineage_context) if args.successor_template else None
                latest_href = render_lineage_href(args.latest_template, lineage_context)

                try:
                    item, _ = build_item_from_s3(
                        s3,
                        bucket,
                        tif_key,
                        args.item_version,
                        deprecated,
                        latest_href,
                        output_key=item_key,
                        collection_id=collection_id,
                        root_href=catalog_href,
                        parent_href=collection_href,
                        collection_href=collection_href,
                        predecessor_href=predecessor_href,
                        successor_href=successor_href,
                    )
                except Exception as exc:
                    raise RuntimeError(
                        f"Failed to build/upload item for TIFF key: s3://{bucket}/{tif_key}. "
                        "Verify the source object still exists and is readable with the selected AWS profile."
                    ) from exc

                items.append(item)
                item_hrefs_for_collection.append(item_self_href)
                snapshot = get_s3_object_snapshot(s3, bucket, tif_key)
                manifest_items.append(
                    {
                        "logical_id": item.get("id"),
                        "tif_key": tif_key,
                        "etag": snapshot.get("etag"),
                        "size": snapshot.get("size"),
                        "last_modified": snapshot.get("last_modified"),
                        "status": "new",
                        "item_version": args.item_version,
                        "item_key": item_key,
                        "item_href": item_self_href,
                        "detection_method": "initial_snapshot",
                    }
                )

            collection_href = s3_uri(bucket, collection_key)
            links = [
                {
                    "rel": "self",
                    "href": collection_href,
                    "type": "application/json",
                    "title": collection_link_title("self", collection_href),
                }
            ]
            for href in item_hrefs_for_collection:
                links.append(
                    {
                        "rel": "item",
                        "href": href,
                        "type": "application/geo+json",
                        "title": collection_link_title("item", href),
                    }
                )

            links.insert(
                1,
                {
                    "rel": "root",
                    "href": catalog_href,
                    "type": "application/json",
                    "title": collection_link_title("root", catalog_href),
                },
            )
            links.insert(
                2,
                {
                    "rel": "parent",
                    "href": catalog_href,
                    "type": "application/json",
                    "title": collection_link_title("parent", catalog_href),
                },
            )

            assets: dict = {}
            for vrt_key in vrt_keys:
                upsert_asset(
                    assets,
                    Path(vrt_key).stem,
                    {
                        "href": s3_uri(bucket, vrt_key),
                        "type": "application/xml",
                        "roles": ["metadata"],
                        "title": Path(vrt_key).name,
                    },
                )

            gpkg_asset_count = 0
            gpkg_table_count = 0
            if args.s3_gpkg_key:
                gpkg_key = args.s3_gpkg_key.strip("/")
                if not s3_object_exists(s3, bucket, gpkg_key):
                    available_gpkgs = list_s3_keys(s3, bucket, prefix, True, (".gpkg",))
                    examples = available_gpkgs[:5]
                    if examples:
                        suggestion_text = "\n".join([f"- s3://{bucket}/{k}" for k in examples])
                        raise ValueError(
                            f"GeoPackage key not found: s3://{bucket}/{gpkg_key}\n"
                            "Found these .gpkg keys under the source prefix:\n"
                            f"{suggestion_text}\n"
                            "Pass one of these with --s3-gpkg-key."
                        )
                    raise ValueError(
                        f"GeoPackage key not found: s3://{bucket}/{gpkg_key}. "
                        "No .gpkg files were found under --s3-prefix."
                    )
                local_gpkg = temp_root / Path(gpkg_key).name
                try:
                    s3.download_file(bucket, gpkg_key, str(local_gpkg))
                except Exception as exc:
                    raise RuntimeError(
                        f"Failed to download GeoPackage from s3://{bucket}/{gpkg_key}. "
                        "Verify the key, permissions, and profile access."
                    ) from exc
                gpkg_tables = read_gpkg_tables(local_gpkg)
                gpkg_asset_count, gpkg_table_count = add_gpkg_rollup_asset(
                    assets,
                    s3_uri(bucket, gpkg_key),
                    Path(gpkg_key).name,
                    gpkg_tables,
                )

            stac_version = items[0].get("stac_version", "1.1.0")
            item_bboxes = [item.get("bbox") for item in items if item.get("bbox")]
            if not item_bboxes:
                raise ValueError("Generated items are missing bbox values")

            merged_bbox = merge_bboxes(item_bboxes)
            dt_start, dt_end = collect_datetimes(items)
            temporal_interval = [[dt_start, dt_end]]
            collection_extensions = collect_item_extensions(items)
            summaries.pop("proj:epsg", None)
            summaries.update(collect_crs_summaries(items))

            collection = {
                "type": "Collection",
                "stac_version": stac_version,
                "stac_extensions": collection_extensions,
                "version": args.item_version,
                "deprecated": deprecated,
                "id": collection_id,
                "title": title,
                "description": args.description,
                "license": args.license,
                "extent": {
                    "spatial": {"bbox": [merged_bbox]},
                    "temporal": {"interval": temporal_interval},
                },
                "links": links,
                "assets": assets,
            }

            if providers:
                collection["providers"] = providers
            if keywords:
                collection["keywords"] = keywords
            if summaries:
                collection["summaries"] = summaries

            local_collection = temp_root / "collection.json"
            with local_collection.open("w", encoding="utf-8") as f:
                json.dump(collection, f, indent=2)
            s3.upload_file(str(local_collection), bucket, collection_key)

            manifest = {
                "manifest_version": "1.0",
                "generated_at": iso_z_now(),
                "dataset_id": collection_id,
                "release_version": args.item_version,
                "source": {
                    "bucket": bucket,
                    "prefix": prefix,
                },
                "stac": {
                    "bucket": bucket,
                    "collection_key": collection_key,
                    "collection_href": collection_href,
                    "catalog_href": catalog_href,
                    "collection_id": collection_id,
                },
                "policy": {
                    "change_detection_primary": "size_last_modified",
                    "change_detection_fallback": "etag",
                },
                "summary": {
                    "total_current_tifs": len(tif_keys),
                    "unchanged": 0,
                    "changed": 0,
                    "new": len(tif_keys),
                    "removed": 0,
                },
                "items": sorted(manifest_items, key=lambda row: str(row.get("tif_key", ""))),
            }

            local_manifest = temp_root / "manifest.json"
            with local_manifest.open("w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
            s3.upload_file(str(local_manifest), bucket, manifest_key)

            print(f"Wrote collection: {collection_href}")
            print(f"Wrote manifest: {s3_uri(bucket, manifest_key)}")
            print(f"Generated/updated item files: {len(item_hrefs_for_collection)}")
            print(f"Added VRT collection assets: {len(vrt_keys)}")
            print(f"Added GeoPackage rollup assets: {gpkg_asset_count}")
            print(f"Rolled up GeoPackage tables: {gpkg_table_count}")
        finally:
            cleaned = cleanup_temp_dir_with_retries(temp_root)
            if not cleaned:
                print(f"Warning: unable to delete temporary directory: {temp_root}")
        return

    base_dir = args.directory.resolve()
    if not base_dir.exists() or not base_dir.is_dir():
        raise FileNotFoundError(f"Directory not found: {base_dir}")

    output_path = args.output.resolve() if args.output else base_dir / "collection.json"
    catalog_href = args.root_href or "../catalog.json"
    collection_id = args.collection_id or base_dir.name
    title = args.title or collection_id.replace("-", " ").replace("_", " ").title()

    tif_files = find_files(base_dir, ("*.tif", "*.tiff"), args.recursive)
    if not tif_files:
        raise ValueError(f"No TIFF files found in {base_dir}")

    vrt_files = find_files(base_dir, ("*.vrt",), args.recursive)

    item_paths: list[Path] = []
    for tif_path in tif_files:
        item = build_stac_item(tif_path, item_version=args.item_version, deprecated=deprecated)
        item["collection"] = collection_id
        item_json_path = output_path.parent / f"{tif_path.stem}.json"

        # Keep TIFF references pointing to the source file location relative to new item location.
        item["assets"]["data"]["href"] = posix_relpath(tif_path, item_json_path.parent)

        item_links = item.setdefault("links", [])
        upsert_link(item_links, "self", posix_relpath(item_json_path, item_json_path.parent), "application/geo+json")
        upsert_link(item_links, "parent", posix_relpath(output_path, item_json_path.parent), "application/json")
        upsert_link(item_links, "collection", posix_relpath(output_path, item_json_path.parent), "application/json")
        upsert_link(item_links, "root", posix_relpath(output_path.parent.parent / "catalog.json", item_json_path.parent), "application/json")
        lineage_context = {
            "item_id": item["id"],
            "item_json": item_json_path.name,
            "item_href": posix_relpath(item_json_path, item_json_path.parent),
            "version": args.item_version,
            "major": major,
            "minor": minor,
        }
        if args.predecessor_template:
            upsert_link(
                item_links,
                "predecessor-version",
                render_lineage_href(args.predecessor_template, lineage_context),
                "application/geo+json",
            )
        if args.successor_template:
            upsert_link(
                item_links,
                "successor-version",
                render_lineage_href(args.successor_template, lineage_context),
                "application/geo+json",
            )
        upsert_link(
            item_links,
            "latest-version",
            render_lineage_href(args.latest_template, lineage_context),
            "application/geo+json",
        )
        item_json_path.parent.mkdir(parents=True, exist_ok=True)
        with item_json_path.open("w", encoding="utf-8") as f:
            json.dump(item, f, indent=2)

        items.append(item)
        item_paths.append(item_json_path)

    stac_version = items[0].get("stac_version", "1.1.0")

    item_bboxes = [item.get("bbox") for item in items if item.get("bbox")]
    if not item_bboxes:
        raise ValueError("Generated items are missing bbox values")

    merged_bbox = merge_bboxes(item_bboxes)
    dt_start, dt_end = collect_datetimes(items)
    temporal_interval = [[dt_start, dt_end]]
    collection_extensions = collect_item_extensions(items)
    summaries.pop("proj:epsg", None)
    summaries.update(collect_crs_summaries(items))

    links = [
        {
            "rel": "self",
            "href": "collection.json",
            "type": "application/json",
            "title": collection_link_title("self", "collection.json"),
        },
    ]

    for item_path in item_paths:
        links.append(
            {
                "rel": "item",
                "href": posix_relpath(item_path, output_path.parent),
                "type": "application/geo+json",
                "title": collection_link_title("item", posix_relpath(item_path, output_path.parent)),
            }
        )

    links.insert(
        1,
        {
            "rel": "root",
            "href": catalog_href,
            "type": "application/json",
            "title": collection_link_title("root", catalog_href),
        },
    )
    links.insert(
        2,
        {
            "rel": "parent",
            "href": catalog_href,
            "type": "application/json",
            "title": collection_link_title("parent", catalog_href),
        },
    )

    assets: dict = {}
    for vrt_path in vrt_files:
        asset_key = vrt_path.stem
        upsert_asset(
            assets,
            asset_key,
            {
                "href": posix_relpath(vrt_path, output_path.parent),
                "type": "application/xml",
                "roles": ["metadata"],
                "title": vrt_path.name,
            },
        )

    gpkg_asset_count = 0
    gpkg_table_count = 0
    if args.gpkg:
        gpkg_path = args.gpkg if args.gpkg.is_absolute() else (base_dir / args.gpkg)
        gpkg_path = gpkg_path.resolve()
        gpkg_tables = read_gpkg_tables(gpkg_path)
        gpkg_asset_count, gpkg_table_count = add_gpkg_rollup_asset(
            assets,
            posix_relpath(gpkg_path, output_path.parent),
            gpkg_path.name,
            gpkg_tables,
        )

    collection = {
        "type": "Collection",
        "stac_version": stac_version,
        "stac_extensions": collection_extensions,
        "version": args.item_version,
        "deprecated": deprecated,
        "id": collection_id,
        "title": title,
        "description": args.description,
        "license": args.license,
        "extent": {
            "spatial": {"bbox": [merged_bbox]},
            "temporal": {"interval": temporal_interval},
        },
        "links": links,
        "assets": assets,
    }

    if providers:
        collection["providers"] = providers
    if keywords:
        collection["keywords"] = keywords
    if summaries:
        collection["summaries"] = summaries

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(collection, f, indent=2)

    print(f"Wrote collection: {output_path}")
    print(f"Generated/updated item files: {len(item_paths)}")
    print(f"Added VRT collection assets: {len(vrt_files)}")
    print(f"Added GeoPackage rollup assets: {gpkg_asset_count}")
    print(f"Rolled up GeoPackage tables: {gpkg_table_count}")


if __name__ == "__main__":
    main()