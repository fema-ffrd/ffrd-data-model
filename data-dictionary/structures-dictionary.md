# Data Dictionary — Structures

Covers the four Iceberg tables modeled in `structures.mmd`. Keys are **logical** (not enforced by Iceberg).


## Tables and Fields

### Table: `dams`

TODO

| Column | Type | Source | Description |
|---|---|---|---|
| `dam_id` | string | TODO | TODO |
| `location` | string | TODO | TODO |
| `nid_id` | string | TODO | TODO |
| `nid_dam_name` | string | TODO | TODO |
| `top_elev` | float | TODO | TODO |
| `toe_elev` | float | TODO | TODO |
| `source` | string | TODO | TODO |
| `ingest_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `levees`

TODO

| Column | Type | Source | Description |
|---|---|---|---|
| `levee_id` | string | TODO | TODO |
| `location` | string | TODO | TODO |
| `breach_fid` | string | TODO | TODO |
| `nld_system_id` | string | TODO | TODO |
| `nld_system_name` | string | TODO | TODO |
| `nld_segment_id` | string | TODO | TODO |
| `top_elev` | float | TODO | TODO |
| `toe_elev` | float | TODO | TODO |
| `source` | string | TODO | TODO |
| `ingest_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `structure_response_curves`

TODO

| Column | Type | Source | Description |
|---|---|---|---|
| `structure_response_id` | string | TODO | TODO |
| `structure_type` | string | TODO | TODO |
| `structure_location_id` | string | TODO | TODO |
| `failure_mode` | string | TODO | TODO |
| `source` | string | TODO | TODO |
| `point_order` | int | TODO | TODO |
| `probability` | float | TODO | TODO |
| `distribution_type` | string | TODO | TODO |
| `distribution_params_json` | string | TODO | TODO |
| `stage_value` | float | TODO | TODO |
| `ingest_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `structure_failure_elev`

TODO

| Column | Type | Source | Description |
|---|---|---|---|
| `structure_response_id` | string | TODO | TODO |
| `event_id` | string | TODO | TODO |
| `failure_elev` | float | TODO | TODO |
| `ingest_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `buildings`

Building inventory records derived from NSI-style and Milliman-style datasets. Each row represents one structure (building) at a fixed geographic location. This table is the primary input for consequence modeling workflows and is a standalone reference entity in the Structures domain, peer to `dams` and `levees`.

> **Iceberg design:** partition `state_fips` (identity); sort `state_fips`, `county_fips`, `building_id`. For study-domain-scoped deployments (pre-filtered to a watershed), `bucket(128, building_id)` is an appropriate alternative.

| Column | Type | Required | Source (NSI Public → NSI Enhanced → Milliman) | Description |
|---|---|---|---|---|
| `building_id` | string | **Required** | Surrogate | Logical PK. Synthetic unique key. Recommended format: `{inventory_source}_{source_building_id}` |
| `source_building_id` | string | **Required** | `fd_id` → `OBJECTID` → `Location`/`location` | Original identifier from the source dataset before any transformation |
| `inventory_source` | string | **Required** | ETL | Source dataset type. Allowed values: `NSI_PUBLIC_2022`, `NSI_ENHANCED_2022`, `MILLIMAN_UNIFORM_2021`, `MILLIMAN_UNCORRELATED_2021`, `USER_DEFINED` |
| `inventory_version` | string | Optional | ETL | Version label of the source dataset (e.g., `"2022"`) |
| `latitude` | double | **Required** | `y` → `y` → `LAT` | Latitude in decimal degrees, WGS84 (EPSG:4326) |
| `longitude` | double | **Required** | `x` → `x` → `LON` | Longitude in decimal degrees, WGS84 (EPSG:4326) |
| `geom_wkt` | string | Optional | Derived | WKT POINT geometry derived from `latitude`/`longitude`. Follows the `geom_wkt` pattern used in `models` and `gages` |
| `state_fips` | string | Optional | Derived from `cbfips` / geocode | 2-digit state FIPS code. Primary Iceberg partition key |
| `county_fips` | string | Optional | First 5 chars of `cbfips` / geocode | 5-digit county FIPS code |
| `census_block_fips` | string | Optional | `cbfips` → `cbfips` → — | Full 15-digit census block FIPS code. NSI only |
| `occupancy_type` | string | Optional (default: `RES1`) | `occtype` → `OCCTYPE` → all `RES1` | HAZUS occupancy classification code (e.g., `RES1`, `COM1`, `IND2`). Drives depth-damage function selection in consequence modeling |
| `general_building_type` | string | Optional (default: `W`) | `bldgtype` → `GENERALBUILDINGTYPE` → `CONSTR_CODE` (1→`W`, 2→`M`) | Construction material code: `W`=Wood, `M`=Masonry, `C`=Concrete, `S`=Steel, `MH`=Mobile Home |
| `number_stories` | int | Optional (default: `1`) | `num_story` → `NUM_STORY` → `NUM_STORIES`/`NUM_STORIE` | Number of above-grade stories. For RES1 depth-damage functions, effective max is 3 |
| `area_sqft` | double | Optional (Hazus default by occupancy type) | `sqft` → `SQFT` → default `1800` for RES1 | Building floor area in square feet |
| `foundation_type` | string | Optional (default: `SLAB`) | `found_type` → `FNDTYPE` + parcel refinement → `foundationtype`/`foundation` | Standardized foundation type. Allowed values: `PILE`, `SHALLOW`, `BASEMENT`, `SLAB`. Raw source codes are mapped during ETL; see the [inland-consequences foundation type mapping tables](https://fema-ffrd.github.io/inland-consequences/building_inventories/) |
| `first_floor_height_ft` | double | Optional (default by foundation type) | `found_ht` → `FOUND_HT` → `FIRST_FLOOR_ELEV`/`FIRST_FLOO` | Height of first floor above ground elevation in feet. Defaults: `SLAB`=1 ft, `SHALLOW`=3 ft, `PILE`=8 ft, `BASEMENT`=2 ft |
| `basement_type` | int | Optional (default: `0`) | Derived | Basement finish type: `0`=no basement, `1`=unfinished, `2`=finished. Milliman source field: `BasementFinishType`/`BasementFi` |
| `building_cost` | double | **Required** | `val_struct` (depreciated) → `Hazus_Building_Values` (full replacement) → `BLDG_VALUE` (full replacement) | Building structural replacement cost in USD. NSI Public uses depreciated values; NSI Enhanced and Milliman use full replacement cost |
| `content_cost` | double | Optional (default: percentage of `building_cost` by occupancy type) | `val_cont` → `Hazus_Content_Values` → `CNT_VALUE` | Contents replacement cost in USD. Hazus default: 50% of `building_cost` for RES1 |
| `inventory_cost` | double | Optional | `val_inv` (if present) → — → — | Business inventory replacement cost in USD. Applicable to non-residential occupancies |
| `bldg_insurance_deductible` | double | Optional | — → — → `BLDG_DED` | Building insurance deductible in USD. Milliman only; not used in loss calculations |
| `bldg_insurance_limit` | double | Optional | — → — → `BLDG_LIMIT` | Building insurance limit in USD. Milliman only; not used in loss calculations |
| `content_insurance_deductible` | double | Optional | — → — → `CNT_DED` | Content insurance deductible in USD. Milliman only; not used in loss calculations |
| `content_insurance_limit` | double | Optional | — → — → `CNT_LIMIT` | Content insurance limit in USD. Milliman only; not used in loss calculations |
| `ground_elevation_ft` | double | Coastal: **Required** / Inland: Optional | `Ground_elv` (coastal) → — → `elev_ft` (inland CSV) / `DEMft` (coastal SHP) | Ground surface elevation in feet, NAVD88 datum. Required for coastal consequence analysis |
| `pop_2am` | int | Optional | `pop2amu65 + pop2amo65` → same → — | Total estimated building occupancy at 2:00 AM. Derived sum of age brackets. NSI only |
| `pop_2pm` | int | Optional | `pop2pmu65 + pop2pmo65` → same → — | Total estimated building occupancy at 2:00 PM. Derived sum of age brackets. NSI only |
| `pop_2am_under65` | int | Optional | `pop2amu65` → same → — | 2:00 AM population under age 65. NSI only |
| `pop_2am_over65` | int | Optional | `pop2amo65` → same → — | 2:00 AM population age 65 and older. NSI only |
| `pop_2pm_under65` | int | Optional | `pop2pmu65` → same → — | 2:00 PM population under age 65. NSI only |
| `pop_2pm_over65` | int | Optional | `pop2pmo65` → same → — | 2:00 PM population age 65 and older. NSI only |
| `raw_attributes_json` | string | Optional | All source fields | JSON blob of original source field values before mapping and imputation. Supports audit, data lineage tracing, and reprocessing without re-ingestion. Pattern consistent with `distribution_params_json` in `structure_response_curves` and `metadata_json` in `output_grids_repo` |
| `source` | string | Optional | Source dataset authority | Data provenance label for the originating authority (e.g., `USACE_NSI`, `MILLIMAN_INC`). Distinct from `source_system` (the ETL pipeline). Analogous to `dams.source` and `levees.source` |
| `ingest_ts` | timestamp | **Required** | ETL | Datetime when the record was written to the lakehouse |
| `source_system` | string | **Required** | ETL | ETL pipeline identifier |


### Common Metadata Fields

These fields are present on all tables.

| Column | Type | Description |
|--------|------|-------------|
| `ingest_ts` | timestamp | Datetime when the record was updated in the database |
| `source_system` | string | Identifier of the upstream system or pipeline that produced this record |


## Relationships

- Each **dam** may be associated with zero or many **structure_response_curves** (one per failure mode and curve definition).
- Each **levee** may be associated with zero or many **structure_response_curves**.
- Each **event** may be associated with zero or many **structure_failure_elev** rows, one per structure response curve sampled for that event.
- Each **structure_response_curve** may produce zero or many **structure_failure_elev** rows across events.
- Each **building** may be registered as zero or many **model_elements** (via `model_elements.structure_id = buildings.building_id`, disambiguated by `model_elements.structure_type = 'building'`).


## Join Intent

| Child Column | Joins To |
|---|---|
| `structure_response_curves.structure_location_id` | `dams.dam_id` or `levees.levee_id` (see `structure_type` on `structure_response_curves`) |
| `structure_failure_elev.structure_response_id` | `structure_response_curves.structure_response_id` |
| `structure_failure_elev.event_id` | `events.event_id` (see events schema) |
| `model_elements.structure_id` | `dams.dam_id`, `levees.levee_id`, or `buildings.building_id` (resolved by `model_elements.structure_type`; see models schema) |


## Notes

- **No enforced constraints.** These are Iceberg tables; PKs and FKs are logical conventions only.
- **`source` vs `source_system`.** These are two distinct columns with different meanings:
  - `source` is a **data provenance field** inherent to the structure record itself — it identifies the origin dataset or authority for that structure's attributes (e.g., NID, NLD, a study-specific dataset).
  - `source_system` is a **pipeline metadata field** that identifies the upstream ETL system or ingestion pipeline that wrote the record into this table.
- **`structure_response_curves` grain.** Each row is a single point on a probability–stage response curve. `point_order` defines the sequence within a curve. Multiple rows with the same `structure_response_id` together form one complete curve.
- **`structure_type` routing on `structure_response_curves`.** Use `structure_response_curves.structure_type` to determine whether `structure_location_id` resolves against `dams.dam_id` or `levees.levee_id`.
- **`buildings` consequence modeling flow.** The `buildings` table is the input inventory for consequence analysis. Results flow as: `buildings` → `model_elements` (element registration) → `output_ts` (per-event flood depth/loss variables) → derived tables (peak depth, loss aggregations). Loss variable names such as `building_loss` and `content_loss` are stored as `output_ts.variable` values; they are not columns on the `buildings` table itself.
- **NSI Public depreciated vs. replacement cost.** The `building_cost` field in NSI Public records represents depreciated replacement value, not full replacement cost. NSI Enhanced and Milliman records use full replacement cost. ETL pipelines should record the cost basis in `inventory_source` and preserve original values in `raw_attributes_json`.
- **NSI Enhanced parcel fields.** `P_FNDTYPE` and `P_BSMNT` from the FEMA-Enhanced NSI are used only during ETL-time foundation type imputation. They are not stored as typed columns; they should be preserved in `raw_attributes_json` for reprocessing traceability.
- **Milliman scope.** Milliman Market Basket records are limited to single-family residential (`RES1`) structures. All Milliman rows will have `occupancy_type = 'RES1'`.
- **CRS.** `geom_wkt` is WGS84 (EPSG:4326). `ground_elevation_ft` is NAVD88 vertical datum.


## Schema Diagram

[lakehouse/structures.mmd](../lakehouse/structures.mmd) — renders as a Mermaid ER diagram (GitHub displays `.mmd` files natively).
