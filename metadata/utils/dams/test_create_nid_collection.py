"""Checks for the per-dam NID STAC Collection generator."""

import json
import re
import subprocess
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from pystac.validation import validate_dict

from create_nid_collection import (
    ITEM_PROPERTY_LABELS,
    MEASUREMENT_KEYS,
    NID_DOWNLOADS,
    NID_HOME,
    SOURCE_RETRIEVED_ON,
    THUMBNAIL_MANIFEST,
    build_collection,
    derived_properties,
    fetch_thumbnail_urls,
)


SOURCE = Path(__file__).with_name("0501_allegheny_nid-dams.geojson")


class NidCollectionTest(unittest.TestCase):
    def test_all_dams_and_valid_stac(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "collection.json"
            collection, entries = build_collection(SOURCE, output)
            validate_dict(collection)
            self.assertEqual(len(entries), 239)
            self.assertEqual(len([link for link in collection["links"] if link["rel"] == "item"]), 239)
            self.assertEqual(
                collection["extent"]["temporal"]["interval"],
                [["2021-04-09T00:00:00Z", "2026-09-16T00:00:00Z"]],
            )
            self.assertEqual(
                collection["summaries"]["source_retrieved_on"], ["2026-09-30"]
            )
            self.assertEqual(
                next(link["href"] for link in collection["links"] if link["rel"] == "related"),
                NID_HOME,
            )
            self.assertEqual(
                next(link["href"] for link in collection["links"] if link["rel"] == "via"),
                NID_DOWNLOADS,
            )
            self.assertEqual(
                (output.parent / collection["assets"]["source"]["href"]).resolve(),
                SOURCE.resolve(),
            )
            ids = set()
            thumbnail_urls = json.loads(THUMBNAIL_MANIFEST.read_text(encoding="utf-8"))
            thumbnail_count = 0
            labels = ITEM_PROPERTY_LABELS
            self.assertEqual(len(labels), 26)
            self.assertEqual(labels["nidId"], "nid_id")
            self.assertEqual(labels["damHeight"], "dam_height_ft")
            self.assertEqual(labels["publicHazardId"], "hazard_potential_classification")
            expected_fields = {
                "nid_id", "state", "county", "huc4", "huc8", "primary_purpose",
                "primary_dam_type", "dam:dam_height_ft", "dam:hydraulic_height_ft",
                "dam:structural_height_ft", "dam:nid_height_ft", "dam:dam_length_ft",
                "dam:volume_cubic_yards", "dam:nid_storage_acre_ft",
                "dam:max_storage_acre_ft", "dam:normal_storage_acre_ft",
                "dam:surface_area_acres", "dam:drainage_area_sq_miles",
                "dam:max_discharge_cubic_ft_second", "dam:spillway_width_ft",
                "year_completed",
                "hazard_potential_classification", "condition_assessment",
                "last_inspection_date", "eap_prepared", "source_agency",
                "datetime", "title", "source_retrieved_on",
                "ffrd:flood_pool_fraction", "ffrd:data_emergency_action_plan",
                "ffrd:data_operations_manual_likely", "ffrd:breach_structure_class",
                "ffrd:recommended_breach_method",
                "ffrd_screening:size_class", "ffrd_screening:storage_class",
                "ffrd_screening:flood_control_dominant",
                "ffrd_screening:hydrologic_influence",
                "ffrd_screening:major_flood_risk_infrastructure",
                "ffrd_screening:candidate_reservoir_operations_model",
                "ffrd_screening:candidate_for_breach_analysis",
                "ffrd_screening:recommended_hydraulic_type",
                "ffrd_screening:modeling_priority",
            }
            derived_fields = {key for key in expected_fields if key.startswith(("ffrd:", "ffrd_screening:"))}
            self.assertEqual(len(derived_fields), 14)
            self.assertEqual(
                {
                    f"dam:{labels[key]}" if key in MEASUREMENT_KEYS else labels[key]
                    for key in ITEM_PROPERTY_LABELS
                } | {"datetime", "title", "source_retrieved_on"} | derived_fields,
                expected_fields,
            )
            for item_path, item, asset_path, asset in entries:
                validate_dict(item)
                ids.add(item["id"])
                self.assertEqual(item["collection"], collection["id"])
                self.assertEqual(item["geometry"], asset["geometry"])
                self.assertEqual(set(item["properties"]), expected_fields)
                self.assertEqual(
                    item["properties"]["source_retrieved_on"], SOURCE_RETRIEVED_ON
                )
                self.assertTrue(
                    all(
                        re.fullmatch(r"(?:(?:dam|ffrd|ffrd_screening):)?[a-z][a-z0-9_]*", key)
                        for key in item["properties"]
                    )
                )
                self.assertEqual(
                    len([key for key in item["properties"] if key.startswith("dam:")]),
                    len(MEASUREMENT_KEYS),
                )
                for key in ITEM_PROPERTY_LABELS:
                    field = f"dam:{labels[key]}" if key in MEASUREMENT_KEYS else labels[key]
                    value = item["properties"][field]
                    source_value = asset["properties"][key]
                    if key in MEASUREMENT_KEYS and source_value is not None:
                        self.assertIsInstance(value, (int, float))
                        self.assertEqual(value, float(source_value))
                    else:
                        self.assertEqual(value, source_value)
                self.assertEqual(
                    {key: item["properties"][key] for key in derived_fields},
                    derived_properties(item["properties"]),
                )
                self.assertEqual(len(asset["properties"]), 98)
                self.assertEqual(item["links"][1]["href"], "../collection.json")
                related = [link for link in item["links"] if link["rel"] == "related"]
                self.assertEqual(len(related), 1)
                self.assertEqual(
                    related[0]["href"],
                    "https://nid.sec.usace.army.mil/nid/#/dams/system/"
                    + asset["properties"]["nidId"],
                )
                self.assertEqual(related[0]["type"], "text/html")
                self.assertEqual(
                    next(link["href"] for link in item["links"] if link["rel"] == "via"),
                    NID_DOWNLOADS,
                )
                self.assertEqual(item["assets"]["data"]["href"], asset_path.name)
                if asset["properties"]["hasDamPhotoId"] == "Yes":
                    thumbnail_count += 1
                    self.assertEqual(
                        item["assets"]["thumbnail"]["href"],
                        thumbnail_urls[asset["properties"]["nidId"]],
                    )
                    self.assertEqual(item["assets"]["thumbnail"]["roles"], ["thumbnail"])
                    self.assertEqual(item["assets"]["thumbnail"]["type"], "image/jpeg")
                else:
                    self.assertNotIn("thumbnail", item["assets"])
                self.assertEqual(item_path.parent, asset_path.parent)
            self.assertEqual(len(ids), 239)
            self.assertEqual(thumbnail_count, 17)
            self.assertEqual(len(thumbnail_urls), 17)
            self.assertEqual(
                len([item for _, item, _, _ in entries if item["properties"]["nid_id"] == "PA00114"]),
                2,
            )

    def test_cli_writes_linked_items_and_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "collection.json"
            subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("create_nid_collection.py")),
                    str(SOURCE),
                    "--output",
                    str(output),
                    "--source-href",
                    "https://example.org/dams.geojson",
                    "--id",
                    "allegheny-dams",
                    "--parent-href",
                    "https://example.org/watershed.json",
                    "--root-href",
                    "https://example.org/catalog.json",
                ],
                check=True,
            )
            collection = json.loads(output.read_text(encoding="utf-8"))
            validate_dict(collection)
            self.assertEqual(collection["id"], "allegheny-dams")
            self.assertEqual(collection["assets"]["source"]["href"], "https://example.org/dams.geojson")
            item_links = [link for link in collection["links"] if link["rel"] == "item"]
            for link in item_links:
                item_path = output.parent / link["href"]
                item = json.loads(item_path.read_text(encoding="utf-8"))
                asset = json.loads((item_path.parent / item["assets"]["data"]["href"]).read_text(encoding="utf-8"))
                self.assertEqual(
                    item["id"],
                    f"{asset['properties']['nidId']}-{asset['properties']['fid']}",
                )
                self.assertEqual(
                    asset["properties"]["nidId"], item["properties"]["nid_id"]
                )
                self.assertEqual(
                    float(asset["properties"]["maxStorage"])
                    if asset["properties"]["maxStorage"] is not None else None,
                    item["properties"]["dam:max_storage_acre_ft"],
                )
                if item["properties"]["nid_id"] == "PA00118":
                    self.assertEqual(item["properties"]["dam:max_discharge_cubic_ft_second"], 70000)
                    self.assertEqual(item["properties"]["dam:drainage_area_sq_miles"], 8844)
                    self.assertEqual(item["properties"]["dam:dam_length_ft"], 1064)
                    self.assertEqual(
                        item["assets"]["thumbnail"]["href"],
                        "https://usace-cwbi-prod-il2-nld2-docs.s3.us-gov-west-1.amazonaws.com/gallery/dams/550000/PA00118.JPG",
                    )
                self.assertEqual(
                    next(link["href"] for link in item["links"] if link["rel"] == "root"),
                    "https://example.org/catalog.json",
                )

    def test_bad_geometry_and_duplicate_id_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bad.geojson"
            data = json.loads(SOURCE.read_text(encoding="utf-8"))
            data["features"][0]["geometry"] = None
            source.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Feature 0 must have a Point"):
                build_collection(source, Path(directory) / "collection.json")
            data["features"][0] = data["features"][1]
            source.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate dam Item ID"):
                build_collection(source, Path(directory) / "collection.json")
            del data["features"][0]["properties"]["maxStorage"]
            source.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing Item fields"):
                build_collection(source, Path(directory) / "collection.json")
            data["features"][0]["properties"]["maxStorage"] = "not a number"
            source.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Feature 0 has invalid maxStorage"):
                build_collection(source, Path(directory) / "collection.json")

    def test_refresh_uses_api_once_per_nid_id(self):
        def respond(request, timeout):
            nid_id = request.full_url.rsplit("/", 2)[-2]
            self.assertEqual(timeout, 20)
            return BytesIO(
                json.dumps({
                    "nidId": nid_id,
                    "thumbnailUrl": f"https://example.org/{nid_id}.jpg",
                }).encode("utf-8")
            )

        with patch("create_nid_collection.urlopen", side_effect=respond) as get:
            urls = fetch_thumbnail_urls(SOURCE)
        self.assertEqual(len(urls), 17)
        self.assertEqual(get.call_count, 17)
        self.assertEqual(urls["PA00114"], "https://example.org/PA00114.jpg")

    def test_photo_without_cached_thumbnail_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "No cached HTTPS thumbnail"):
                build_collection(SOURCE, Path(directory) / "collection.json", thumbnail_urls={})

    def test_derived_thresholds_and_missing_inputs(self):
        props = {
            "dam:structural_height_ft": 30,
            "dam:max_storage_acre_ft": 10000,
            "dam:normal_storage_acre_ft": 2500,
            "dam:drainage_area_sq_miles": 50,
            "primary_dam_type": "Earth",
            "primary_purpose": "Flood Risk Reduction",
            "hazard_potential_classification": "High",
            "source_agency": "US Army Corps of Engineers",
            "eap_prepared": "Yes",
        }
        result = derived_properties(props)
        self.assertEqual(result, {
            "ffrd:flood_pool_fraction": 0.75,
            "ffrd:data_emergency_action_plan": True,
            "ffrd:data_operations_manual_likely": True,
            "ffrd:breach_structure_class": "EarthenDamLE30ft",
            "ffrd:recommended_breach_method": "SimplifiedPhysical",
            "ffrd_screening:size_class": "Small",
            "ffrd_screening:storage_class": "Significant",
            "ffrd_screening:flood_control_dominant": True,
            "ffrd_screening:hydrologic_influence": "Watershed",
            "ffrd_screening:major_flood_risk_infrastructure": True,
            "ffrd_screening:candidate_reservoir_operations_model": True,
            "ffrd_screening:candidate_for_breach_analysis": True,
            "ffrd_screening:recommended_hydraulic_type": "TypeA",
            "ffrd_screening:modeling_priority": 1,
        })
        props.update({
            "dam:structural_height_ft": 100,
            "dam:max_storage_acre_ft": 100000,
            "dam:normal_storage_acre_ft": 100000,
            "dam:drainage_area_sq_miles": 250,
            "primary_purpose": "Navigation",
            "hazard_potential_classification": "Low",
        })
        result = derived_properties(props)
        self.assertEqual(result["ffrd:breach_structure_class"], "EarthenDamGT30ft")
        self.assertEqual(result["ffrd:recommended_breach_method"], "UserDefined")
        self.assertEqual(result["ffrd_screening:size_class"], "Large")
        self.assertEqual(result["ffrd_screening:storage_class"], "Major")
        self.assertEqual(result["ffrd_screening:hydrologic_influence"], "Regional")
        self.assertEqual(result["ffrd_screening:recommended_hydraulic_type"], None)
        self.assertEqual(result["ffrd_screening:modeling_priority"], 2)
        self.assertFalse(result["ffrd_screening:flood_control_dominant"])

        props.update({
            "dam:structural_height_ft": 50,
            "dam:max_storage_acre_ft": 1000,
            "dam:normal_storage_acre_ft": 100,
            "dam:drainage_area_sq_miles": 0,
            "primary_dam_type": "Concrete",
            "source_agency": "Pennsylvania",
            "eap_prepared": "No",
        })
        result = derived_properties(props)
        self.assertEqual(result["ffrd:recommended_breach_method"], "FixedWidth")
        self.assertEqual(result["ffrd_screening:size_class"], "Medium")
        self.assertEqual(result["ffrd_screening:storage_class"], "Moderate")
        self.assertEqual(result["ffrd_screening:hydrologic_influence"], "Local")
        self.assertEqual(result["ffrd_screening:modeling_priority"], 3)
        self.assertFalse(result["ffrd:data_operations_manual_likely"])
        self.assertFalse(result["ffrd:data_emergency_action_plan"])

        props.update({
            "dam:structural_height_ft": None,
            "dam:max_storage_acre_ft": None,
            "dam:normal_storage_acre_ft": None,
            "dam:drainage_area_sq_miles": None,
            "primary_dam_type": "Earth",
            "primary_purpose": "Navigation",
            "hazard_potential_classification": "Low",
        })
        result = derived_properties(props)
        for key in (
            "ffrd:flood_pool_fraction", "ffrd:breach_structure_class",
            "ffrd:recommended_breach_method", "ffrd_screening:size_class",
            "ffrd_screening:storage_class", "ffrd_screening:flood_control_dominant",
            "ffrd_screening:hydrologic_influence", "ffrd_screening:modeling_priority",
            "ffrd_screening:candidate_for_breach_analysis",
            "ffrd_screening:major_flood_risk_infrastructure",
        ):
            self.assertIsNone(result[key], key)
        props["hazard_potential_classification"] = "High"
        self.assertTrue(derived_properties(props)["ffrd_screening:candidate_for_breach_analysis"])
        props["dam:max_storage_acre_ft"] = 0
        self.assertIsNone(derived_properties(props)["ffrd:flood_pool_fraction"])
        props["primary_dam_type"] = "Masonry"
        self.assertEqual(derived_properties(props)["ffrd:recommended_breach_method"], "UniqueCase")
        props.update({
            "dam:structural_height_ft": 31,
            "dam:drainage_area_sq_miles": 49,
            "hazard_potential_classification": "Undetermined",
        })
        result = derived_properties(props)
        self.assertEqual(result["ffrd_screening:modeling_priority"], 4)
        self.assertEqual(result["ffrd_screening:hydrologic_influence"], "Local")
        props["primary_dam_type"] = "Earth"
        self.assertEqual(derived_properties(props)["ffrd:breach_structure_class"], "EarthenDamGT30ft")


if __name__ == "__main__":
    unittest.main()
