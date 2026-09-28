#!/usr/bin/env python3
"""Create a standalone STAC collection with a GeoParquet item archive.

This utility reads a source catalog and collection from local paths or S3 URIs,
loads all item links from the collection, writes a STAC GeoParquet file, and
emits a standalone collection copy that references the parquet as a collection
asset.
"""

from __future__ import annotations

import argparse
import copy
import inspect
import json
import os
import posixpath
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError
import pystac
import stac_geoparquet.arrow as sgpa

PARQUET_MEDIA_TYPE = "application/vnd.apache.parquet"
SUPPORTED_SCHEMA_VERSIONS = ("1.0.0", "1.1.0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a standalone portable STAC collection with a "
            "GeoParquet item asset."
        )
    )
    parser.add_argument(
        "catalog",
        help="Local path or s3:// URI for the source STAC catalog.json",
    )
    parser.add_argument(
        "collection",
        help=(
            "Collection ID to resolve from catalog child links, or collection "
            "href relative to catalog"
        ),
    )
    parser.add_argument(
        "--output",
        help=(
            "Output folder or s3:// prefix for the parquet item archive. "
            "The portable collection JSON is always written beside the source "
            "collection.json"
        ),
    )
    parser.add_argument(
        "--parquet-name",
        help="Parquet filename in the portable bundle (default: <collection-id>-<version>.parquet)",
    )
    parser.add_argument(
        "--asset-key",
        default="items-geoparquet",
        help="Collection asset key to use for the parquet asset",
    )
    parser.add_argument(
        "--schema-version",
        choices=SUPPORTED_SCHEMA_VERSIONS,
        default="1.1.0",
        help="GeoParquet schema version (default: 1.1.0)",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip PySTAC validation for the output catalog and collection",
    )
    return parser.parse_args()


def configure_aws_environment(session: boto3.Session) -> None:
    """Expose boto3 credentials to libraries that read/write S3."""
    credentials = session.get_credentials()
    if credentials is not None:
        frozen = credentials.get_frozen_credentials()
        os.environ["AWS_ACCESS_KEY_ID"] = frozen.access_key
        os.environ["AWS_SECRET_ACCESS_KEY"] = frozen.secret_key
        if frozen.token:
            os.environ["AWS_SESSION_TOKEN"] = frozen.token

    region = session.region_name or "us-east-1"
    os.environ.setdefault("AWS_REGION", region)
    os.environ.setdefault("AWS_DEFAULT_REGION", region)


def is_s3_uri(location: str) -> bool:
    return location.startswith("s3://")


def parse_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    return parsed.netloc, parsed.path.lstrip("/")


def is_missing_s3_object(error: ClientError) -> bool:
    code = error.response.get("Error", {}).get("Code", "")
    return code in {"NoSuchKey", "404", "NotFound"}


def read_text(location: str, s3_client) -> str:
    if is_s3_uri(location):
        bucket, key = parse_s3_uri(location)
        return (
            s3_client.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
        )
    return Path(location).read_text(encoding="utf-8")


def read_json(location: str, s3_client) -> dict:
    return json.loads(read_text(location, s3_client))


def write_json(location: str, document: dict, s3_client) -> None:
    body = json.dumps(document, indent=2).encode("utf-8")
    if is_s3_uri(location):
        bucket, key = parse_s3_uri(location)
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
        return

    path = Path(location)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def join_location(base_file: str, href: str) -> str:
    if not href:
        raise ValueError("Link href is empty")
    if href.startswith(("s3://", "http://", "https://")):
        return href

    if is_s3_uri(base_file):
        parsed = urlparse(base_file)
        parent = posixpath.dirname(parsed.path.lstrip("/"))
        key = posixpath.normpath(posixpath.join(parent, href))
        return f"s3://{parsed.netloc}/{key}"

    candidate = Path(href)
    if candidate.is_absolute() and candidate.exists():
        return str(candidate)
    return str((Path(base_file).resolve().parent / href).resolve())


def is_collection_reference(value: str) -> bool:
    return value.endswith(".json") or "/" in value or value.startswith(".")


def resolve_collection_location(
    catalog_location: str, catalog: dict, collection_arg: str, s3_client
) -> str:
    if collection_arg.startswith("s3://"):
        return collection_arg

    if is_collection_reference(collection_arg):
        return join_location(catalog_location, collection_arg)

    # Treat the input as a collection ID and resolve through catalog child links.
    for link in catalog.get("links", []):
        if link.get("rel") != "child":
            continue
        href = link.get("href")
        if not href:
            continue
        location = join_location(catalog_location, href)
        try:
            child = read_json(location, s3_client)
        except FileNotFoundError:
            continue
        except ClientError as exc:
            if is_missing_s3_object(exc):
                continue
            raise
        if child.get("id") == collection_arg:
            return location

    raise ValueError(
        f"Could not resolve collection '{collection_arg}' from catalog child links"
    )


def resolve_item_locations(collection_location: str, collection: dict) -> list[str]:
    locations: list[str] = []
    for link in collection.get("links", []):
        if link.get("rel") != "item":
            continue
        href = link.get("href")
        if not href:
            continue
        locations.append(join_location(collection_location, href))
    return locations


def upload_file_to_s3(local_path: Path, destination_uri: str, s3_client) -> None:
    bucket, key = parse_s3_uri(destination_uri)
    s3_client.upload_file(str(local_path), bucket, key)


def write_geoparquet(
    items: list[dict],
    collection: dict,
    destination: str,
    schema_version: str,
    s3_client,
) -> None:
    collections_metadata = {collection["id"]: collection}

    # PyArrow cannot write struct columns with zero children. Some hecstac
    # properties use empty dicts (for example HEC-RAS:breach_locations), so
    # convert empty objects to null before Arrow conversion.
    def _sanitize_value(value):
        if isinstance(value, dict):
            if not value:
                return None
            return {k: _sanitize_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_sanitize_value(v) for v in value]
        return value

    sanitized_items = [_sanitize_value(item) for item in items]
    arrow_batches = sgpa.parse_stac_items_to_arrow(sanitized_items)

    # stac-geoparquet API support differs by version. Newer releases accept
    # collections metadata kwargs while older ones pass unknown kwargs straight
    # to pyarrow and fail. Try supported options and fall back to no metadata.
    signature = inspect.signature(sgpa.to_parquet)
    parameter_names = set(signature.parameters)
    kwargs_variants: list[dict] = []
    if "collections" in parameter_names:
        kwargs_variants.append({"collections": collections_metadata})
    if "collection_metadata" in parameter_names:
        kwargs_variants.append({"collection_metadata": collection})
    kwargs_variants.append({})

    def _write_to_path(output_path: Path) -> None:
        last_error: TypeError | None = None
        for extra_kwargs in kwargs_variants:
            try:
                sgpa.to_parquet(
                    arrow_batches,
                    output_path=output_path,
                    schema_version=schema_version,
                    **extra_kwargs,
                )
                return
            except TypeError as exc:
                # Retry with fewer kwargs for older stac-geoparquet builds.
                last_error = exc
        assert last_error is not None
        raise last_error

    if is_s3_uri(destination):
        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / Path(destination).name
            _write_to_path(local_path)
            upload_file_to_s3(local_path, destination, s3_client)
        return

    local_output = Path(destination)
    local_output.parent.mkdir(parents=True, exist_ok=True)
    _write_to_path(local_output)


def output_location(output: str, filename: str) -> str:
    if is_s3_uri(output):
        return f"{output.rstrip('/')}/{filename}"
    return str(Path(output).expanduser().resolve() / filename)


def mirrored_output_location(
    output_root: str,
    catalog_location: str,
    collection_location: str,
    filename: str,
) -> str:
    """Mirror collection subpath under a new root output location.

    The mirrored directory is computed from the collection parent directory
    relative to the catalog parent directory.
    """
    if (
        is_s3_uri(output_root)
        and is_s3_uri(catalog_location)
        and is_s3_uri(collection_location)
    ):
        out_bucket, out_prefix = parse_s3_uri(output_root)
        _, catalog_key = parse_s3_uri(catalog_location)
        _, collection_key = parse_s3_uri(collection_location)

        catalog_dir = posixpath.dirname(catalog_key)
        collection_dir = posixpath.dirname(collection_key)
        rel_dir = posixpath.relpath(collection_dir, catalog_dir)

        root_prefix = posixpath.normpath(out_prefix) if out_prefix else ""
        if rel_dir == ".":
            target_dir = root_prefix
        elif root_prefix:
            target_dir = posixpath.join(root_prefix, rel_dir)
        else:
            target_dir = rel_dir

        key = posixpath.join(target_dir, filename) if target_dir else filename
        return f"s3://{out_bucket}/{key}"

    if (
        not is_s3_uri(output_root)
        and not is_s3_uri(catalog_location)
        and not is_s3_uri(collection_location)
    ):
        root = Path(output_root).expanduser().resolve()
        catalog_dir = Path(catalog_location).resolve().parent
        collection_dir = Path(collection_location).resolve().parent
        rel_dir = Path(os.path.relpath(collection_dir, catalog_dir))
        target = root if str(rel_dir) == "." else root / rel_dir
        return str(target / filename)

    return output_location(output_root, filename)


def sibling_location(file_location: str, filename: str) -> str:
    """Build a path/URI for a file beside another file."""
    if is_s3_uri(file_location):
        bucket, key = parse_s3_uri(file_location)
        parent = posixpath.dirname(key)
        return f"s3://{bucket}/{parent}/{filename}"
    return str(Path(file_location).resolve().parent / filename)


def collection_version(collection: dict) -> str:
    """Return collection version and fail when absent or blank."""
    version = collection.get("version")
    if not isinstance(version, str) or not version.strip():
        collection_id = collection.get("id", "<unknown>")
        raise ValueError(
            f"Collection {collection_id} must include a non-empty top-level 'version'"
        )
    return version.strip()


def build_portable_collection(
    source_collection: dict,
    parquet_name: str,
    collection_filename: str,
    asset_key: str,
    schema_version: str,
    parquet_href: str,
) -> dict:
    collection = copy.deepcopy(source_collection)

    retained_links = []
    for link in collection.get("links", []):
        rel = link.get("rel")
        if rel in {"item", "self", "root", "parent"}:
            continue
        retained_links.append(link)

    retained_links.extend(
        [
            {
                "rel": "root",
                "href": f"./{collection_filename}",
                "type": "application/json",
            },
            {
                "rel": "self",
                "href": f"./{collection_filename}",
                "type": "application/json",
            },
            {
                "rel": "alternate",
                "href": parquet_href,
                "type": PARQUET_MEDIA_TYPE,
                "title": f"{collection['id']} STAC GeoParquet",
            },
        ]
    )
    collection["links"] = retained_links

    assets = collection.setdefault("assets", {})
    assets[asset_key] = {
        "href": parquet_href,
        "type": PARQUET_MEDIA_TYPE,
        "roles": ["collection-mirror"],
        "title": f"{collection['id']} STAC Items (GeoParquet)",
        "description": (
            "Standalone GeoParquet archive of all Items referenced by this "
            "collection, encoded with STAC GeoParquet metadata."
        ),
        "stac_geoparquet:version": schema_version,
    }
    return collection


def main() -> None:
    args = parse_args()

    session = boto3.Session()
    configure_aws_environment(session)
    s3_client = session.client("s3")

    catalog_location = args.catalog
    catalog = read_json(catalog_location, s3_client)

    collection_location = resolve_collection_location(
        catalog_location, catalog, args.collection, s3_client
    )
    source_collection = read_json(collection_location, s3_client)

    item_locations = resolve_item_locations(collection_location, source_collection)
    if not item_locations:
        raise ValueError(
            f"Collection {source_collection.get('id', '<unknown>')} has no item links"
        )
    items = [read_json(location, s3_client) for location in item_locations]

    collection_id = source_collection["id"]
    version = collection_version(source_collection)
    parquet_name = args.parquet_name or f"{collection_id}-{version}.parquet"
    collection_filename = f"collection-{version}.json"

    if args.output:
        parquet_location = mirrored_output_location(
            output_root=args.output,
            catalog_location=catalog_location,
            collection_location=collection_location,
            filename=parquet_name,
        )
        collection_out = mirrored_output_location(
            output_root=args.output,
            catalog_location=catalog_location,
            collection_location=collection_location,
            filename=collection_filename,
        )
        parquet_href = f"./{parquet_name}"
    else:
        parquet_location = sibling_location(collection_location, parquet_name)
        collection_out = sibling_location(collection_location, collection_filename)
        parquet_href = f"./{parquet_name}"

    write_geoparquet(
        items=items,
        collection=source_collection,
        destination=parquet_location,
        schema_version=args.schema_version,
        s3_client=s3_client,
    )

    portable_collection = build_portable_collection(
        source_collection,
        parquet_name=parquet_name,
        collection_filename=collection_filename,
        asset_key=args.asset_key,
        schema_version=args.schema_version,
        parquet_href=parquet_href,
    )

    if not args.no_validate:
        # Use schema-only validation without link dereferencing. Object-based
        # validation can try to resolve s3:// links via urllib.
        pystac.validation.validate_dict(
            portable_collection, pystac.STACObjectType.COLLECTION
        )

    write_json(collection_out, portable_collection, s3_client)

    print(f"Wrote {parquet_location}")
    print(f"Wrote {collection_out}")
    print(f"Portable collection contains {len(items)} items in GeoParquet")


if __name__ == "__main__":
    main()
