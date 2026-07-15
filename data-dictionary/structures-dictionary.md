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


## Join Intent

| Child Column | Joins To |
|---|---|
| `structure_response_curves.structure_location_id` | `dams.dam_id` or `levees.levee_id` (see `structure_type`) |
| `structure_failure_elev.structure_response_id` | `structure_response_curves.structure_response_id` |
| `structure_failure_elev.event_id` | `events.event_id` (see events schema) |


## Notes

- **No enforced constraints.** These are Iceberg tables; PKs and FKs are logical conventions only.
- **`source` vs `source_system`.** These are two distinct columns with different meanings:
  - `source` is a **data provenance field** inherent to the structure record itself — it identifies the origin dataset or authority for that structure's attributes (e.g., NID, NLD, a study-specific dataset).
  - `source_system` is a **pipeline metadata field** that identifies the upstream ETL system or ingestion pipeline that wrote the record into this table.
- **`structure_response_curves` grain.** Each row is a single point on a probability–stage response curve. `point_order` defines the sequence within a curve. Multiple rows with the same `structure_response_id` together form one complete curve.
- **`structure_type` routing.** Use `structure_type` to determine whether `structure_location_id` resolves against `dams.dam_id` or `levees.levee_id`.
- **CRS.** No geometry columns are present in this schema. Structure locations are referenced by ID and resolved through the models schema (`model_elements`).


## Schema Diagram

[lakehouse/structures.mmd](../lakehouse/structures.mmd) — renders as a Mermaid ER diagram (GitHub displays `.mmd` files natively).
