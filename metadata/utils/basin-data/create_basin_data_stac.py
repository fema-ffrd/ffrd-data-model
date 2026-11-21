#!/usr/bin/env python3
"""Create a STAC Collection and Items from geospatial zip archives in an S3 prefix.

Design goals:
- Remote-first processing using S3 and GDAL VSI paths.
- Two-pass zip handling: list members first, then read geospatial metadata.
- Explicit, fail-fast errors with clear messages.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import zipfile

import boto3
import pystac
import s3fs
from pyproj import CRS, Transformer

VERSION_EXTENSION = "https://stac-extensions.github.io/version/v1.2.0/schema.json"
PROJECTION_EXTENSION = "https://stac-extensions.github.io/projection/v2.0.0/schema.json"
EXTENSIONS = [VERSION_EXTENSION, PROJECTION_EXTENSION]


@dataclass(frozen=True)
class S3Uri:
    bucket: str
    key: str


@dataclass(frozen=True)
class LayerSummary:
    name: str
    geometry_type: str


@dataclass(frozen=True)
class ExtentSummary:
    minx: float
    miny: float
    maxx: float
    maxy: float
    wkt: str


class CliError(RuntimeError):
    """Raised for intentional fail-fast CLI errors."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a STAC Collection from an S3 prefix with one STAC Item per zip file."
        )
    )
    parser.add_argument(
        "s3_prefix",
        help="Input S3 prefix (for example s3://south-platte/basin-data/transportation/)",
    )
    parser.add_argument(
        "--output",
        help="Local output folder or s3:// output prefix for collection and items",
    )
    parser.add_argument(
        "--output-root",
        help=(
            "Root output prefix used to mirror input structure, for example "
            "s3://south-platte/stac-metadata/basin-data/"
        ),
    )
    parser.add_argument(
        "--mirror-anchor",
        default="basin-data",
        help=(
            "Anchor segment in input prefix used to preserve relative structure "
            "when --output-root is set (default: basin-data)"
        ),
    )
    parser.add_argument(
        "--collection-id",
        help="STAC Collection ID (default: derived from prefix)",
    )
    parser.add_argument(
        "--item-path",
        default="items",
        help="Subdirectory under output where item JSON files are written (default: items)",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip PySTAC validation",
    )
    args = parser.parse_args()
    if bool(args.output) == bool(args.output_root):
        parser.error("Specify exactly one of --output or --output-root")
    return args


def parse_s3_uri(uri: str) -> S3Uri:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise CliError(f"Expected s3:// URI, got: {uri}")
    key = parsed.path.lstrip("/")
    if not key:
        raise CliError(f"S3 URI must include a key/prefix path: {uri}")
    return S3Uri(bucket=parsed.netloc, key=key)


def to_s3_uri(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def list_prefix_objects(s3_client, prefix_uri: str) -> list[dict[str, Any]]:
    prefix = parse_s3_uri(prefix_uri)
    key_prefix = prefix.key if prefix.key.endswith("/") else f"{prefix.key}/"

    paginator = s3_client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=prefix.bucket, Prefix=key_prefix)
    objects: list[dict[str, Any]] = []
    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            objects.append(obj)

    if not objects:
        raise CliError(f"No objects found under prefix: {prefix_uri}")
    return objects


def list_zip_members(bucket: str, key: str) -> list[str]:
    s3 = s3fs.S3FileSystem(anon=False)
    full_key = f"{bucket}/{key}"
    try:
        with s3.open(full_key, "rb") as fobj:
            with zipfile.ZipFile(fobj) as zf:
                return zf.namelist()
    except Exception as exc:  # explicit conversion to clear context
        raise CliError(
            f"Failed to list zip members for s3://{full_key}: {exc}"
        ) from exc


def infer_dataset_path(members: list[str], zip_stem: str) -> str:
    lower = {m.lower(): m for m in members}

    preferred_gdb = f"{zip_stem.lower()}.gdb/"
    for member_lc, original in lower.items():
        if member_lc.startswith(preferred_gdb):
            return original.split("/")[0]

    for member in members:
        if ".gdb/" in member.lower():
            return member[: member.lower().index(".gdb/") + 4]

    for member in members:
        if member.lower().endswith(".gpkg"):
            return member

    for member in members:
        if member.lower().endswith(".shp"):
            return member

    raise CliError("Could not infer geospatial dataset in zip")


def build_datasource_path(bucket: str, key: str, inner_dataset: str) -> str:
    root = f"/vsizip//vsis3/{bucket}/{key}"
    if not inner_dataset:
        return root
    cleaned = inner_dataset.strip("/")
    return f"{root}/{cleaned}"


def run_ogrinfo(args: list[str]) -> str:
    cmd = ["ogrinfo", "-ro", "-so", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        details = stderr if stderr else stdout
        raise CliError(f"ogrinfo failed ({' '.join(cmd)}): {details}")
    return proc.stdout


def parse_layer_list(summary_text: str) -> list[LayerSummary]:
    layers: list[LayerSummary] = []
    for line in summary_text.splitlines():
        match = re.match(r"^\s*\d+:\s+(.+?)\s+\((.*)\)\s*$", line)
        if not match:
            continue
        layers.append(LayerSummary(name=match.group(1), geometry_type=match.group(2)))
    return layers


def parse_extent(summary_text: str) -> ExtentSummary:
    extent_match = re.search(
        r"Extent:\s*\(([-0-9.eE+]+),\s*([-0-9.eE+]+)\)\s*-\s*\(([-0-9.eE+]+),\s*([-0-9.eE+]+)\)",
        summary_text,
    )
    if not extent_match:
        raise CliError("Could not parse layer extent from ogrinfo output")

    wkt = parse_wkt(summary_text)

    return ExtentSummary(
        minx=float(extent_match.group(1)),
        miny=float(extent_match.group(2)),
        maxx=float(extent_match.group(3)),
        maxy=float(extent_match.group(4)),
        wkt=wkt,
    )


def parse_wkt(summary_text: str) -> str:
    wkt_match = re.search(
        r"Layer SRS WKT:\n(.*?)(?:\nData axis to CRS axis mapping:|\nFID Column =|\nGeometry Column =|\n[A-Za-z0-9_]+:\s|\Z)",
        summary_text,
        flags=re.DOTALL,
    )
    if not wkt_match:
        raise CliError("Could not parse layer CRS WKT from ogrinfo output")
    return wkt_match.group(1).strip()


def bbox_to_epsg4326(extent: ExtentSummary) -> list[float]:
    src = CRS.from_wkt(extent.wkt)
    dst = CRS.from_epsg(4326)
    if src == dst:
        return [extent.minx, extent.miny, extent.maxx, extent.maxy]

    transformer = Transformer.from_crs(src, dst, always_xy=True)
    corners = [
        transformer.transform(extent.minx, extent.miny),
        transformer.transform(extent.minx, extent.maxy),
        transformer.transform(extent.maxx, extent.miny),
        transformer.transform(extent.maxx, extent.maxy),
    ]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    return [min(xs), min(ys), max(xs), max(ys)]


def bbox_to_polygon(bbox: list[float]) -> dict[str, Any]:
    minx, miny, maxx, maxy = bbox
    ring = [
        [minx, miny],
        [maxx, miny],
        [maxx, maxy],
        [minx, maxy],
        [minx, miny],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def attach_item_extensions(item: pystac.Item) -> None:
    existing = list(item.stac_extensions or [])
    item.stac_extensions = sorted(set(existing + EXTENSIONS))

    item.properties["version"] = "1.0"
    item.properties["deprecated"] = False

    item.properties["proj:epsg"] = 4326
    item.properties["proj:wkt2"] = CRS.from_epsg(4326).to_wkt()
    item.properties["proj:bbox"] = item.bbox
    item.properties["proj:geometry"] = item.geometry


def attach_collection_extensions(collection: pystac.Collection) -> None:
    existing = list(collection.stac_extensions or [])
    collection.stac_extensions = sorted(set(existing + EXTENSIONS))

    collection.extra_fields["version"] = "1.0"
    collection.extra_fields["deprecated"] = False

    collection.summaries = pystac.Summaries({"proj:epsg": [4326]})


def media_type_for_key(key: str) -> str:
    lowered = key.lower()
    if lowered.endswith(".zip"):
        return "application/zip"
    guessed, _ = mimetypes.guess_type(key)
    return guessed or "application/octet-stream"


def join_output(output: str, relative: str) -> str:
    if output.startswith("s3://"):
        return f"{output.rstrip('/')}/{relative.lstrip('/')}"
    return str((Path(output).expanduser().resolve() / relative).as_posix())


def mirror_output_prefix(input_prefix: str, output_root: str, anchor: str) -> str:
    if not output_root.startswith("s3://"):
        raise CliError("--output-root must be an s3:// URI")

    source = parse_s3_uri(input_prefix)
    parts = [part for part in source.key.strip("/").split("/") if part]
    if not parts:
        raise CliError(f"Cannot mirror empty input prefix path: {input_prefix}")

    try:
        anchor_index = parts.index(anchor)
    except ValueError as exc:
        raise CliError(
            f"Input prefix does not contain mirror anchor '{anchor}': {input_prefix}"
        ) from exc

    suffix_parts = parts[anchor_index + 1 :]
    suffix = "/".join(suffix_parts)
    if suffix:
        return f"{output_root.rstrip('/')}/{suffix}/"
    return output_root.rstrip("/") + "/"


def write_json(location: str, document: dict[str, Any], s3_client) -> None:
    data = json.dumps(document, indent=2).encode("utf-8")
    if location.startswith("s3://"):
        uri = parse_s3_uri(location)
        s3_client.put_object(
            Bucket=uri.bucket,
            Key=uri.key,
            Body=data,
            ContentType="application/geo+json",
        )
        return

    path = Path(location)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def force_relative_item_links(
    document: dict[str, Any], item_path: str
) -> dict[str, Any]:
    item_id = document.get("id")
    if not item_id:
        raise CliError("Item document is missing required id")

    rel_self = f"{item_path.strip('/')}/{item_id}.json"
    rel_collection = "../collection.json"

    links = document.get("links", [])
    if not isinstance(links, list):
        raise CliError("Item document links must be a list")

    rel_map = {
        "self": rel_self,
        "root": rel_collection,
        "parent": rel_collection,
        "collection": rel_collection,
    }
    latest_version_seen = False
    for link in links:
        if not isinstance(link, dict):
            continue
        rel = link.get("rel")
        if rel in rel_map:
            link["href"] = rel_map[rel]
        if rel == "latest-version":
            link["href"] = rel_self
            link.setdefault("type", "application/geo+json")
            latest_version_seen = True

    if not latest_version_seen:
        links.append(
            {
                "rel": "latest-version",
                "href": rel_self,
                "type": "application/geo+json",
            }
        )
    document["links"] = links
    return document


def force_relative_collection_links(document: dict[str, Any]) -> dict[str, Any]:
    links = document.get("links", [])
    if not isinstance(links, list):
        raise CliError("Collection document links must be a list")

    for link in links:
        if not isinstance(link, dict):
            continue
        rel = link.get("rel")
        if rel == "self":
            link["href"] = "collection.json"
        elif rel == "item":
            href = link.get("href")
            if isinstance(href, str) and "/items/" in href:
                link["href"] = href[href.index("items/") :]
    document["links"] = links
    return document


def collection_id_from_prefix(prefix_uri: str) -> str:
    parsed = parse_s3_uri(prefix_uri)
    tail = parsed.key.rstrip("/").split("/")[-1]
    if not tail:
        raise CliError(f"Cannot infer collection id from prefix: {prefix_uri}")
    return tail


def summarize_shapefile(datasource: str, layer_name: str) -> dict[str, Any]:
    text = run_ogrinfo([datasource, layer_name])

    row_match = re.search(r"Feature Count:\s*(\d+)", text)
    geom_match = re.search(r"Geometry:\s*(.+)", text)

    fields: list[str] = []
    for line in text.splitlines():
        field_match = re.match(r"^([A-Za-z0-9_]+):\s+", line)
        if field_match:
            fields.append(field_match.group(1))

    projection = parse_wkt(text)

    if row_match is None or geom_match is None:
        raise CliError(f"Could not parse shapefile summary for layer: {layer_name}")

    return {
        "layer": layer_name,
        "columns": fields,
        "row_count": int(row_match.group(1)),
        "geometry_type": geom_match.group(1).strip(),
        "projection_wkt": projection,
    }


def summarize_dataset(
    bucket: str, key: str, inner_dataset: str
) -> tuple[list[float], dict[str, Any]]:
    datasource = build_datasource_path(bucket, key, inner_dataset)
    layer_text = run_ogrinfo([datasource])
    layers = parse_layer_list(layer_text)
    if not layers:
        raise CliError(f"No layers discovered in datasource: {datasource}")

    geom_layers = [l for l in layers if l.geometry_type and l.geometry_type != "None"]
    if not geom_layers:
        raise CliError(
            f"No geometry-bearing layers discovered in datasource: {datasource}"
        )

    extent: ExtentSummary | None = None
    extent_source_layer: str | None = None
    layer_extent_errors: list[str] = []
    for layer in geom_layers:
        layer_text = run_ogrinfo([datasource, layer.name])
        try:
            extent = parse_extent(layer_text)
            extent_source_layer = layer.name
            break
        except CliError as exc:
            layer_extent_errors.append(f"{layer.name}: {exc}")

    if extent is None or extent_source_layer is None:
        raise CliError(
            "Could not parse layer extent from any geometry layer. "
            f"Tried {len(geom_layers)} layers: {'; '.join(layer_extent_errors)}"
        )

    bbox_4326 = bbox_to_epsg4326(extent)

    details: dict[str, Any] = {
        "geospatial_dataset": {
            "inner_path": inner_dataset,
            "bbox_source_layer": extent_source_layer,
            "layer_count": len(layers),
            "layers": [
                {"name": l.name, "geometry_type": l.geometry_type} for l in layers
            ],
        }
    }

    lowered = inner_dataset.lower()
    if lowered.endswith(".shp"):
        details["shapefile_summary"] = summarize_shapefile(
            datasource, extent_source_layer
        )
    if lowered.endswith(".gdb") or lowered.endswith(".gpkg"):
        details["table_summary"] = {
            "table_names": [l.name for l in layers],
            "table_count": len(layers),
        }

    return bbox_4326, details


def build_collection_assets(
    all_objects: list[dict[str, Any]], prefix_uri: str
) -> dict[str, dict[str, Any]]:
    prefix = parse_s3_uri(prefix_uri)
    key_prefix = prefix.key if prefix.key.endswith("/") else f"{prefix.key}/"

    assets: dict[str, dict[str, Any]] = {}
    for obj in all_objects:
        key = obj["Key"]
        if not key.startswith(key_prefix):
            continue
        name = key[len(key_prefix) :]
        if not name:
            continue
        if name.lower().endswith(".zip"):
            continue
        if name.lower().endswith("stac.json"):
            continue
        asset_key = name.replace("/", "_")
        assets[asset_key] = {
            "href": to_s3_uri(prefix.bucket, key),
            "type": media_type_for_key(key),
            "roles": ["data"],
            "title": name,
            "file:size": obj.get("Size"),
        }
    return assets


def build_zip_asset(prefix: S3Uri, zip_obj: dict[str, Any]) -> dict[str, Any]:
    zip_key = zip_obj["Key"]
    return {
        "href": to_s3_uri(prefix.bucket, zip_key),
        "type": media_type_for_key(zip_key),
        "roles": ["data"],
        "title": Path(zip_key).name,
        "file:size": zip_obj.get("Size"),
    }


def build_item(
    zip_obj: dict[str, Any],
    prefix_uri: str,
) -> pystac.Item:
    prefix = parse_s3_uri(prefix_uri)
    zip_key = zip_obj["Key"]
    zip_name = Path(zip_key).name
    zip_stem = Path(zip_name).stem

    zip_members = list_zip_members(prefix.bucket, zip_key)
    if not zip_members:
        raise CliError(f"Zip archive has no members: s3://{prefix.bucket}/{zip_key}")

    inner_dataset = infer_dataset_path(zip_members, zip_stem)

    bbox, details = summarize_dataset(prefix.bucket, zip_key, inner_dataset)
    geom = bbox_to_polygon(bbox)

    item_id = re.sub(r"[^A-Za-z0-9._-]+", "-", zip_stem).strip("-").lower()
    if not item_id:
        raise CliError(f"Could not derive valid item id from zip name: {zip_name}")

    item_datetime = zip_obj.get("LastModified")
    if item_datetime is None:
        item_datetime = datetime.now(timezone.utc)

    zip_asset_key = zip_name.replace("/", "_")
    zip_asset = build_zip_asset(prefix, zip_obj)
    details["asset"] = {
        "key": zip_asset_key,
        "name": zip_name,
        "href": zip_asset["href"],
    }

    item = pystac.Item(
        id=item_id,
        geometry=geom,
        bbox=bbox,
        datetime=item_datetime,
        properties={
            "title": zip_name,
            "source_prefix": prefix_uri,
            "zip_member_count": len(zip_members),
            "zip:asset_name": zip_name,
            "zip:analysis": details,
        },
    )
    attach_item_extensions(item)

    item.add_asset(zip_asset_key, pystac.Asset.from_dict(zip_asset))

    return item


def build_collection(
    collection_id: str,
    prefix_uri: str,
    all_objects: list[dict[str, Any]],
    items: list[pystac.Item],
    output: str,
    item_path: str,
) -> tuple[pystac.Collection, list[tuple[pystac.Item, str]], str]:
    if not items:
        raise CliError("Cannot build collection with no items")

    overall_bbox = [
        min(i.bbox[0] for i in items),
        min(i.bbox[1] for i in items),
        max(i.bbox[2] for i in items),
        max(i.bbox[3] for i in items),
    ]

    starts = [i.datetime for i in items if i.datetime is not None]
    if not starts:
        raise CliError("All items are missing datetime")

    collection = pystac.Collection(
        id=collection_id,
        description=f"Basin data collection generated from {prefix_uri}",
        extent=pystac.Extent(
            pystac.SpatialExtent([overall_bbox]),
            pystac.TemporalExtent([[min(starts), max(starts)]]),
        ),
        license="proprietary",
        title=collection_id,
    )
    attach_collection_extensions(collection)
    collection.extra_fields["source_prefix"] = prefix_uri
    collection.extra_fields["created"] = now_iso()

    collection_assets = build_collection_assets(all_objects, prefix_uri)
    for asset_key, asset in collection_assets.items():
        collection.add_asset(asset_key, pystac.Asset.from_dict(asset))

    item_locations: list[tuple[pystac.Item, str]] = []
    for item in items:
        rel = f"{item_path.strip('/')}/{item.id}.json"
        loc = join_output(output, rel)
        item.set_self_href(rel)
        collection.add_item(item)
        item_locations.append((item, loc))

    collection_loc = join_output(output, "collection.json")
    collection.set_self_href("collection.json")
    return collection, item_locations, collection_loc


def main() -> None:
    args = parse_args()

    if not args.s3_prefix.startswith("s3://"):
        raise CliError("Input prefix must be an s3:// URI")

    output_location_root = args.output
    if args.output_root:
        output_location_root = mirror_output_prefix(
            input_prefix=args.s3_prefix,
            output_root=args.output_root,
            anchor=args.mirror_anchor,
        )

    if output_location_root is None:
        raise CliError("Internal error: output location was not resolved")

    session = boto3.Session()
    s3_client = session.client("s3")

    objects = list_prefix_objects(s3_client, args.s3_prefix)
    zip_objects = [o for o in objects if o["Key"].lower().endswith(".zip")]
    if not zip_objects:
        raise CliError(
            "No zip files found in prefix; cannot build one-item-per-zip STAC"
        )

    collection_id = args.collection_id or collection_id_from_prefix(args.s3_prefix)

    items: list[pystac.Item] = []
    for zip_obj in sorted(zip_objects, key=lambda o: o["Key"]):
        item = build_item(zip_obj, args.s3_prefix)
        if not args.no_validate:
            # Validate each item before it is attached to a collection/root link.
            pystac.Item.from_dict(item.to_dict(include_self_link=False)).validate()
        items.append(item)

    collection, item_locations, collection_location = build_collection(
        collection_id=collection_id,
        prefix_uri=args.s3_prefix,
        all_objects=objects,
        items=items,
        output=output_location_root,
        item_path=args.item_path,
    )

    for item, location in item_locations:
        doc = item.to_dict(include_self_link=True)
        doc = force_relative_item_links(doc, args.item_path)
        write_json(location, doc, s3_client)

    collection_doc = collection.to_dict(include_self_link=True)
    collection_doc = force_relative_collection_links(collection_doc)
    if not args.no_validate and not output_location_root.startswith("s3://"):
        pystac.Collection.from_dict(collection_doc).validate()
    write_json(collection_location, collection_doc, s3_client)

    print(f"Wrote collection: {collection_location}")
    print(f"Items written: {len(item_locations)}")
    print(f"Output root: {output_location_root}")


if __name__ == "__main__":
    main()
