#!/usr/bin/env python3
"""Create a STAC Item JSON from a GeoTIFF stored in S3 and upload it back to S3."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import timezone
from pathlib import Path
from urllib.parse import quote

from stac_item_shared import build_stac_item, parse_semver, parse_bool_arg, upsert_link


def s3_uri(bucket: str, key: str) -> str:
    normalized_key = key.lstrip("/")
    return f"https://{bucket}.s3.amazonaws.com/{quote(normalized_key, safe='/')}"


def maybe_get_s3_client(profile: str | None):
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required for S3 mode. Install with: pip install boto3") from exc

    if profile:
        session = boto3.Session(profile_name=profile)
        return session.client("s3")
    return boto3.client("s3")


def get_s3_object_head_fields(s3, bucket: str, key: str) -> tuple[str | None, str]:
    """Return ETag and LastModified (UTC ISO-8601 Z) from a single head_object call."""
    response = s3.head_object(Bucket=bucket, Key=key)
    etag = response.get("ETag")
    cleaned_etag = str(etag).strip('"') if etag else None
    last_modified = response["LastModified"].astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return cleaned_etag, last_modified


def build_and_upload_item_from_s3(
    s3,
    bucket: str,
    input_key: str,
    item_version: str,
    deprecated: bool,
    latest_href: str,
    *,
    output_key: str | None = None,
    collection_id: str | None = None,
    root_href: str | None = None,
    parent_href: str | None = None,
    collection_href: str | None = None,
    predecessor_href: str | None = None,
    successor_href: str | None = None,
) -> tuple[dict, str]:
    """Build a STAC Item from an S3 TIFF and upload the item JSON to S3."""
    key_lower = input_key.lower()
    if not (key_lower.endswith(".tif") or key_lower.endswith(".tiff")):
        raise ValueError(f"Input S3 key must end with .tif or .tiff: {input_key}")

    major, minor = parse_semver(item_version)
    is_initial_version = (major, minor) == (1, 0)
    if not is_initial_version and not predecessor_href:
        raise ValueError("predecessor_href is required when item_version is not 1.0")

    normalized_input_key = input_key.strip("/")
    normalized_output_key = output_key.strip("/") if output_key else str(Path(normalized_input_key).with_suffix(".json")).replace("\\", "/")

    with tempfile.TemporaryDirectory(prefix="stac_item_s3_") as td:
        temp_dir = Path(td)
        local_tif = temp_dir / Path(normalized_input_key).name
        source_etag, source_updated = get_s3_object_head_fields(s3, bucket, normalized_input_key)
        s3.download_file(bucket, normalized_input_key, str(local_tif))

        item = build_stac_item(
            local_tif,
            item_version=item_version,
            deprecated=deprecated,
            source_etag=source_etag,
            source_created=source_updated,
            source_updated=source_updated,
        )

        if collection_id:
            item["collection"] = collection_id

        # Source raster lives in S3, so set the asset href to an absolute HTTPS object URL.
        item["assets"]["data"]["href"] = s3_uri(bucket, normalized_input_key)

        item_links = item.setdefault("links", [])
        self_href = s3_uri(bucket, normalized_output_key)
        upsert_link(item_links, "self", self_href, "application/geo+json")

        if collection_href:
            upsert_link(item_links, "collection", collection_href, "application/json")
            upsert_link(item_links, "parent", parent_href or collection_href, "application/json")
        elif parent_href:
            upsert_link(item_links, "parent", parent_href, "application/json")

        if root_href:
            upsert_link(item_links, "root", root_href, "application/json")

        if predecessor_href:
            upsert_link(item_links, "predecessor-version", predecessor_href, "application/geo+json")
        if successor_href:
            upsert_link(item_links, "successor-version", successor_href, "application/geo+json")
        upsert_link(item_links, "latest-version", latest_href, "application/geo+json")

        local_json = temp_dir / "item.json"
        with local_json.open("w", encoding="utf-8") as f:
            json.dump(item, f, indent=2)

        s3.upload_file(str(local_json), bucket, normalized_output_key)

    return item, normalized_output_key


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a STAC Item JSON from an S3 GeoTIFF and upload it to S3")
    parser.add_argument("--s3-bucket", required=True, help="S3 bucket containing input TIFF and target JSON")
    parser.add_argument("--s3-key", required=True, help="S3 key to input .tif/.tiff")
    parser.add_argument("--s3-output-key", help="S3 key for output item JSON (default: input key with .json suffix)")
    parser.add_argument("--s3-profile", help="Optional AWS profile name for boto3 session")
    parser.add_argument("--collection-id", help="Optional collection id to set on the item")
    parser.add_argument("--root-href", help="Optional root catalog href")
    parser.add_argument("--parent-href", help="Optional parent link href (defaults to collection-href when provided)")
    parser.add_argument("--collection-href", help="Optional collection link href")
    parser.add_argument("--item-version", default="1.0", help="Item version string (Major.Minor X.Y)")
    parser.add_argument("--deprecated", default="false", help="Whether this item is deprecated: true|false")
    parser.add_argument("--predecessor-href", help="Href for predecessor-version link (required for non-initial versions)")
    parser.add_argument("--successor-href", help="Optional href for successor-version link")
    parser.add_argument("--latest-href", required=True, help="Href for latest-version link")
    args = parser.parse_args()

    deprecated = parse_bool_arg(args.deprecated)

    bucket = args.s3_bucket
    input_key = args.s3_key.strip("/")
    output_key = args.s3_output_key.strip("/") if args.s3_output_key else str(Path(input_key).with_suffix(".json")).replace("\\", "/")

    s3 = maybe_get_s3_client(args.s3_profile)
    _, output_key = build_and_upload_item_from_s3(
        s3,
        bucket,
        input_key,
        args.item_version,
        deprecated,
        args.latest_href,
        output_key=output_key,
        collection_id=args.collection_id,
        root_href=args.root_href,
        parent_href=args.parent_href,
        collection_href=args.collection_href,
        predecessor_href=args.predecessor_href,
        successor_href=args.successor_href,
    )

    print(f"Read TIFF: {s3_uri(bucket, input_key)}")
    print(f"Wrote STAC item: {s3_uri(bucket, output_key)}")


if __name__ == "__main__":
    main()
