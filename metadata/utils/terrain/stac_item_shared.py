#!/usr/bin/env python3
"""Shared STAC item helpers used by S3 workflows."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from pathlib import Path

import rasterio
from rasterio.warp import transform_bounds


VERSION_EXTENSION_URL = "https://stac-extensions.github.io/version/v1.2.0/schema.json"


def upsert_link(links: list[dict], rel: str, href: str, media_type: str) -> None:
    for link in links:
        if link.get("rel") == rel:
            link["href"] = href
            link["type"] = media_type
            return
    links.append({"rel": rel, "href": href, "type": media_type})


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


def iso_z(dt: datetime) -> str:
    """Format a datetime as UTC ISO-8601 with a trailing Z."""
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_stac_item(
    tif_path: Path,
    item_version: str = "1.0",
    deprecated: bool = False,
    source_etag: str | None = None,
    source_created: str | None = None,
    source_updated: str | None = None,
) -> dict:
    """Read a GeoTIFF and build a STAC Item dictionary for it."""
    if source_created is not None and source_updated is not None:
        created = source_created
        updated = source_updated
    else:
        stat = tif_path.stat()
        created = source_created or iso_z(datetime.fromtimestamp(stat.st_birthtime, tz=timezone.utc))
        if source_updated is not None:
            updated = source_updated
        else:
            updated = iso_z(datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)) if (stat.st_mtime > stat.st_birthtime) else created

    parse_semver(item_version)

    with rasterio.open(tif_path) as src:
        bounds = src.bounds
        width = src.width
        height = src.height
        count = src.count
        crs = src.crs
        transform = src.transform

        if crs is not None:
            minx, miny, maxx, maxy = transform_bounds(
                crs,
                "EPSG:4326",
                bounds.left,
                bounds.bottom,
                bounds.right,
                bounds.top,
                densify_pts=21,
            )
        else:
            minx, miny, maxx, maxy = bounds.left, bounds.bottom, bounds.right, bounds.top

        geometry = {
            "type": "Polygon",
            "coordinates": [[
                [minx, miny],
                [maxx, miny],
                [maxx, maxy],
                [minx, maxy],
                [minx, miny],
            ]],
        }
        bbox = [minx, miny, maxx, maxy]

        proj_epsg = crs.to_epsg() if crs else None
        proj_wkt2 = crs.to_wkt() if crs else None

        x_res = math.sqrt(transform.a * transform.a + transform.d * transform.d)
        y_res = math.sqrt(transform.b * transform.b + transform.e * transform.e)
        spatial_resolution = x_res if abs(x_res - y_res) < 1e-9 else max(x_res, y_res)

        crs_unit = None
        if crs is not None:
            crs_unit = getattr(crs, "linear_units", None)

        band_meta = []
        for i in range(1, count + 1):
            nodata = src.nodatavals[i - 1]
            dtype = src.dtypes[i - 1]
            band = {"band": i, "data_type": dtype}
            unit = None
            if src.units and len(src.units) >= i:
                unit = src.units[i - 1]
            if not unit:
                unit = crs_unit
            if nodata is not None:
                band["nodata"] = nodata
            if unit:
                band["unit"] = unit
            band["spatial_resolution"] = spatial_resolution
            band_meta.append(band)

        item = {
            "type": "Feature",
            "stac_version": "1.1.0",
            "stac_extensions": [
                "https://stac-extensions.github.io/projection/v2.0.0/schema.json",
                "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
                VERSION_EXTENSION_URL,
            ],
            "id": tif_path.stem,
        }
        if source_etag is not None:
            item["etag"] = source_etag

        item.update({
            "geometry": geometry,
            "bbox": bbox,
            "properties": {
                "datetime": updated,
                "created": created,
                "updated": updated,
                "version": item_version,
                "deprecated": deprecated,
                "proj:shape": [height, width],
                "proj:transform": [
                    transform.a,
                    transform.b,
                    transform.c,
                    transform.d,
                    transform.e,
                    transform.f,
                    0.0,
                    0.0,
                    1.0,
                ],
                **({"proj:epsg": proj_epsg} if proj_epsg is not None else {}),
                **({"proj:wkt2": proj_wkt2} if proj_wkt2 is not None else {}),
                **({"proj:bbox": [bounds.left, bounds.bottom, bounds.right, bounds.top]} if bounds else {}),
                **({"proj:code": f"EPSG:{proj_epsg}"} if proj_epsg is not None else {}),
            },
            "assets": {
                "data": {
                    "href": tif_path.name,
                    "type": "image/tiff; application=geotiff",
                    "roles": ["data"],
                    "title": tif_path.name,
                    "raster:bands": band_meta,
                    "proj:shape": [height, width],
                }
            },
            "links": [],
        })

        return item
