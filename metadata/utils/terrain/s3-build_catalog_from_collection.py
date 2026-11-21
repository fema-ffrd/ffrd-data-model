#!/usr/bin/env python3
"""Create a STAC Catalog from a single STAC Collection."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import quote


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


def upsert_link(links: list[dict], rel: str, href: str, media_type: str) -> None:
    for link in links:
        if link.get("rel") == rel:
            link["href"] = href
            link["type"] = media_type
            return
    links.append({"rel": rel, "href": href, "type": media_type})


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a top-level STAC Catalog JSON from a Collection JSON")
    parser.add_argument("collection", nargs="?", type=Path, help="Path to STAC Collection JSON (local mode)")
    parser.add_argument("-o", "--output", type=Path, help="Output catalog path (default: parent-folder/catalog.json)")
    parser.add_argument("--catalog-id", help="Catalog id (default: output folder name)")
    parser.add_argument("--title", help="Catalog title")
    parser.add_argument("--description", default="Top-level STAC catalog.", help="Catalog description")
    parser.add_argument("--update-collection-links", action="store_true", help="Update collection with root/parent links to this catalog")
    parser.add_argument("--s3-bucket", help="S3 bucket for input/output mode")
    parser.add_argument("--s3-collection-key", help="S3 key for input collection JSON")
    parser.add_argument("--s3-output-key", help="S3 key for output catalog JSON")
    parser.add_argument("--s3-profile", help="Optional AWS profile name for boto3 session")
    args = parser.parse_args()

    s3_mode = args.s3_bucket is not None or args.s3_collection_key is not None or args.s3_output_key is not None

    if s3_mode and not args.s3_bucket:
        raise ValueError("--s3-bucket is required when using S3 mode")
    if s3_mode and not args.s3_collection_key:
        raise ValueError("--s3-collection-key is required when using S3 mode")
    if not s3_mode and args.collection is None:
        raise ValueError("collection is required in local mode")

    if s3_mode:
        s3 = maybe_get_s3_client(args.s3_profile)
        bucket = args.s3_bucket
        collection_key = args.s3_collection_key.strip("/")
        output_key = args.s3_output_key.strip("/") if args.s3_output_key else str((Path(collection_key).parent.parent / "catalog.json").as_posix())

        with tempfile.TemporaryDirectory(prefix="stac_s3_") as td:
            temp_root = Path(td)
            local_collection = temp_root / "collection.json"
            s3.download_file(bucket, collection_key, str(local_collection))

            with local_collection.open("r", encoding="utf-8") as f:
                collection = json.load(f)

            if collection.get("type") != "Collection":
                raise ValueError("Input file is not a STAC Collection")

            catalog_id = args.catalog_id or Path(output_key).parent.name
            title = args.title or catalog_id.replace("-", " ").replace("_", " ").title()
            child_href = s3_uri(bucket, collection_key)
            catalog_href = s3_uri(bucket, output_key)

            catalog = {
                "type": "Catalog",
                "stac_version": collection.get("stac_version", "1.1.0"),
                "id": catalog_id,
                "title": title,
                "description": args.description,
                "links": [
                    {"rel": "self", "href": catalog_href, "type": "application/json"},
                    {"rel": "root", "href": catalog_href, "type": "application/json"},
                    {"rel": "child", "href": child_href, "type": "application/json"},
                ],
            }

            local_catalog = temp_root / "catalog.json"
            with local_catalog.open("w", encoding="utf-8") as f:
                json.dump(catalog, f, indent=2)
            s3.upload_file(str(local_catalog), bucket, output_key)

            if args.update_collection_links:
                links = collection.setdefault("links", [])
                upsert_link(links, "root", catalog_href, "application/json")
                upsert_link(links, "parent", catalog_href, "application/json")
                with local_collection.open("w", encoding="utf-8") as f:
                    json.dump(collection, f, indent=2)
                s3.upload_file(str(local_collection), bucket, collection_key)

            print(f"Wrote catalog: {catalog_href}")
            if args.update_collection_links:
                print(f"Updated collection links: {s3_uri(bucket, collection_key)}")
        return

    collection_path = args.collection.resolve()
    if not collection_path.exists():
        raise FileNotFoundError(f"Collection not found: {collection_path}")

    with collection_path.open("r", encoding="utf-8") as f:
        collection = json.load(f)

    if collection.get("type") != "Collection":
        raise ValueError("Input file is not a STAC Collection")

    output_path = args.output.resolve() if args.output else (collection_path.parent.parent / "catalog.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    catalog_id = args.catalog_id or output_path.parent.name
    title = args.title or catalog_id.replace("-", " ").replace("_", " ").title()
    child_href = Path(os.path.relpath(collection_path, output_path.parent)).as_posix()

    catalog = {
        "type": "Catalog",
        "stac_version": collection.get("stac_version", "1.1.0"),
        "id": catalog_id,
        "title": title,
        "description": args.description,
        "links": [
            {"rel": "self", "href": "catalog.json", "type": "application/json"},
            {"rel": "root", "href": "catalog.json", "type": "application/json"},
            {"rel": "child", "href": child_href, "type": "application/json"},
        ],
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)

    if args.update_collection_links:
        href_from_collection = Path(os.path.relpath(output_path, collection_path.parent)).as_posix()
        links = collection.setdefault("links", [])
        upsert_link(links, "root", href_from_collection, "application/json")
        upsert_link(links, "parent", href_from_collection, "application/json")
        with collection_path.open("w", encoding="utf-8") as f:
            json.dump(collection, f, indent=2)

    print(f"Wrote catalog: {output_path}")
    if args.update_collection_links:
        print(f"Updated collection links: {collection_path}")


if __name__ == "__main__":
    main()
