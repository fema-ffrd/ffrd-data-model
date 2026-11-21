#!/usr/bin/env python3
"""Generate a STAC Collection and one Item per low-head dam (LHDI)."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

from pyproj import CRS, Transformer

LHDI_HOME = "https://nid.sec.usace.army.mil/lhdi/"
LHDI_DAM_PAGE = "https://nid.sec.usace.army.mil/lhdi/dams"
SOURCE_RETRIEVED_ON = "2026-10-07"
VERSION_EXTENSION_URL = "https://stac-extensions.github.io/version/v1.2.0/schema.json"

ITEM_PROPERTY_LABELS = {
    "lhdId": "lhd_id",
    "federalId": "federal_id",
    "state": "state",
    "countyState": "county_state",
    "city": "city",
    "nearestRiver": "nearest_river",
    "primaryPurposeId": "primary_purpose",
    "purposeIds": "purposes",
    "primaryTypeId": "primary_type",
    "damTypeIds": "dam_types",
    "primaryOwnerTypeId": "primary_owner_type",
    "primaryOwnerName": "primary_owner_name",
    "ownerNames": "owner_names",
    "ownerTypeIds": "owner_types",
    "reviewStatusId": "review_status",
    "lhdReviewer": "reviewer",
    "fatalityId": "fatality_classification",
    "conditionAssessmentId": "condition_assessment",
    "stateRegulatoryAgency": "state_regulatory_agency",
    "primarySourceAgency": "source_agency",
    "federalRegDamId": "federal_regulated",
    "stateRegDamId": "state_regulated",
    "operationalStatusId": "operational_status",
    "yearCompleted": "year_completed",
    "lastInspected": "last_inspected",
    "lastEditedDate": "last_edited_date",
    "damHeight": "dam_height_ft",
    "hydraulicHeight": "hydraulic_height_ft",
    "structuralHeight": "structural_height_ft",
    "nidHeight": "nid_height_ft",
    "length": "dam_length_ft",
    "width": "dam_width_ft",
    "damVolume": "volume_cubic_yards",
}

MEASUREMENT_KEYS = {
    "damHeight",
    "hydraulicHeight",
    "structuralHeight",
    "nidHeight",
    "length",
    "width",
    "damVolume",
}

REQUIRED_SOURCE_KEYS = {"lhdId", "lastEditedDate"}


def measurement(
    value: str | int | float | None, key: str, index: int
) -> int | float | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Feature {index} has invalid {key}: {value!r}") from exc
    if not number.is_finite():
        raise ValueError(f"Feature {index} has invalid {key}: {value!r}")
    return int(number) if number == number.to_integral_value() else float(number)


def relative_href(target: Path, document: Path) -> str:
    return Path(os.path.relpath(target.resolve(), document.resolve().parent)).as_posix()


def normalize_version(version: str) -> str:
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.\d+)?", version.strip())
    if not match:
        raise ValueError(f"Collection version must match X.Y or X.Y.Z: {version!r}")
    return f"{int(match.group(1))}.{int(match.group(2))}"


def normalized_item_timestamp(value: object) -> str:
    if isinstance(value, str):
        candidate = value.strip()
        if candidate and candidate.lower() != "nan/nan/nan":
            try:
                return f"{date.fromisoformat(candidate).isoformat()}T00:00:00Z"
            except ValueError:
                pass
    return f"{SOURCE_RETRIEVED_ON}T00:00:00Z"


def collection_metadata(
    source: Path, features: list[dict]
) -> tuple[str, str, list[str]]:
    dataset_name = source.stem.replace("_", " ").replace("-", " ")
    state_values = sorted(
        {
            props.get("state")
            for feature in features
            if isinstance(feature, dict)
            for props in [feature.get("properties")]
            if isinstance(props, dict)
            and isinstance(props.get("state"), str)
            and props.get("state")
        }
    )
    title = f"National Inventory of Dams: low-head dams ({dataset_name})"
    description = (
        f"USACE low-head dam inventory points from source dataset '{source.name}'. "
        "Temporal extent represents record-level lastEditedDate values, not construction "
        "or observation dates. "
        f"Source inventory retrieved on {SOURCE_RETRIEVED_ON}."
    )
    keywords = ["dams", "low-head dams", "LHDI", "National Inventory of Dams"]
    keywords.extend(state_values)
    return title, description, keywords


def build_collection(
    source: Path,
    output: Path,
    source_href: str | None = None,
    collection_id: str | None = None,
    parent_href: str | None = None,
    root_href: str | None = None,
    version: str = "1.0",
) -> tuple[dict, list[tuple[Path, dict, Path, dict]]]:
    version = normalize_version(version)
    if source.resolve() == output.resolve():
        raise ValueError("Collection output must not overwrite the source GeoJSON")
    if source_href is not None and urlparse(source_href).scheme not in {
        "http",
        "https",
        "s3",
        "file",
    }:
        raise ValueError("--source-href must be an absolute URL or URI")

    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("type") != "FeatureCollection":
        raise ValueError("Input must be a GeoJSON FeatureCollection")
    features = data.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("Input must contain at least one feature")

    declared_crs = data.get("crs")
    if declared_crs is None:
        crs_name = "EPSG:4326"
    else:
        if not isinstance(declared_crs, dict) or declared_crs.get("type") != "name":
            raise ValueError("Unsupported GeoJSON CRS declaration")
        crs_name = declared_crs.get("properties", {}).get("name")
        if not isinstance(crs_name, str):
            raise ValueError("GeoJSON CRS must have a name")
    transformer = Transformer.from_crs(
        CRS.from_user_input(crs_name), CRS.from_epsg(4326), always_xy=True
    )

    collection_id = collection_id or source.stem
    item_dir = output.parent / collection_id
    collection_href = output.name
    collection_links = [
        {"rel": "self", "href": collection_href, "type": "application/json"},
        {
            "rel": "root",
            "href": root_href or parent_href or collection_href,
            "type": "application/json",
        },
    ]
    if parent_href or root_href:
        collection_links.append(
            {
                "rel": "parent",
                "href": parent_href or root_href,
                "type": "application/json",
            }
        )
    collection_links.append(
        {
            "rel": "related",
            "href": LHDI_HOME,
            "type": "text/html",
            "title": "NID Low-Head Dam Inventory",
        }
    )

    xs, ys, updates = [], [], []
    entries: list[tuple[Path, dict, Path, dict]] = []
    seen_ids = set()

    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise ValueError(f"Feature {index} must be an object")
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            raise ValueError(f"Feature {index} must have properties")

        missing_required = REQUIRED_SOURCE_KEYS - properties.keys()
        if missing_required:
            raise ValueError(
                f"Feature {index} is missing required source fields: {sorted(missing_required)}"
            )

        lhd_id = properties.get("lhdId")
        if not isinstance(lhd_id, str) or not lhd_id.strip():
            raise ValueError(f"Feature {index} has an invalid lhdId")

        item_id = lhd_id.strip()
        if item_id in seen_ids:
            item_id = f"{item_id}-{index}"
        if item_id in seen_ids:
            raise ValueError(f"Duplicate low-head Item ID: {item_id}")
        seen_ids.add(item_id)

        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") != "Point":
            raise ValueError(f"Feature {index} must have a Point geometry")
        point = geometry.get("coordinates")
        if (
            not isinstance(point, list)
            or len(point) != 2
            or not all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                for value in point
            )
        ):
            raise ValueError(f"Feature {index} must have two numeric coordinates")

        lon, lat = transformer.transform(*point)
        if not (
            math.isfinite(lon)
            and math.isfinite(lat)
            and -180 <= lon <= 180
            and -90 <= lat <= 90
        ):
            raise ValueError(f"Feature {index} has invalid WGS84 coordinates")

        timestamp = normalized_item_timestamp(properties.get("lastEditedDate"))
        xs.append(lon)
        ys.append(lat)
        updates.append(timestamp)

        item_path = item_dir / f"{item_id}.json"
        asset_path = item_dir / f"{item_id}.geojson"
        item_parent_href = relative_href(output, item_path)
        wgs84_geometry = {"type": "Point", "coordinates": [lon, lat]}

        mapped_properties = {key: properties.get(key) for key in ITEM_PROPERTY_LABELS}
        item_properties = {
            (f"dam:{label}" if key in MEASUREMENT_KEYS else label): (
                measurement(mapped_properties[key], key, index)
                if key in MEASUREMENT_KEYS
                else mapped_properties[key]
            )
            for key, label in ITEM_PROPERTY_LABELS.items()
        }

        title = properties.get("name") or f"Low-head dam {lhd_id}"
        item = {
            "type": "Feature",
            "stac_version": "1.1.0",
            "stac_extensions": [],
            "id": item_id,
            "collection": collection_id,
            "geometry": wgs84_geometry,
            "bbox": [lon, lat, lon, lat],
            "properties": {
                **item_properties,
                "datetime": timestamp,
                "title": title,
                "source_retrieved_on": SOURCE_RETRIEVED_ON,
            },
            "assets": {
                "data": {
                    "href": asset_path.name,
                    "type": "application/geo+json",
                    "roles": ["data"],
                    "title": "Single low-head dam GeoJSON feature",
                }
            },
            "links": [
                {"rel": "self", "href": item_path.name, "type": "application/geo+json"},
                {
                    "rel": "collection",
                    "href": item_parent_href,
                    "type": "application/json",
                },
                {"rel": "parent", "href": item_parent_href, "type": "application/json"},
                {
                    "rel": "root",
                    "href": root_href or parent_href or item_parent_href,
                    "type": "application/json",
                },
                {
                    "rel": "related",
                    "href": f"{LHDI_DAM_PAGE}/{lhd_id}",
                    "type": "text/html",
                    "title": f"LHDI dam record: {title}",
                },
            ],
        }

        asset = {
            "type": "Feature",
            "properties": properties,
            "geometry": wgs84_geometry,
        }
        entries.append((item_path, item, asset_path, asset))
        collection_links.append(
            {
                "rel": "item",
                "href": relative_href(item_path, output),
                "type": "application/geo+json",
            }
        )

    title, description, keywords = collection_metadata(source, features)
    collection = {
        "type": "Collection",
        "stac_version": "1.1.0",
        "stac_extensions": [VERSION_EXTENSION_URL],
        "version": version,
        "id": collection_id,
        "title": title,
        "description": description,
        "license": "other",
        "keywords": keywords,
        "providers": [
            {
                "name": "U.S. Army Corps of Engineers",
                "roles": ["producer"],
                "url": "https://nid.sec.usace.army.mil/",
            }
        ],
        "extent": {
            "spatial": {"bbox": [[min(xs), min(ys), max(xs), max(ys)]]},
            "temporal": {"interval": [[min(updates), max(updates)]]},
        },
        "summaries": {"source_retrieved_on": [SOURCE_RETRIEVED_ON]},
        "assets": {
            "source": {
                "href": source_href or relative_href(source, output),
                "type": "application/geo+json",
                "roles": ["data"],
                "title": "Original low-head dam GeoJSON inventory",
            }
        },
        "links": collection_links,
    }
    return collection, entries


def write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, help="Low-head dam GeoJSON FeatureCollection"
    )
    parser.add_argument(
        "--output", type=Path, help="Collection JSON (default: beside source)"
    )
    parser.add_argument(
        "--source-href", help="Published absolute URL/URI for original GeoJSON"
    )
    parser.add_argument(
        "--id", dest="collection_id", help="Collection ID (default: source stem)"
    )
    parser.add_argument("--parent-href", help="URL/URI of containing Catalog")
    parser.add_argument("--root-href", help="URL/URI of root Catalog")
    parser.add_argument(
        "--version",
        default="1.0",
        help="Collection version (X.Y; legacy X.Y.Z is normalized to X.Y)",
    )
    args = parser.parse_args()

    output = args.output or args.source.with_suffix(".collection.json")
    collection, entries = build_collection(
        args.source,
        output,
        args.source_href,
        args.collection_id,
        args.parent_href,
        args.root_href,
        args.version,
    )
    for item_path, item, asset_path, asset in entries:
        write_json(item_path, item)
        write_json(asset_path, asset)
    write_json(output, collection)


if __name__ == "__main__":
    main()
