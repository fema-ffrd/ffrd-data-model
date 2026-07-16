# Data Dictionary — Models

Covers the eight Iceberg tables modeled in `models.mmd`. Keys are **logical** (not enforced by Iceberg).

> **Note:** `derived_tables` appears as a placeholder node in `models.mmd` to show lineage. Those tables are fully documented in [derived-dictionary.md](derived-dictionary.md).


## Tables and Fields

### Table: `models`

TODO

| Column | Type | Source | Description |
|---|---|---|---|
| `model_id` | int | TODO | TODO |
| `model_type` | string | TODO | TODO |
| `model_version` | string | TODO | TODO |
| `model_name` | string | TODO | TODO |
| `geom_wkt` | geom | TODO | TODO |
| `ingest_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `model_elements`

TODO

| Column | Type | Source | Description |
|---|---|---|---|
| `element_id` | string | TODO | TODO |
| `model_id` | int | TODO | TODO |
| `structure_id` | string | TODO | TODO |
| `structure_type` | string | TODO | Discriminator for `structure_id` resolution. Allowed values: `dam`, `levee`, `building`. Null when the element has no structure association (e.g., gage-only elements) |
| `gage_id` | string | TODO | TODO |
| `element` | string | TODO | TODO |
| `geom_wkt` | geom | TODO | TODO |
| `ingest_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `model_event_files`

TODO

| Column | Type | Source | Description |
|---|---|---|---|
| `model_event_file_id` | string | TODO | TODO |
| `model_id` | int | TODO | TODO |
| `event_id` | string | TODO | TODO |
| `object_uri` | string | TODO | TODO |
| `file_format` | string | TODO | TODO |
| `metadata_json` | string | TODO | TODO |
| `ingest_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `run_catalog`

TODO

| Column | Type | Source | Description |
|---|---|---|---|
| `run_id` | string | TODO | TODO |
| `run_version` | int | TODO | TODO |
| `run_type` | string | TODO | TODO |
| `model_id` | int | TODO | TODO |
| `started_at` | timestamp | TODO | TODO |
| `ended_at` | timestamp | TODO | TODO |
| `status` | string | TODO | TODO |
| `trigger` | string | TODO | TODO |
| `code_ref` | string | TODO | TODO |
| `ingest_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `output_ts`

TODO

> **Iceberg design:** partition `bucket(512, event_id)`, `run_type`; sort `event_id`, `element_id`, `variable`, `ts`. Optimizes full-series reads per event and element across 20k–200k events.

| Column | Type | Source | Description |
|---|---|---|---|
| `event_id` | string | TODO | TODO |
| `element_id` | string | TODO | TODO |
| `model_id` | int | TODO | TODO |
| `run_id` | string | TODO | TODO |
| `run_version` | int | TODO | TODO |
| `ts` | timestamp | TODO | TODO |
| `variable` | string | TODO | TODO |
| `value` | float | TODO | TODO |
| `units` | string | TODO | TODO |
| `run_type` | string | TODO | TODO |
| `ingest_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `output_grids_repo`

TODO

> **Iceberg design:** partition `bucket(512, event_id)`, `run_type`; sort `event_id`, `element_id`, `variable`, `ts`. Stores metadata pointers to Icechunk repositories/snapshots. `snapshot_ref` is an immutable content-addressed snapshot ID, or a stable tag/branch name resolved at read time.

| Column | Type | Source | Description |
|---|---|---|---|
| `event_id` | string | TODO | TODO |
| `element_id` | string | TODO | TODO |
| `model_id` | int | TODO | TODO |
| `run_id` | string | TODO | TODO |
| `run_version` | int | TODO | TODO |
| `ts` | timestamp | TODO | TODO |
| `variable` | string | TODO | TODO |
| `units` | string | TODO | TODO |
| `run_type` | string | TODO | TODO |
| `icechunk_repository_uri` | string | TODO | TODO |
| `dataset_path` | string | TODO | TODO |
| `snapshot_ref` | string | TODO | TODO |
| `metadata_json` | string | TODO | TODO |
| `ingest_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `gages`

TODO

| Column | Type | Source | Description |
|---|---|---|---|
| `gage_id` | string | TODO | TODO |
| `gage_name` | string | TODO | TODO |
| `gage_owner` | string | TODO | TODO |
| `ams_json` | string | TODO | TODO |
| `geom_wkt` | geom | TODO | TODO |
| `ingest_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `obs_ts`

TODO

> **Iceberg design:** partition `bucket(256, gage_id)`, `months(ts)`; sort `gage_id`, `variable`, `ts`.

| Column | Type | Source | Description |
|---|---|---|---|
| `gage_id` | string | TODO | TODO |
| `ts` | timestamp | TODO | TODO |
| `variable` | string | TODO | TODO |
| `value` | float | TODO | TODO |
| `units` | string | TODO | TODO |
| `ingest_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Common Metadata Fields

These fields are present on all tables.

| Column | Type | Description |
|--------|------|-------------|
| `ingest_ts` | timestamp | Datetime when the record was updated in the database |
| `source_system` | string | Identifier of the upstream system or pipeline that produced this record |


## Relationships

- Each **model** contains one or many **model_elements**.
- Each **model_element** may optionally map to a **gage** or a **structure** (from the structures schema).
- Each **gage** may have zero or many **obs_ts** rows, one per variable and timestamp.
- Each **event** may have zero or many **output_ts** rows and zero or many **output_grids_repo** rows.
- Each **run_catalog** entry tracks one execution run and links to **output_ts** and **output_grids_repo** rows produced by that run.
- Each **model** and **event** pair may have zero or many **model_event_files** artifacts.


## Join Intent

| Child Column | Joins To |
|---|---|
| `model_elements.model_id` | `models.model_id` |
| `model_elements.gage_id` | `gages.gage_id` |
| `model_elements.structure_id` | `dams.dam_id`, `levees.levee_id`, or `buildings.building_id` (see structures schema; resolved by `model_elements.structure_type`) |
| `model_event_files.model_id` | `models.model_id` |
| `model_event_files.event_id` | `events.event_id` (see events schema) |
| `run_catalog.model_id` | `models.model_id` |
| `output_ts.event_id` | `events.event_id` (see events schema) |
| `output_ts.element_id` | `model_elements.element_id` |
| `output_ts.model_id` | `models.model_id` (denormalized) |
| `output_ts.run_id` | `run_catalog.run_id` |
| `output_grids_repo.event_id` | `events.event_id` (see events schema) |
| `output_grids_repo.element_id` | `model_elements.element_id` |
| `output_grids_repo.model_id` | `models.model_id` (denormalized) |
| `output_grids_repo.run_id` | `run_catalog.run_id` |
| `obs_ts.gage_id` | `gages.gage_id` |


## Notes

- **No enforced constraints.** These are Iceberg tables; PKs and FKs are logical conventions only.
- **Run semantics.** `run_id` is an immutable execution identifier. `run_version` is a monotonic rerun counter for the same logical run.
- **Denormalized `model_id`.** `output_ts` and `output_grids_repo` carry `model_id` directly to accelerate model-scoped queries without joining through `model_elements`.
- **Derived tables.** `derived_tables` in `models.mmd` is a lineage placeholder. See [derived-dictionary.md](derived-dictionary.md) for full documentation.
- **CRS.** All WKT geometry columns are assumed WGS 84 (EPSG:4326) unless the `source_system` pipeline documents otherwise. (TODO)


## Schema Diagram

[lakehouse/models.mmd](../lakehouse/models.mmd) — renders as a Mermaid ER diagram (GitHub displays `.mmd` files natively).
