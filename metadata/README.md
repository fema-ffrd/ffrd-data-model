# Metadata

This folder contains metadata examples, schema/profile guidance, and utility scripts.

## Directories

| Directory | Purpose |
|---|---|
| examples/ | Example STAC catalogs, collections, and items used as reference artifacts. |
| schemas/ | YAML profile definitions and related metadata conventions. |
| utils/ | Utility scripts for generating and updating STAC metadata artifacts. |

Utility note: [build_portable_geoparquet_collection.py](utils/portable-collection/build_portable_geoparquet_collection.py) is a general-purpose utility for building portable GeoParquet collections from STAC metadata and is not specific to a single dataset profile.

## Schema Conventions

- Prefer native property names as they appear in STAC examples.
- Do not restate mandatory STAC core fields.
- Split guidance into `required` and `recommended` sections.
- Add short descriptions for each recommended property.
- Keep link and asset constraints explicit and plain-language.

## Shared Properties

Shared properties are defined by [global.profile.yaml](schemas/global.profile.yaml).

| Scope | Shared properties |
|---|---|
| Collection and Item | version, deprecated |
| Item | zip:* (including zip_member_count) |

## Profile Inventory

| Category | Profile ID | File | Example(s) | Utility |
|---|---|---|---|---|
| Global | global-shared-properties | [global.profile.yaml](schemas/global.profile.yaml) | [catalog.json](examples/catalog.json) | — |
| Dataset | calibration | [calibration.profile.yaml](schemas/calibration.profile.yaml) | [collection-v1.0.json](examples/calibration/collection-v1.0.json) | [update_stac_with_parquet.py](utils/models/update_stac_with_parquet.py) |
| Dataset | conformance | [conformance.profile.yaml](schemas/conformance.profile.yaml) | [collection-v0.1.json](examples/conformance/collection-v0.1.json) | — |
| Model | models-ras | [ras.profile.yaml](schemas/models/ras.profile.yaml) | [big-thompson-ras-v1.0.json](examples/calibration/hydraulics/big-thompson/v1.0/big-thompson-ras-v1.0.json) | [create_ras_stac.py](utils/models/create_ras_stac.py) |
| Model | models-hms | [hms.profile.yaml](schemas/models/hms.profile.yaml) | [big-thompson-hms-v1.0.json](examples/calibration/hydrology/big-thompson/v1.0/big-thompson-hms-v1.0.json) | [create_hms_stac.py](utils/models/create_hms_stac.py) |
| Model | models-ressim | [ressim.profile.yaml](schemas/models/ressim.profile.yaml) | — | — |
| Basin data | basin-data-terrain | [basin-data-terrain.profile.yaml](schemas/basin-data-terrain.profile.yaml) | [collection-v1.0.json](examples/terrain-base/test-96ft-v1.0/collection-v1.0.json) | [s3-stac_item_from_tiff.py](utils/terrain/s3-stac_item_from_tiff.py) |
| Basin data | basin-data-dams | [basin-data-dams.profile.yaml](schemas/basin-data-dams.profile.yaml) | [0501_allegheny_nid-dams.geojson](examples/dams/0501_allegheny_nid-dams.geojson) | [create_nid_collection.py](utils/dams/create_nid_collection.py), [create_lhdi_collection.py](utils/dams/create_lhdi_collection.py) |
| Basin data | basin-data-levees | [basin-data-levees.profile.yaml](schemas/basin-data-levees.profile.yaml) | — | — |
| Basin data | basin-data-fishnet | [basin-data-fishnet.profile.yaml](schemas/basin-data-fishnet.profile.yaml) | — | — |
| Basin data | basin-data-lulc | [basin-data-lulc.profile.yaml](schemas/basin-data-lulc.profile.yaml) | [collection-v0.1.json](examples/basin-data/landcover/collection-v0.1.json) | [create_basin_data_stac.py](utils/basin-data/create_basin_data_stac.py) |
| Basin data | basin-data-soils | [basin-data-soils.profile.yaml](schemas/basin-data-soils.profile.yaml) | [collection-v0.1.json](examples/basin-data/soils/collection-v0.1.json) | [create_basin_data_stac.py](utils/basin-data/create_basin_data_stac.py) |
| Basin data | basin-data-stream-gages | [basin-data-stream-gages.profile.yaml](schemas/basin-data-stream-gages.profile.yaml) | [collection-v1.0.json](examples/basin-data/stream-gages/collection-v1.0.json) | [create_basin_data_stac.py](utils/basin-data/create_basin_data_stac.py) |
| Basin data | basin-data-storm-catalog | [basin-data-storm-catalog.profile.yaml](schemas/basin-data-storm-catalog.profile.yaml) | [collection-v1.0.json](examples/basin-data/storm-catalog/collection-v1.0.json) | [create_basin_data_stac.py](utils/basin-data/create_basin_data_stac.py) |
| Basin data | basin-data-fema | [basin-data-fema.profile.yaml](schemas/basin-data-fema.profile.yaml) | [collection-v1.0.json](examples/basin-data/fema/collection-v1.0.json) | [create_basin_data_stac.py](utils/basin-data/create_basin_data_stac.py) |
| Basin data | basin-data-government-boundaries | [basin-data-government-boundaries.profile.yaml](schemas/basin-data-government-boundaries.profile.yaml) | [collection-v1.0.json](examples/basin-data/government-boundaries/collection-v1.0.json) | [create_basin_data_stac.py](utils/basin-data/create_basin_data_stac.py) |
| Basin data | basin-data-nhd | [basin-data-nhd.profile.yaml](schemas/basin-data-nhd.profile.yaml) | [collection-v1.0.json](examples/basin-data/nhd/collection-v1.0.json) | [create_basin_data_stac.py](utils/basin-data/create_basin_data_stac.py) |
| Basin data | basin-data-structure-inventory | [basin-data-structure-inventory.profile.yaml](schemas/basin-data-structure-inventory.profile.yaml) | [collection-v1.0.json](examples/basin-data/structure-inventory/collection-v1.0.json) | — |
| Basin data | basin-data-transportation | [basin-data-transportation.profile.yaml](schemas/basin-data-transportation.profile.yaml) | [collection-v1.0.json](examples/basin-data/transportation/collection-v1.0.json) | [create_basin_data_stac.py](utils/basin-data/create_basin_data_stac.py) |
