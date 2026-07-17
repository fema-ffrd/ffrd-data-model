# ffrd-data-model
FFRD Data Model

## Entity Relationship Diagram(s)
* [FFRD Data Model - ERD](./rdb/ffrd-erd-unified.mmd)
* [FFRD Data Model - Grids Detail](./rdb/grids.mmd)
* [FFRD Lakehouse Data Model - ERD](./lakehouse/ffrd-lakehouse.mmd)

## ETL Needs:
* code to load `storms` table from StormHub STAC (already part of StormHub itself, just needs to be uncommented manually)

## Notes / Questions
* MODEL LINKAGES
* gages: ams == annual maxmium series?
* fishnet: what is `weight`? importance sampling?
* reservoir, levee, and system response tables -- how is this supposed to work?
* Gridded data (RAS depth/velocity, HMS excess precip, observed precip) is cataloged in
  [`rdb/grids.mmd`](./rdb/grids.mmd) rather than stored in relational tables. Each domain
  is backed by one long-lived Icechunk repository that accumulates snapshots over time
  (not one repo per run/event); the `grids` table holds catalog/pointer rows (one per
  variable per `event` or `storm`) into the shared repo. For model outputs (RAS/HMS),
  each grid is merged across all runs for a given event. Transposed/event-specific
  precipitation is computed at runtime from the storm-level grid and is not persisted
  separately.

## Prior Art
![Iceberg Data Process](prior-art/iceberg-plugin-data-process.png)
![Iceberg Production Data](prior-art/iceberg-production-data.png)
