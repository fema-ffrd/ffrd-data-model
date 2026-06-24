# ffrd-data-model
FFRD Data Model

## Entity Relationship Diagram(s)
* [FFRD Data Model - ERD](./rdb/ffrd-erd-unified.mmd)
* [FFRD Lakehouse Data Model - ERD](./lakehouse/ffrd-lakehouse.mmd)

## ETL Needs:
* code to load `storms` table from StormHub STAC (already part of StormHub itself, just needs to be uncommented manually)

## Notes / Questions
* MODEL LINKAGES
* gages: ams == annual maxmium series?
* fishnet: what is `weight`? importance sampling?
* reservoir, levee, and system response tables -- how is this supposed to work?

## Prior Art
![Iceberg Data Process](prior-art/iceberg-plugin-data-process.png)
![Iceberg Production Data](prior-art/iceberg-production-data.png)
