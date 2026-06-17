# ffrd-data-model
FFRD Data Model

## Entity Relationship Diagram
```mermaid
erDiagram
    events ||--|{ seeds : "random"
    events }o--|| storms : "random"
    events }o--|| fishnet_points : "random"
    models }o--o{ por_events : "POR simulations"
    por_events ||--o{ por_output_ts : output
    models ||--o{ model_elements : "model elements"
    model_elements ||--o{ output_ts : "model element output"
    model_elements ||--o{ por_output_ts : "model element output"
    model_event_files }o--|| models : "model event file"
    model_event_files }o--|| events : "model event file"
    gages |o--o{ model_elements : "calibration"
    events ||--o{ output_ts : "event output"
    structures ||--o{ structure_response : "struct response"
    events ||--o{ structure_failure_elev : "failure elevs"
    structure_failure_elev ||--o{ structure_response : "failure elev"


    storms {
        storm_id int PK
        storm_rank int
        storm_type str
        datetime datetime
        duration_hrs int
        centroid geom
        mean_precip float
    }
    fishnet_points {
        fishnet_point_id int PK
        weight float
        geom geom
    }
    events {
        event_id int PK
        storm_id int FK
        fishnet_point_id int FK
        block_id int
        realization_id int
        centroid_trnsp geom
    }
    seeds {
        seed_id int PK
        event_id int FK
        process_id int
        realization_seed int
        block_seed int
        event_seed int
    }
    gages {
        gage_id int PK
        gage_name str
        gage_owner str
        ams array
        geom geom 
    }

    models {
        model_id int PK
        model_type str
        model_name str
        geom geom
    }
    model_elements {
        element_id int PK
        model_id int FK
        gage_id int FK
        element str
        geom geom
    }
    model_event_files {
        model_event_file_id int PK
        model_id int FK
        event_id int FK
        filename str
        data blob
        metadata blob
    }
    output_ts {
        event_id int FK
        element_id int FK
        timestamp datetime
        metric str
        value float
        units str
    }

    por_events {
        por_event_id int PK
    }
    por_output_ts {
        por_event_id int FK
        element_id int FK
        timestamp datetime
        metric str
        value float
        units str
    }

    structures {
        structure_id int PK
        hydro_model_id int FK
        hydra_model_id int FK
        system_type str
        name str
        nid_id str
        nld_id str
        nld_name str
        nld_segment_id str
        top_elev float
        toe_elev float
        source str
    }
    structure_response {
        structure_response_id int PK
        structure_id int FK
        failure_mode str
        source str
        prob_x float
        prob_y float
    }
    structure_failure_elev {
        structure_response_id int PK
        event_id int FK
        failure_elev float
    }

```

## ETL Needs:
* code to load `storms` table from StormHub STAC (already part of StormHub itself, just needs to be uncommented manually)

## Notes / Questions
* gages: ams == annual maxmium series? 
* fishnet: what is `weight`? importance sampling?
* reservoir, levee, and system response tables -- how is this supposed to work?

## Prior Art
![Iceberg Data Process](prior-art/iceberg-plugin-data-process.png)
![Iceberg Production Data](prior-art/iceberg-production-data.png)
