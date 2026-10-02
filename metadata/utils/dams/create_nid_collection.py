#!/usr/bin/env python3
"""Generate a STAC Collection and one Item per NID dam."""

from __future__ import annotations

import argparse
import json
import math
import mimetypes
import os
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pyproj import CRS, Transformer


NID_HOME = "https://nid.sec.usace.army.mil/nid/#/"
NID_DOWNLOADS = f"{NID_HOME}downloads"
NID_INVENTORY_API = "https://nid.sec.usace.army.mil/api/dams"
SOURCE_RETRIEVED_ON = "2026-09-30"
THUMBNAIL_MANIFEST = Path(__file__).with_name("thumbnail_urls.json")

ITEM_PROPERTY_LABELS = {
    "nidId": "nid_id",
    "state": "state",
    "county": "county",
    "huc4": "huc4",
    "huc8": "huc8",
    "primaryPurposeId": "primary_purpose",
    "primaryDamTypeId": "primary_dam_type",
    "damHeight": "dam_height_ft",
    "hydraulicHeight": "hydraulic_height_ft",
    "structuralHeight": "structural_height_ft",
    "nidHeight": "nid_height_ft",
    "damLength": "dam_length_ft",
    "volume": "volume_cubic_yards",
    "nidStorage": "nid_storage_acre_ft",
    "maxStorage": "max_storage_acre_ft",
    "normalStorage": "normal_storage_acre_ft",
    "surfaceArea": "surface_area_acres",
    "drainageArea": "drainage_area_sq_miles",
    "maxDischarge": "max_discharge_cubic_ft_second",
    "spillwayWidth": "spillway_width_ft",
    "yearCompleted": "year_completed",
    "publicHazardId": "hazard_potential_classification",
    "conditionAssessId": "condition_assessment",
    "inspectionDate": "last_inspection_date",
    "eapId": "eap_prepared",
    "sourceAgency": "source_agency",
}

MEASUREMENT_KEYS = {
    "damHeight", "hydraulicHeight", "structuralHeight", "nidHeight",
    "damLength", "volume", "nidStorage", "maxStorage", "normalStorage",
    "surfaceArea", "drainageArea", "maxDischarge", "spillwayWidth",
}


def measurement(value: str | int | float | None, key: str, index: int) -> int | float | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Feature {index} has invalid {key}: {value!r}") from exc
    if not number.is_finite():
        raise ValueError(f"Feature {index} has invalid {key}: {value!r}")
    return int(number) if number == number.to_integral_value() else float(number)


def derived_properties(properties: dict) -> dict:
    height = properties["dam:structural_height_ft"]
    storage = properties["dam:max_storage_acre_ft"]
    normal_storage = properties["dam:normal_storage_acre_ft"]
    drainage = properties["dam:drainage_area_sq_miles"]
    dam_type = properties["primary_dam_type"]
    purpose = properties["primary_purpose"]
    hazard = properties["hazard_potential_classification"]
    agency = properties["source_agency"]

    flood_fraction = (
        (storage - normal_storage) / storage
        if storage is not None and storage != 0 and normal_storage is not None
        else None
    )
    if dam_type == "Earth":
        breach_class = (
            "EarthenDamGT30ft" if height > 30 else "EarthenDamLE30ft"
        ) if height is not None else None
    elif dam_type is None:
        breach_class = None
    elif "Concrete" in dam_type:
        breach_class = "ConcreteDam"
    else:
        breach_class = "Other"
    breach_methods = {
        "EarthenDamGT30ft": "UserDefined",
        "EarthenDamLE30ft": "SimplifiedPhysical",
        "ConcreteDam": "FixedWidth",
        "Other": "UniqueCase",
        None: None,
    }

    def at_least(value: int | float | None, threshold: int) -> bool | None:
        return value >= threshold if value is not None else None

    def any_known_true(*values: bool | None) -> bool | None:
        if any(value is True for value in values):
            return True
        if any(value is None for value in values):
            return None
        return False

    size_class = (
        "Large" if height >= 100 else "Medium" if height >= 50 else "Small"
    ) if height is not None else None
    storage_class = (
        "Major" if storage >= 100000 else
        "Significant" if storage >= 10000 else
        "Moderate" if storage >= 1000 else "Minor"
    ) if storage is not None else None
    hydrologic_influence = (
        "Regional" if drainage >= 250 else
        "Watershed" if drainage >= 50 else "Local"
    ) if drainage is not None else None
    if storage is not None and drainage is not None:
        score = (
            {"Low": 1, "Significant": 3, "High": 5}.get(hazard, 0)
            + (4 if storage >= 100000 else 3 if storage >= 10000 else
               2 if storage >= 1000 else 1)
            + (3 if purpose == "Flood Risk Reduction" else 1)
            + (3 if drainage >= 250 else 2 if drainage >= 50 else 1)
        )
        priority = 1 if score >= 12 else 2 if score >= 8 else 3 if score >= 4 else 4
    else:
        priority = None
    return {
        "ffrd:flood_pool_fraction": flood_fraction,
        "ffrd:data_emergency_action_plan": (
            properties["eap_prepared"] == "Yes"
            if properties["eap_prepared"] is not None else None
        ),
        "ffrd:data_operations_manual_likely": (
            agency == "US Army Corps of Engineers" if agency is not None else None
        ),
        "ffrd:breach_structure_class": breach_class,
        "ffrd:recommended_breach_method": breach_methods[breach_class],
        "ffrd_screening:size_class": size_class,
        "ffrd_screening:storage_class": storage_class,
        "ffrd_screening:flood_control_dominant": (
            flood_fraction >= 0.75 if flood_fraction is not None else None
        ),
        "ffrd_screening:hydrologic_influence": hydrologic_influence,
        "ffrd_screening:major_flood_risk_infrastructure": any_known_true(
            hazard == "High" if hazard is not None else None,
            at_least(storage, 100000),
            purpose == "Flood Risk Reduction" if purpose is not None else None,
        ),
        "ffrd_screening:candidate_reservoir_operations_model": any_known_true(
            purpose == "Flood Risk Reduction" if purpose is not None else None,
            at_least(storage, 10000),
        ),
        "ffrd_screening:candidate_for_breach_analysis": any_known_true(
            hazard == "High" if hazard is not None else None,
            at_least(storage, 10000),
        ),
        "ffrd_screening:recommended_hydraulic_type": (
            "TypeA" if agency == "US Army Corps of Engineers"
            and purpose == "Flood Risk Reduction"
            and storage is not None and storage >= 10000 else None
        ),
        "ffrd_screening:modeling_priority": priority,
    }


def relative_href(target: Path, document: Path) -> str:
    return Path(os.path.relpath(target.resolve(), document.resolve().parent)).as_posix()


def fetch_thumbnail_urls(source: Path) -> dict[str, str]:
    data = json.loads(source.read_text(encoding="utf-8"))
    features = data.get("features")
    if not isinstance(features, list):
        raise ValueError("Input must contain a features list")
    ids = {
        feature["properties"]["nidId"]
        for feature in features
        if feature["properties"].get("hasDamPhotoId") == "Yes"
    }
    urls = {}
    for nid_id in sorted(ids):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", nid_id):
            raise ValueError(f"Invalid NID ID for thumbnail lookup: {nid_id!r}")
        request = Request(
            f"{NID_INVENTORY_API}/{nid_id}/inventory",
            headers={"Accept": "application/json", "User-Agent": "ffrd-stac-generator/1.0"},
        )
        with urlopen(request, timeout=20) as response:
            record = json.load(response)
        if not isinstance(record, dict) or record.get("nidId") != nid_id:
            raise ValueError(f"NID API returned the wrong record for {nid_id}")
        url = record.get("thumbnailUrl")
        if not isinstance(url, str) or not (
            urlparse(url).scheme == "https" and urlparse(url).netloc
        ):
            raise ValueError(f"NID API returned no HTTPS thumbnail for {nid_id}: {url!r}")
        urls[nid_id] = url
    return urls


def build_collection(
    source: Path,
    output: Path,
    source_href: str | None = None,
    collection_id: str | None = None,
    parent_href: str | None = None,
    root_href: str | None = None,
    thumbnail_urls: dict[str, str] | None = None,
) -> tuple[dict, list[tuple[Path, dict, Path, dict]]]:
    if source.resolve() == output.resolve():
        raise ValueError("Collection output must not overwrite the source GeoJSON")
    if source_href is not None and urlparse(source_href).scheme not in {
        "http", "https", "s3", "file"
    }:
        raise ValueError("--source-href must be an absolute URL or URI")

    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("type") != "FeatureCollection":
        raise ValueError("Input must be a GeoJSON FeatureCollection")
    features = data.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("Input must contain at least one feature")
    if thumbnail_urls is None:
        thumbnail_urls = json.loads(THUMBNAIL_MANIFEST.read_text(encoding="utf-8"))

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
    item_dir = output.parent / f"{output.stem}-items"
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
        collection_links.append({
            "rel": "parent",
            "href": parent_href or root_href,
            "type": "application/json",
        })
    collection_links.extend([
        {
            "rel": "related",
            "href": NID_HOME,
            "type": "text/html",
            "title": "National Inventory of Dams",
        },
        {
            "rel": "via",
            "href": NID_DOWNLOADS,
            "type": "text/html",
            "title": "NID Data Downloads",
        },
    ])

    xs, ys, updates = [], [], []
    entries = []
    seen_ids = set()
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise ValueError(f"Feature {index} must be an object")
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            raise ValueError(f"Feature {index} must have properties")
        missing = ITEM_PROPERTY_LABELS.keys() - properties.keys()
        if missing:
            raise ValueError(f"Feature {index} is missing Item fields: {sorted(missing)}")
        nid_id, fid = properties.get("nidId"), properties.get("fid")
        if not isinstance(nid_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", nid_id):
            raise ValueError(f"Feature {index} has an invalid nidId")
        if not isinstance(fid, int) or isinstance(fid, bool) or fid < 0:
            raise ValueError(f"Feature {index} has an invalid fid")
        item_id = f"{nid_id}-{fid}"
        if item_id in seen_ids:
            raise ValueError(f"Duplicate dam Item ID: {item_id}")
        seen_ids.add(item_id)

        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") != "Point":
            raise ValueError(f"Feature {index} must have a Point geometry")
        point = geometry.get("coordinates")
        if not isinstance(point, list) or len(point) != 2 or not all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in point
        ):
            raise ValueError(f"Feature {index} must have two numeric coordinates")
        lon, lat = transformer.transform(*point)
        if not (
            math.isfinite(lon) and math.isfinite(lat)
            and -180 <= lon <= 180 and -90 <= lat <= 90
        ):
            raise ValueError(f"Feature {index} has invalid WGS84 coordinates")
        updated = properties.get("dataUpdated")
        if not isinstance(updated, str):
            raise ValueError(f"Feature {index} is missing a dataUpdated date")
        updated_date = date.fromisoformat(updated)
        timestamp = f"{updated_date.isoformat()}T00:00:00Z"
        xs.append(lon)
        ys.append(lat)
        updates.append(timestamp)

        item_path = item_dir / f"{item_id}.json"
        asset_path = item_dir / f"{item_id}.geojson"
        item_parent_href = relative_href(output, item_path)
        wgs84_geometry = {"type": "Point", "coordinates": [lon, lat]}
        item_properties = {
            (f"dam:{label}" if key in MEASUREMENT_KEYS else label): (
                measurement(properties[key], key, index)
                if key in MEASUREMENT_KEYS else properties[key]
            )
            for key, label in ITEM_PROPERTY_LABELS.items()
        }
        assets = {
            "data": {
                "href": asset_path.name,
                "type": "application/geo+json",
                "roles": ["data"],
                "title": "Single-dam GeoJSON feature",
            }
        }
        if properties.get("hasDamPhotoId") == "Yes":
            thumbnail_url = thumbnail_urls.get(nid_id)
            if not isinstance(thumbnail_url, str) or not (
                urlparse(thumbnail_url).scheme == "https" and urlparse(thumbnail_url).netloc
            ):
                raise ValueError(f"No cached HTTPS thumbnail for {nid_id}; use --refresh-thumbnails")
            thumbnail = {
                "href": thumbnail_url,
                "roles": ["thumbnail"],
                "title": "NID dam photo",
            }
            media_type = mimetypes.guess_type(urlparse(thumbnail_url).path)[0]
            if media_type is not None:
                thumbnail["type"] = media_type
            assets["thumbnail"] = thumbnail
        title = properties.get("name") or nid_id,
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
                **derived_properties(item_properties),
            },
            "assets": assets,
            "links": [
                {"rel": "self", "href": item_path.name, "type": "application/geo+json"},
                {"rel": "collection", "href": item_parent_href, "type": "application/json"},
                {"rel": "parent", "href": item_parent_href, "type": "application/json"},
                {
                    "rel": "root",
                    "href": root_href or parent_href or item_parent_href,
                    "type": "application/json",
                },
                {
                    "rel": "related",
                    "href": f"https://nid.sec.usace.army.mil/nid/#/dams/system/{nid_id}",
                    "type": "text/html",
                    "title": f"NID dam record: {title}",
                },
                {
                    "rel": "via",
                    "href": NID_DOWNLOADS,
                    "type": "text/html",
                    "title": "NID Data Downloads",
                },
            ],
        }
        asset = {
            "type": "Feature",
            "properties": properties,
            "geometry": wgs84_geometry,
        }
        entries.append((item_path, item, asset_path, asset))
        collection_links.append({
            "rel": "item",
            "href": relative_href(item_path, output),
            "type": "application/geo+json",
        })

    collection = {
        "type": "Collection",
        "stac_version": "1.1.0",
        "stac_extensions": [],
        "id": collection_id,
        "title": "National Inventory of Dams: Allegheny watershed (HUC4 0501)",
        "description": (
            "USACE National Inventory of Dams points selected for the Allegheny "
            "watershed (HUC4 0501). Temporal extent represents record-level "
            "dataUpdated dates, not construction or observation dates. "
            "Source records are not filtered by their own HUC4 attribute. "
            f"Source inventory retrieved from NID downloads on {SOURCE_RETRIEVED_ON}."
        ),
        "license": "other",
        "keywords": ["dams", "National Inventory of Dams", "Allegheny", "HUC4 0501"],
        "providers": [{
            "name": "U.S. Army Corps of Engineers",
            "roles": ["producer"],
            "url": "https://nid.sec.usace.army.mil/",
        }],
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
                "title": "Original NID GeoJSON inventory (NAD83)",
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
    parser.add_argument("source", type=Path, help="NID GeoJSON FeatureCollection")
    parser.add_argument("--output", type=Path, help="Collection JSON (default: beside source)")
    parser.add_argument("--source-href", help="Published absolute URL/URI for original GeoJSON")
    parser.add_argument("--id", dest="collection_id", help="Collection ID (default: source stem)")
    parser.add_argument("--parent-href", help="URL/URI of containing watershed Catalog")
    parser.add_argument("--root-href", help="URL/URI of root Catalog")
    parser.add_argument(
        "--refresh-thumbnails",
        action="store_true",
        help="Fetch thumbnail URLs from the NID API and update thumbnail_urls.json",
    )
    args = parser.parse_args()
    output = args.output or args.source.with_suffix(".collection.json")
    thumbnail_urls = fetch_thumbnail_urls(args.source) if args.refresh_thumbnails else None
    collection, entries = build_collection(
        args.source,
        output,
        args.source_href,
        args.collection_id,
        args.parent_href,
        args.root_href,
        thumbnail_urls,
    )
    if args.refresh_thumbnails:
        write_json(THUMBNAIL_MANIFEST, thumbnail_urls)
    for item_path, item, asset_path, asset in entries:
        write_json(item_path, item)
        write_json(asset_path, asset)
    write_json(output, collection)


if __name__ == "__main__":
    main()
