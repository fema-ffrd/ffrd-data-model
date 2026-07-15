# Data Dictionary — Derived Tables

Covers the eight materialized Iceberg tables modeled in `derived.mmd`. Keys are **logical** (not enforced by Iceberg).

> **Important:** These are derived/materialized tables regenerated from source-of-truth tables. They are lookup accelerators, not authoritative raw records. They are safe to fully regenerate when logic changes.
>
> **Primary sources:** `output_ts` (all variable summaries), `output_grids_repo` (grid-informed rollups), `run_catalog` (run metadata rollups).


## Tables and Fields

### Table: `derived_event_variable_summary`

TODO

> **Iceberg design:** partition `bucket(512, event_id)`, `variable`; sort `event_id`, `variable`, `run_type`, `run_version`.

| Column | Type | Source | Description |
|---|---|---|---|
| `event_id` | string | TODO | TODO |
| `variable` | string | TODO | TODO |
| `run_id` | string | TODO | TODO |
| `run_version` | int | TODO | TODO |
| `run_type` | string | TODO | TODO |
| `max_value` | float | TODO | TODO |
| `max_value_ts` | timestamp | TODO | TODO |
| `mean_value` | float | TODO | TODO |
| `p95_value` | float | TODO | TODO |
| `summary_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `derived_event_element_variable_summary`

TODO

> **Iceberg design:** partition `bucket(512, event_id)`, `variable`; sort `event_id`, `element_id`, `variable`, `run_type`, `run_version`.

| Column | Type | Source | Description |
|---|---|---|---|
| `event_id` | string | TODO | TODO |
| `element_id` | string | TODO | TODO |
| `variable` | string | TODO | TODO |
| `run_id` | string | TODO | TODO |
| `run_version` | int | TODO | TODO |
| `run_type` | string | TODO | TODO |
| `max_value` | float | TODO | TODO |
| `max_value_ts` | timestamp | TODO | TODO |
| `mean_value` | float | TODO | TODO |
| `p95_value` | float | TODO | TODO |
| `summary_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `derived_event_peak_by_variable`

TODO

> **Iceberg design:** partition `bucket(512, event_id)`, `variable`; sort `event_id`, `variable`, `run_type`, `run_version`.

| Column | Type | Source | Description |
|---|---|---|---|
| `event_id` | string | TODO | TODO |
| `variable` | string | TODO | TODO |
| `run_id` | string | TODO | TODO |
| `run_version` | int | TODO | TODO |
| `run_type` | string | TODO | TODO |
| `peak_value` | float | TODO | TODO |
| `peak_ts` | timestamp | TODO | TODO |
| `element_id_at_peak` | string | TODO | TODO |
| `summary_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `derived_event_element_peak`

TODO

> **Iceberg design:** partition `bucket(512, event_id)`, `variable`; sort `event_id`, `element_id`, `variable`, `run_type`, `run_version`.

| Column | Type | Source | Description |
|---|---|---|---|
| `event_id` | string | TODO | TODO |
| `element_id` | string | TODO | TODO |
| `variable` | string | TODO | TODO |
| `run_id` | string | TODO | TODO |
| `run_version` | int | TODO | TODO |
| `run_type` | string | TODO | TODO |
| `peak_value` | float | TODO | TODO |
| `peak_ts` | timestamp | TODO | TODO |
| `duration_above_threshold` | float | TODO | TODO |
| `summary_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `derived_event_model_rollup`

TODO

> **Iceberg design:** partition `bucket(512, event_id)`, `variable`; sort `event_id`, `model_id`, `variable`, `run_type`, `run_version`. Sourced from both `output_ts` and `output_grids_repo`.

| Column | Type | Source | Description |
|---|---|---|---|
| `event_id` | string | TODO | TODO |
| `model_id` | int | TODO | TODO |
| `variable` | string | TODO | TODO |
| `run_id` | string | TODO | TODO |
| `run_version` | int | TODO | TODO |
| `run_type` | string | TODO | TODO |
| `max_value` | float | TODO | TODO |
| `mean_value` | float | TODO | TODO |
| `p95_value` | float | TODO | TODO |
| `count_elements` | int | TODO | TODO |
| `summary_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `derived_event_window_rollup`

TODO

> **Iceberg design:** partition `bucket(512, event_id)`, `variable`; sort `event_id`, `element_id`, `variable`, `window_start`.

| Column | Type | Source | Description |
|---|---|---|---|
| `event_id` | string | TODO | TODO |
| `element_id` | string | TODO | TODO |
| `variable` | string | TODO | TODO |
| `run_id` | string | TODO | TODO |
| `run_version` | int | TODO | TODO |
| `run_type` | string | TODO | TODO |
| `window_start` | timestamp | TODO | TODO |
| `window_end` | timestamp | TODO | TODO |
| `window_max` | float | TODO | TODO |
| `window_mean` | float | TODO | TODO |
| `window_sum` | float | TODO | TODO |
| `summary_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `derived_run_catalog`

TODO

> **Iceberg design:** partition `run_type`; sort `run_type`, `model_id`, `started_at`. Sourced from `run_catalog`.

| Column | Type | Source | Description |
|---|---|---|---|
| `run_id` | string | TODO | TODO |
| `run_version` | int | TODO | TODO |
| `run_type` | string | TODO | TODO |
| `model_id` | int | TODO | TODO |
| `event_count` | int | TODO | TODO |
| `started_at` | timestamp | TODO | TODO |
| `ended_at` | timestamp | TODO | TODO |
| `status` | string | TODO | TODO |
| `code_ref` | string | TODO | TODO |
| `summary_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Table: `derived_latest_run_pointer`

TODO

> **Iceberg design:** partition `run_type`; sort `event_id`, `model_id`, `run_type`. Derived from `derived_run_catalog`. Provides a fast lookup for the latest run per event, model, and run type.

| Column | Type | Source | Description |
|---|---|---|---|
| `event_id` | string | TODO | TODO |
| `model_id` | int | TODO | TODO |
| `run_type` | string | TODO | TODO |
| `latest_run_id` | string | TODO | TODO |
| `latest_run_version` | int | TODO | TODO |
| `updated_ts` | timestamp | TODO | TODO |
| `source_system` | string | TODO | TODO |


### Common Metadata Fields

These fields are present on all derived tables.

| Column | Type | Description |
|--------|------|-------------|
| `summary_ts` | timestamp | Datetime when the derived record was last computed or refreshed |
| `source_system` | string | Identifier of the upstream system or pipeline that produced this record |


## Relationships

- `output_ts` is the primary source for all variable summary tables (`derived_event_variable_summary`, `derived_event_element_variable_summary`, `derived_event_peak_by_variable`, `derived_event_element_peak`, `derived_event_window_rollup`).
- `output_grids_repo` contributes to `derived_event_model_rollup` alongside `output_ts`.
- `run_catalog` is the authoritative source for `derived_run_catalog`.
- `derived_run_catalog` is the source for `derived_latest_run_pointer`.


## Join Intent

| Child Column | Joins To |
|---|---|
| `derived_event_*` columns `event_id` | `events.event_id` (see events schema) |
| `derived_event_*` columns `element_id` | `model_elements.element_id` (see models schema) |
| `derived_event_*` columns `run_id` | `run_catalog.run_id` (see models schema) |
| `derived_event_model_rollup.model_id` | `models.model_id` (see models schema) |
| `derived_run_catalog.run_id` | `run_catalog.run_id` (see models schema) |
| `derived_latest_run_pointer.latest_run_id` | `run_catalog.run_id` (see models schema) |


## Notes

- **No enforced constraints.** These are Iceberg tables; PKs and FKs are logical conventions only.
- **Not source of truth.** All derived tables are regenerated from `output_ts`, `output_grids_repo`, and `run_catalog`. Do not treat them as authoritative raw records.
- **Rebuild cadence.** Incremental by `run_id` per completed run or by run batch (TBD). Late data is handled by overwrite/merge keyed on `run_id` + `run_version`.
- **`summary_ts` vs `ingest_ts`.** Derived tables use `summary_ts` (the time the aggregation was computed) instead of `ingest_ts` used in source tables.
- **`duration_above_threshold` units.** Units for `derived_event_element_peak.duration_above_threshold` are TBD (TODO).


## Schema Diagram

[lakehouse/derived.mmd](../lakehouse/derived.mmd) — renders as a Mermaid ER diagram (GitHub displays `.mmd` files natively).
