# ffrd-data-model
FFRD Data Model
```mermaid
erDiagram
    fishnet }o--o{ transposed_storms : blah

    blocks_seeds {
        realization_id int
        block_id int
        plugin_id int
        model_id int
        seed int
    }
    gages {
        gage_id int
        gage_name str
        gage_owner str
        ams array
        geom geom
    }
    storms {
        storm_id int
        storm_rank int
        storm_type str
        storm_centroid geom
        mean_precip float
    }
    fishnet {
        fishnet_point_id int
        weight float
        geom geom
    }
    transposed_storms {
        event_id int
        storm_id int
        fishnet_point_id int
    }

```

## ETL Needs:
* code to load `storms` table from StormHub STAC (already part of StormHub itself, just needs to be uncommented manually)

## Notes / Questions
* gages: ams == annual maxmium series? 
* fishnet: what is `weight`? importance sampling?
* are we actually duplicating the 
