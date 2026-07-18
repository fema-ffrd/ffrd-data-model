# FFRD Data Dictionary

_Auto-generated from `data-dictionary.yaml`. Do not edit directly._

---

## Table of Contents

- **Events**
  - [fishnet_points](#fishnet-points)
  - [events](#events)
  - [seeds](#seeds)
- **Models**
  - [models](#models)
  - [model_elements](#model-elements)
  - [model_linkages](#model-linkages)
  - [hotfixes](#hotfixes)
- **Structures**
  - [levees](#levees)
  - [dams](#dams)
  - [structure_response](#structure-response)
  - [structure_failure_elev](#structure-failure-elev)
  - [buildings](#buildings)
  - [buildings_impacted](#buildings-impacted)
- **Management**
  - [run_catalog](#run-catalog)
  - [manifests](#manifests)
  - [run_logs](#run-logs)
  - [run_resources](#run-resources)
  - [run_files](#run-files)

---

## Events

### fishnet_points

Spatial sampling grid points used to place storms across the basin.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `fishnet_point_id` | `int` | 🔑 ✱ |  | Unique identifier for the fishnet sample point. |
| `weight` | `float` |  |  | Spatial weight assigned to this point for event frequency calculations. |
| `geom` | `geom` |  |  | Point geometry of the fishnet location. |

### events

Realized simulation events, each combining a storm with a spatial placement (fishnet point) within a stochastic block and realization.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `event_id` | `int` | 🔑 ✱ |  | Unique event identifier. |
| `storm_id` | `int` | 🔗 | storms.storm_id | Storm from the catalog used for this event. |
| `fishnet_point_id` | `int` | 🔗 | fishnet_points.fishnet_point_id | Spatial placement point for this event. |
| `event_type` | `enum` |  |  | Classification of the event (e.g. calibration, stochastic, historical). |
| `block_id` | `int` |  |  | Stochastic block identifier grouping events into frequency bands. |
| `realization_id` | `int` |  |  | Realization index within the stochastic ensemble, used for uncertainty quantification. |

### seeds

Random seeds used to reproduce each stochastic realization. One record per process per event.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `seed_id` | `int` | 🔑 ✱ |  | Unique seed record identifier. |
| `event_id` | `int` | 🔗 | events.event_id | Event this seed applies to. |
| `process_id` | `int` |  |  | Identifier for the stochastic process (e.g. precipitation, initial conditions). |
| `realization_seed` | `int` |  |  | Seed value for the realization-level random draw. |
| `block_seed` | `int` |  |  | Seed value for the block-level random draw. |
| `event_seed` | `int` |  |  | Seed value for the event-level random draw. |

## Models

### models

Hydrologic and hydraulic models (HEC-HMS, HEC-RAS, ResSim) organized by basin and version.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `model_id` | `int` | 🔑 ✱ |  | Unique model identifier. |
| `model_type` | `str` |  |  | Model software type (e.g. hec-hms, hec-ras, ressim). |
| `model_name` | `str` |  |  | Human-readable name identifying the model basin or domain. |
| `model_version` | `str` |  |  | Version string distinguishing calibration, conformance, and hotfix variants. |
| `geom` | `geom` |  |  | Polygon geometry representing the model domain or basin boundary. |
| `stac_metadata` | `uri` |  |  | URI to a STAC-formatted metadata document for this model. |

### model_elements

Individual features within a model — junctions, subbasins, 2D flow areas, boundary conditions, reaches, etc.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `element_id` | `int` | 🔑 ✱ |  | Unique element identifier. |
| `model_id` | `int` | 🔗 | models.model_id | Model this element belongs to. |
| `structure_id` | `int` |  |  | Optional reference to a dam, levee, or building if this element represents a structure. |
| `structure_type` | `str` |  |  | Type of structure represented (e.g. dam, levee, building). Null if not a structure element. |
| `gage_id` | `str` | 🔗 | gages.gage_id | Associated gage for observed vs. modeled comparison. Null if no gage co-location. |
| `element` | `str` |  |  | Feature name as used in the model input file. |
| `geom` | `geom` |  |  | Geometry of the element (point, line, or polygon depending on element type). |

### model_linkages

Inter-model connections defining how outputs from one model (donor) become inputs to another (receiver).

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `linkage_id` | `int` | 🔑 ✱ |  | Unique linkage identifier. |
| `donor_model_id` | `int` | 🔗 | models.model_id | Model providing the output at this linkage point. |
| `donor_model_type` | `str` |  |  | Software type of the donor model (e.g. hec-hms). |
| `donor_site_type` | `str` |  |  | Element type at the donor hand-off point (e.g. hms_junction, hms_subbasin). |
| `donor_site_id` | `str` | 🔗 | model_elements.element | Named element in the donor model that provides the output. |
| `receiver_model_id` | `int` | 🔗 | models.model_id | Model consuming the input at this linkage point. |
| `receiver_model_type` | `str` |  |  | Software type of the receiver model (e.g. hec-ras). |
| `receiver_site_type` | `str` |  |  | Element type at the receiver intake point (e.g. ras_bc, ras_2d_flow_area). |
| `receiver_site_id` | `str` | 🔗 | model_elements.element | Named element in the receiver model that accepts the input. |

### hotfixes

Tracks model versions that required remediation, recording the issue and resolution status.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `hotfix_id` | `int` | 🔑 ✱ |  | Unique hotfix record identifier. |
| `model_id` | `int` | 🔗 | models.model_id | Model this hotfix applies to. |
| `model_version` | `str` |  |  | Model version associated with this hotfix. |
| `issue_description` | `str` |  |  | Plain-language description of the issue that triggered the hotfix. |
| `status` | `enum` |  |  | Current state of the hotfix (e.g. open, in_progress, resolved, verified). |
| `resolved_at` | `datetime` |  |  | UTC timestamp when the hotfix was confirmed resolved. |

## Structures

### levees

Levee inventory. Each record represents one levee segment within a model domain.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `structure_id` | `int` | 🔑 ✱ |  | Unique structure identifier shared across dams, levees, and buildings. |
| `model_id` | `int` | 🔗 | models.model_id | Model domain this levee belongs to. |
| `system_type` | `str` |  |  | Levee system classification (e.g. earthen, floodwall, composite). |
| `nld_system_id` | `str` |  |  | Authoritative system identifier from the National Levee Database (NLD). |
| `nld_system_name` | `str` |  |  | Authoritative levee system name from the National Levee Database (NLD). |
| `nld_segment_id` | `str` |  |  | Authoritative segment identifier from the NLD. |
| `breach_fid` | `str` |  |  | Feature identifier of the associated breach location element within the model. |
| `top_elev` | `float` |  |  | Top-of-levee elevation in feet (NAVD88). |
| `toe_elev` | `float` |  |  | Toe-of-levee elevation in feet (NAVD88). |
| `source` | `str` |  |  | Data source for this levee record (e.g. NLD, USACE, LiDAR survey). |
| `geom` | `geom` |  |  | Geometry of the levee segment. |
| `stac_metadata` | `uri` |  |  | URI to a STAC-formatted metadata document for this levee. |

### dams

Dam inventory. Each record represents one dam structure within a model domain.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `structure_id` | `int` | 🔑 ✱ |  | Unique structure identifier shared across dams, levees, and buildings. |
| `model_id` | `int` | 🔗 | models.model_id | Model domain this dam belongs to. |
| `system_type` | `str` |  |  | Structural system classification (e.g. earthen, concrete, arch). |
| `nid_id` | `str` |  |  | Authoritative National Inventory of Dams (NID) identifier for this dam. |
| `nid_dam_name` | `str` |  |  | Authoritative dam name from the National Inventory of Dams (NID). |
| `top_elev` | `float` |  |  | Top-of-dam (crest) elevation in feet (NAVD88). |
| `toe_elev` | `float` |  |  | Toe-of-dam elevation in feet (NAVD88). |
| `source` | `str` |  |  | Data source for this dam record (e.g. NID, state agency, field survey). |
| `geom` | `geom` |  |  | Geometry of the dam. |
| `stac_metadata` | `uri` |  |  | URI to a STAC-formatted metadata document for this dam. |

### structure_response

Fragility or response functions defining the probability of a structure failing at a given hazard level.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `structure_response_id` | `int` | 🔑 ✱ |  | Unique response function identifier. |
| `structure_id` | `int` | 🔗 |  | Dam or levee this response function applies to. |
| `failure_mode` | `str` |  |  | Failure mechanism described by this function (e.g. overtopping, piping, seepage). |
| `source` | `str` |  |  | Source of the fragility function (e.g. USACE, peer-reviewed, project-specific). |
| `prob_x` | `float` |  |  | Hazard input value (e.g. water surface elevation or head differential) for this fragility point. |
| `prob_y` | `float` |  |  | Probability of failure corresponding to prob_x (0.0–1.0). |

### structure_failure_elev

Per-event failure water surface elevation for each structure, derived from simulation results and fragility functions.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `structure_response_id` | `int` | 🔑 🔗 | structure_response.structure_response_id | Response function instance associated with this failure record. |
| `event_id` | `int` | 🔗 | events.event_id | Event during which this failure elevation applies. |
| `failure_elev` | `float` |  |  | Water surface elevation (ft, NAVD88) at which the structure fails for this event. |

### buildings

Building inventory used for consequence analysis. Includes structural, financial, and occupancy attributes.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `structure_id` | `int` | 🔑 ✱ |  | Unique structure identifier shared across dams, levees, and buildings. |
| `source_building_id` | `str` |  |  | Identifier for this building in its source inventory dataset. |
| `inventory_source` | `str` |  |  | Name of the building inventory dataset (e.g. NSI, HAZUS). |
| `inventory_version` | `str` |  |  | Version or vintage of the inventory dataset. |
| `latitude` | `float` |  |  | Latitude of the building centroid in decimal degrees (WGS84). |
| `longitude` | `float` |  |  | Longitude of the building centroid in decimal degrees (WGS84). |
| `geom` | `geom` |  |  | Point geometry of the building location. |
| `occupancy_type` | `str` |  |  | HAZUS occupancy class code (e.g. RES1, COM1, IND2). |
| `general_building_type` | `str` |  |  | General structural type (e.g. wood frame, masonry, steel frame). |
| `number_stories` | `int` |  |  | Number of above-ground stories. |
| `area_sqft` | `float` |  |  | Total floor area in square feet. |
| `foundation_type` | `str` |  |  | Foundation classification (e.g. slab, crawlspace, basement, pier). |
| `first_floor_height_ft` | `float` |  |  | Height of the first finished floor above grade in feet. |
| `basement_type` | `int` |  |  | Basement classification code (0 = none, 1 = unfinished, 2 = finished). |
| `building_cost` | `float` |  |  | Replacement cost of the building structure in USD. |
| `content_cost` | `float` |  |  | Replacement cost of building contents in USD. |
| `inventory_cost` | `float` |  |  | Replacement cost of business inventory in USD (commercial/industrial only). |
| `bldg_insurance_deductible` | `float` |  |  | Building insurance deductible amount in USD. |
| `bldg_insurance_limit` | `float` |  |  | Building insurance coverage limit in USD. |
| `content_insurance_deductible` | `float` |  |  | Contents insurance deductible amount in USD. |
| `content_insurance_limit` | `float` |  |  | Contents insurance coverage limit in USD. |
| `ground_elevation_ft` | `float` |  |  | Ground surface elevation at the building location in feet (NAVD88). |
| `source` | `str` |  |  | Primary data source for this building record. |

### buildings_impacted

Per-event building inundation results linking buildings to events with modeled inundation depth.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `structure_id` | `int` | 🔑 | buildings.structure_id | Building impacted. |
| `event_id` | `int` | 🔑 🔗 | events.event_id | Event causing the impact. |
| `inundation_depth` | `float` |  |  | Modeled inundation depth at the building location in feet. |

## Management

### run_catalog

Individual simulation executions, each pairing one event with one model version.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `run_id` | `int` | 🔑 ✱ |  | Unique run identifier. |
| `event_id` | `int` | 🔗 | events.event_id | Stochastic or calibration event simulated in this run. |
| `model_id` | `int` | 🔗 | models.model_id | Model version used for this run. |
| `run_type` | `enum` |  |  | Classification of the run (e.g. calibration, conformance, hotfix, rerun). |
| `timestamp` | `datetime` |  |  | UTC timestamp when the run was initiated. |
| `success` | `bool` |  |  | Whether the run completed successfully without fatal errors. |
| `metadata` | `uri` |  |  | URI to run-level metadata document. |

### manifests

Execution manifests capturing the software configuration active for a set of runs, including plugin and linkage versions.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `manifest_id` | `int` | 🔑 ✱ |  | Unique manifest identifier. |
| `run_id` | `int` | 🔗 | run_catalog.run_id | Run associated with this manifest. |
| `model_id` | `int` | 🔗 | models.model_id | Model associated with this manifest. |
| `manifest_version` | `str` |  |  | Version string of the manifest document itself. |
| `plugin_id` | `int` | 🔑 |  | Identifier for the plugin active under this manifest. |
| `plugin_name` | `str` |  |  | Name of the plugin or software component. |
| `plugin_version` | `str` |  |  | Semantic version string of the plugin. |
| `linkage_version` | `str` |  |  | Version of the inter-model linkage configuration active for this manifest. |
| `uri` | `str` |  |  | Cloud storage URI pointing to the full manifest document. |
| `created_at` | `datetime` |  |  | UTC timestamp when this manifest was created or published. |

### run_logs

Links each run to its cloud container execution log.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `log_id` | `int` | 🔑 ✱ |  | Unique log record identifier. |
| `run_id` | `int` | 🔗 | run_catalog.run_id | Run this log belongs to. |
| `uri` | `str` |  |  | Cloud storage or logging service URI for the run's full execution log. |

### run_resources

Compute resource consumption per run, used for budget tracking and forecasting.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `run_id` | `int` | 🔗 | run_catalog.run_id | Run this resource record applies to. |
| `cpu_hours` | `float` |  |  | Total CPU core-hours consumed by the run. |
| `memory_gb` | `float` |  |  | Peak memory usage in gigabytes during the run. |
| `storage_gb` | `float` |  |  | Total cloud storage consumed by run outputs in gigabytes. |

### run_files

Raw model file artifacts (CC raw output) associated with a run, referenced by URI.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `run_file_id` | `int` | 🔑 ✱ |  | Unique file record identifier. |
| `run_id` | `int` | 🔗 | run_catalog.run_id | Run this file belongs to. |
| `uri` | `str` |  |  | Cloud storage URI pointing to the file artifact. |
