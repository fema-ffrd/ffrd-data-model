#!/usr/bin/env python3
"""Add a derived Parquet asset and version metadata to a STAC Item."""

from __future__ import annotations

import argparse
import json
from pathlib import PurePosixPath

import boto3
import pystac

from stac_utils import configure_aws_environment, read_text, write_document

PARQUET_MEDIA_TYPE = "application/vnd.apache.parquet"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add a DSS-derived Parquet asset to an existing STAC Item."
    )
    parser.add_argument(
        "--item", required=True, help="Local path or s3:// URI of the source STAC Item"
    )
    parser.add_argument(
        "--output",
        help="Destination Item path or URI (default: update --item in place)",
    )
    parser.add_argument("--source-dss", required=True, help="Source DSS asset URI")
    parser.add_argument("--parquet", required=True, help="Derived Parquet asset URI")
    parser.add_argument(
        "--version", required=True, help="Item version, for example v1.1"
    )
    parser.add_argument(
        "--no-validate", action="store_true", help="Skip PySTAC validation"
    )
    return parser.parse_args()


def update_item(
    document: dict, source_dss: str, parquet: str, version: str, destination: str
) -> dict:
    assets = document.setdefault("assets", {})
    if not any(asset.get("href") == source_dss for asset in assets.values()):
        raise ValueError(f"Source DSS is not an asset of the STAC Item: {source_dss}")

    asset_key = f"lakehouse-outputs/{PurePosixPath(parquet).name}"
    assets[asset_key] = {
        "href": parquet,
        "type": PARQUET_MEDIA_TYPE,
        "title": PurePosixPath(parquet).name,
        "roles": ["data"],
        "description": "Apache Parquet time series derived from the HEC-DSS source asset.",
        "hecstac:relative_path": asset_key,
        "hecstac:source_asset": source_dss,
    }

    properties = document.setdefault("properties", {})
    properties["version"] = version
    properties["hecstac:asset_count"] = len(assets)

    self_links = [
        link for link in document.setdefault("links", []) if link.get("rel") == "self"
    ]
    if self_links:
        for link in self_links:
            link["href"] = destination
    else:
        document["links"].append(
            {"rel": "self", "href": destination, "type": "application/geo+json"}
        )
    return document


def main() -> None:
    args = parse_args()
    destination = args.output or args.item
    session = boto3.Session()
    configure_aws_environment(session)
    s3_client = session.client("s3")

    document = json.loads(read_text(args.item, s3_client))
    update_item(document, args.source_dss, args.parquet, args.version, destination)
    if not args.no_validate:
        pystac.Item.from_dict(document).validate()
    write_document(destination, document, s3_client)
    print(f"Wrote {destination} with version {args.version}")


if __name__ == "__main__":
    main()
