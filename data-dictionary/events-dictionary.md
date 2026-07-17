# Data Dictionary — Events

Covers the four Iceberg tables modeled in `events.mmd`. Keys are **logical** (not enforced by Iceberg).


## Tables and Fields
### Table: `storms`

Catalog of historic observed storms used as forcing inputs.

| Column | Type | Source | Description |
|---|---|---|---|
| `storm_id` | string | TODO | Logical primary key. Unique identifier for a single observed storm. |
| `storm_rank` | int | TODO | Rank of this observed storm (1 being the highest) based on maximum total precipitation depth (TODO: confirm). |
| `storm_type` | string | TODO | Meteorological type of the storm (e.g., tropical, MCS, etc.) |
| `datetime` | timestamp | TODO | UTC timestamp of the storm's reference time (i.e. start of event). |
| `duration_hrs` | int | TODO | Total storm duration in hours. |
| `centroid` | geom | TODO | Point geometry representing the storm centroid in its original (pre-transposition) location. CRS: WGS 84 (TODO: confirm). |
| `mean_precip` | float | TODO | Spatial mean precipitation over the study domain for this storm. Units: inches (TODO: confirm).  |


### Table: `fishnet_points`

Regular-grid sample locations used to define transposition target points across the study domain. Each row is a unique spatial sample location.

| Column | Type | Source | Description |
|---|---|---|---|
| `fishnet_point_id` | string | TODO | Logical primary key. Unique identifier for a fishnet grid point. |
| `weight` | float | TODO | Relative sampling weight of this fishnet grid point based on importance sampling analysis. (TODO: confirm) |
| `geom` | string | TODO | Point geometry for this grid location. CRS assumed WGS 84 unless documented otherwise. CRS: WGS 84 (TODO) |


### Table: `events`

Transposed storm events Each row is one stochastic event instance.

| Column | Type | Source | Description |
|---|---|---|---|
| `event_id` | string | TODO | Logical primary key. Unique identifier for this transposed event instance. |
| `storm_id` | string | TODO | Logical foreign key. Identifies the source storm. |
| `fishnet_point_id` | string | TODO | Logical foriegn key. Identifies the transposition target location. |
| `event_type` | string | TODO | One of: `conformance`, `calibration`, etc. (TODO: confirm / list all) |
| `block_id` | int | TODO | Block index of the Event  |
| `realization_id` | int | TODO | Realization index of the Event  |
| `centroid_trnsp_wkt` | geom | TODO | Point geometry of the storm centroid **after** transposition to the fishnet target location. CRS: WGS 84 (TODO: confirm). |
| `event_date` | date | TODO | Calendar date associated with the event (e.g. synthetic date assigned for model forcing). |


### Table: `event_seeds`

Stochastic seed values used to reproduce individual event realizations.

| Column | Type | Source | Description |
|---|---|---|---|
| `event_id` | string | TODO | Logical foreign key. Identifies the parent event. |
| `process_id` | int | TODO | Is this CC Plugin ID? (TODO)|
| `realization_seed` | int | TODO | Realization seed value for the Event. |
| `block_seed` | int | TODO | Block seed value for the Event. |
| `event_seed` | int | TODO | Event seed value. |

### Common Metadata Fields

These fields are present on all tables.

| Column | Type | Description |
---------|------|-------------|
| `ingest_ts` | timestamp | Datetime when the record was updated in the database |
| `source_system` | string | Identifier of the upstream system or pipeline that produced this record |


## Relationships

- Each **storm** may be associated with zero or many **events** (one per transposition target location and realization).
- Each **fishnet point** may serve as the target location for zero or many **events**.
- Each **event** may have zero or many **event_seeds** rows, one per sub-process involved in generating that event.

## Join Intent

| Child Column | Joins To |
|---|---|
| `events.storm_id` | `storms.storm_id` |
| `events.fishnet_point_id` | `fishnet_points.fishnet_point_id` |
| `event_seeds.event_id` | `events.event_id` |

## Notes

- **No enforced constraints.** These are Iceberg tables; PKs and FKs are logical conventions only.
- **CRS.** All WKT geometry columns are assumed WGS 84 (EPSG:4326) unless the `source_system` pipeline documents otherwise. (TODO)
- **Seed hierarchy.** Needs investigation into realization_seed, block_seed, and event_seed definitions (TODO)
