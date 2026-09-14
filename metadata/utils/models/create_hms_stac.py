#!/usr/bin/env python3
"""Create a standalone STAC Item containing all inputs for an HEC-HMS model."""

from __future__ import annotations

import argparse
import re
from collections import OrderedDict
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import boto3
import pystac
from pyproj import CRS
from pystac import Asset
from pystac.extensions.projection import ProjectionExtension

import hecstac.hms.utils as hms_utils
from hecstac.hms.consts import ATTR_KEYVAL_GROUPER, ATTR_NESTED_KEYVAL_GROUPER
from hecstac.hms.item import HMSModelItem
from hecstac.ras.consts import NULL_DATETIME, NULL_STAC_BBOX, NULL_STAC_GEOMETRY

from stac_utils import (
    configure_aws_environment,
    output_location,
    resolve_crs,
    write_document,
)

# HEC-HMS-generated result artifacts are not model inputs. Everything else under
# the project directory is included so DSS data, terrain, GIS, and map support
# files are retained without relying on a fixed extension allowlist.
OUTPUT_DIRECTORIES = {"results"}
OUTPUT_SUFFIXES = {".animation", ".h5", ".log", ".out", ".results", ".tilecache"}

ASSET_METADATA = {
    ".hms": ("text/plain", ["metadata", "hms-project"], "HEC-HMS project file."),
    ".basin": ("text/plain", ["data", "hms-basin"], "HEC-HMS basin model definition."),
    ".control": (
        "text/plain",
        ["data", "hms-control"],
        "HEC-HMS simulation time control.",
    ),
    ".met": (
        "text/plain",
        ["data", "hms-met"],
        "HEC-HMS meteorological model definition.",
    ),
    ".run": ("text/plain", ["data", "hms-run"], "HEC-HMS simulation run definition."),
    ".gage": (
        "text/plain",
        ["data", "hms-gage"],
        "HEC-HMS time-series gage definitions.",
    ),
    ".grid": ("text/plain", ["data", "hms-grid"], "HEC-HMS grid data definitions."),
    ".pdata": ("text/plain", ["data", "hms-pdata"], "HEC-HMS paired data definitions."),
    ".terrain": (
        "text/plain",
        ["data", "hms-terrain"],
        "HEC-HMS terrain data definition.",
    ),
    ".dss": (
        "application/octet-stream",
        ["data", "hec-dss"],
        "HEC-DSS model input data.",
    ),
    ".sqlite": (
        "application/x-sqlite3",
        ["data", "hms-sqlite"],
        "SQLite spatial model data.",
    ),
    ".tif": (
        "image/tiff; application=geotiff",
        ["data", "hms-terrain"],
        "GeoTIFF terrain or grid input.",
    ),
    ".tiff": (
        "image/tiff; application=geotiff",
        ["data", "hms-terrain"],
        "GeoTIFF terrain or grid input.",
    ),
    ".shp": (
        "application/vnd.shp",
        ["data", "hms-gis"],
        "ESRI Shapefile geometry component.",
    ),
    ".dbf": (
        "application/x-dbf",
        ["data", "hms-gis"],
        "ESRI Shapefile attribute component.",
    ),
    ".shx": (
        "application/octet-stream",
        ["data", "hms-gis"],
        "ESRI Shapefile index component.",
    ),
    ".prj": (
        "text/plain",
        ["metadata", "projection"],
        "Coordinate reference system definition.",
    ),
    ".xml": (
        "application/xml",
        ["metadata", "hms-map"],
        "HEC-HMS map or raster metadata.",
    ),
    ".gdr": (
        "application/octet-stream",
        ["data", "hms-map"],
        "HEC-HMS gridded data record.",
    ),
    ".txt": ("text/plain", ["metadata"], "Supporting model documentation."),
    ".access": (
        "text/plain",
        ["metadata", "hms-access"],
        "HEC-HMS project access metadata.",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a STAC Item containing all input files for an HEC-HMS project."
    )
    parser.add_argument(
        "project", help="Local path or s3:// URI of the HEC-HMS .hms file"
    )
    parser.add_argument(
        "--output", required=True, help="Local output directory or s3:// output prefix"
    )
    parser.add_argument(
        "--projection",
        help="CRS text, or a local/S3 projection file containing WKT",
    )
    parser.add_argument(
        "--id", dest="item_id", help="STAC Item ID (default: project filename stem)"
    )
    parser.add_argument("--filename", help="Output filename (default: <item-id>.json)")
    parser.add_argument(
        "--no-simplify", action="store_true", help="Do not simplify the basin footprint"
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip PySTAC validation before writing",
    )
    return parser.parse_args()


def is_input(relative_path: str) -> bool:
    path = PurePosixPath(relative_path)
    return not (
        any(part.lower() in OUTPUT_DIRECTORIES for part in path.parts[:-1])
        or path.suffix.lower() in OUTPUT_SUFFIXES
        or " - copy." in path.name.lower()
    )


def install_hecstac_parser_compatibility() -> None:
    """Work around hecstac 0.5.3's unbound HMS attribute-parser state."""

    def parse_attrs(lines: list[str]) -> OrderedDict:
        attrs: dict = {}
        parent_key = None
        parent_val = None
        for line in lines:
            if line.strip() == "End:":
                return OrderedDict(attrs)
            if not line:
                continue

            top_level = re.findall(ATTR_KEYVAL_GROUPER, line)
            nested = re.findall(ATTR_NESTED_KEYVAL_GROUPER, line)
            if top_level:
                parent_key, parent_val = hms_utils._process_keyval_pairs(
                    attrs, top_level
                )
            elif nested:
                if parent_key is None:
                    raise ValueError(f"Nested HMS attribute has no parent: {line!r}")
                hms_utils._process_nested_pair(attrs, nested, parent_key, parent_val)
            elif "Hamon Coefficient" in line:
                key, val = line.split(":", 1)
                hms_utils.add_no_duplicate(attrs, key, val)
            else:
                raise ValueError(f"Unexpected HMS attribute line: {line!r}")
        raise ValueError("never found End:")

    hms_utils.parse_attrs = parse_attrs


def discover_s3_inputs(project: str, s3_client) -> tuple[list[tuple[str, str]], str]:
    parsed = urlparse(project)
    project_key = parsed.path.lstrip("/")
    prefix = project_key.rsplit("/", 1)[0]
    paginator = s3_client.get_paginator("list_objects_v2")
    inputs: list[tuple[str, str]] = []

    for page in paginator.paginate(Bucket=parsed.netloc, Prefix=f"{prefix}/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            relative = key.removeprefix(f"{prefix}/")
            if relative and is_input(relative):
                inputs.append((relative, f"s3://{parsed.netloc}/{key}"))
    return sorted(inputs), prefix


def discover_local_inputs(project: str) -> tuple[list[tuple[str, str]], str]:
    root = Path(project).expanduser().resolve().parent
    inputs = [
        (path.relative_to(root).as_posix(), str(path))
        for path in root.rglob("*")
        if path.is_file() and is_input(path.relative_to(root).as_posix())
    ]
    return sorted(inputs), str(root)


def discover_inputs(project: str, s3_client) -> tuple[list[tuple[str, str]], str]:
    if project.startswith("s3://"):
        return discover_s3_inputs(project, s3_client)
    return discover_local_inputs(project)


def asset_metadata(relative: str) -> tuple[str, list[str], str]:
    """Return media type, roles, and description for an HMS input asset."""
    path = PurePosixPath(relative)
    suffix = ".xml" if path.name.lower().endswith(".aux.xml") else path.suffix.lower()
    media_type, roles, description = ASSET_METADATA.get(
        suffix,
        (
            "application/octet-stream",
            ["data", "hms-supporting"],
            "Supporting HEC-HMS model input.",
        ),
    )
    roles = [role for role in roles if role not in {"input", "data", "metadata"}]
    return media_type, roles, description


def normalize_document(
    document: dict, crs: CRS | None, projection_source: str | None
) -> None:
    """Normalize legacy hecstac fields and S3-blind summary counts."""
    properties = document["properties"]
    legacy_wkt = properties.pop("proj:wkt", None)
    if crs is None and legacy_wkt:
        crs = CRS(legacy_wkt)
    if crs is not None:
        properties["proj:wkt2"] = crs.to_wkt()
        authority = crs.to_authority()
        properties["proj:code"] = ":".join(authority) if authority else None
    if projection_source:
        properties["hecstac:projection_source"] = projection_source

    filenames = [PurePosixPath(key).name.lower() for key in document["assets"]]
    properties["hms:summary"] = {
        "Basins": sum(name.endswith(".basin") for name in filenames),
        "Controls": sum(name.endswith(".control") for name in filenames),
        "Mets": sum(name.endswith(".met") for name in filenames),
        "Runs": sum(name.endswith(".run") for name in filenames),
        "Terrain": sum(name.endswith(".terrain") for name in filenames),
        "Paired_Data": sum(name.endswith(".pdata") for name in filenames),
        "Grid": sum(name.endswith(".grid") for name in filenames),
        "Gage": sum(name.endswith(".gage") for name in filenames),
        "SQLite": sum(name.endswith(".sqlite") for name in filenames),
    }


def create_item(
    project: str,
    inputs: list[tuple[str, str]],
    item_id: str,
    destination: str,
    simplify_geometry: bool,
) -> HMSModelItem:
    """Construct an HMS item without generating thumbnails or derived GeoJSON."""
    item = HMSModelItem(
        item_id,
        NULL_STAC_GEOMETRY,
        NULL_STAC_BBOX,
        NULL_DATETIME,
        {"hms_project_file": project},
        href=destination,
        assets={},
    )
    for relative, href in inputs:
        # Bypass HMSModelItem.add_asset(): hecstac 0.5.3 eagerly treats every
        # SQLite asset as an HMS basin database, including ancillary GIS DBs.
        media_type, roles, description = asset_metadata(relative)
        extra_fields = {}
        if PurePosixPath(relative).parent != PurePosixPath("."):
            extra_fields["hecstac:relative_path"] = relative
        pystac.Item.add_asset(
            item,
            relative,
            Asset(
                href=href,
                title=Path(relative).name,
                media_type=media_type,
                roles=roles or None,
                description=description,
                extra_fields=extra_fields,
            ),
        )
    item.simplify_geometry = simplify_geometry
    ProjectionExtension.add_to(item)
    item.properties["hecstac:asset_scope"] = "all-inputs"
    item.properties["hecstac:asset_count"] = len(item.assets)
    return item


def main() -> None:
    args = parse_args()
    install_hecstac_parser_compatibility()
    session = boto3.Session()
    configure_aws_environment(session)
    s3_client = session.client("s3")
    crs = resolve_crs(args.projection, s3_client)

    project = args.project
    if Path(urlparse(project).path).suffix.lower() != ".hms":
        raise ValueError(f"Expected an HEC-HMS .hms project: {project}")

    inputs, source_prefix = discover_inputs(project, s3_client)
    if not inputs:
        raise FileNotFoundError(f"No model inputs found beside {project}")
    if project not in {href for _, href in inputs}:
        raise FileNotFoundError(
            f"Project file was not found during input discovery: {project}"
        )

    item_id = args.item_id or Path(project).stem
    filename = args.filename or f"{item_id}.json"
    destination = output_location(args.output, filename)
    item = create_item(
        project=project,
        inputs=inputs,
        item_id=item_id,
        destination=destination,
        simplify_geometry=not args.no_simplify,
    )
    item.properties["hecstac:source_prefix"] = source_prefix

    document = item.to_dict()
    normalize_document(document, crs, args.projection)
    if not args.no_validate:
        pystac.Item.from_dict(document).validate()
    write_document(destination, document, s3_client)
    print(f"Wrote {destination} ({len(document['assets'])} input assets)")


if __name__ == "__main__":
    main()
