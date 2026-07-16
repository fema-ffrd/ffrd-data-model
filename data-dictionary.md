# FFRD Data Dictionary

_Auto-generated from `data-dictionary.yaml`. Do not edit directly._

---

## Table of Contents

- **Events**
  - [storms](#storms)
  - [fishnet_points](#fishnet-points)
  - [events](#events)
  - [seeds](#seeds)
- **Models**
  - [gages](#gages)
  - [models](#models)
  - [model_elements](#model-elements)
  - [model_linkages](#model-linkages)
  - [runs](#runs)
  - [output_ts](#output-ts)
  - [output_grids](#output-grids)
  - [obs_ts](#obs-ts)
- **Structures**
  - [dams](#dams)
  - [levees](#levees)
  - [structure_response](#structure-response)
  - [structure_failure_elev](#structure-failure-elev)
  - [buildings](#buildings)
- **Management**
  - [manifests](#manifests)
  - [plugins](#plugins)
  - [manifest_plugins](#manifest-plugins)
  - [run_manifest](#run-manifest)
  - [run_logs](#run-logs)
  - [hotfixes](#hotfixes)
  - [run_resources](#run-resources)
  - [run_files](#run-files)

---

## Events

### storms

Stochastic storm catalog. Each record represents one synthetic or historical storm event.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `storm_id` | `int` | 🔑 ✱ |  | Unique storm identifier. |
| `storm_rank` | `int` |  |  | Rank of the storm within its catalog by severity or selection order. |
| `storm_type` | `str` |  |  | Classification of the storm (e.g. synoptic, convective, snowmelt). |
| `datetime` | `datetime` |  |  | Reference timestamp for the storm (typically centroid or start time). |
| `duration_hrs` | `int` |  |  | Storm duration in hours. |
| `centroid` | `geom` |  |  | Geographic centroid of the storm as a point geometry. |
| `mean_precip` | `float` |  |  | Mean precipitation depth over the storm domain in inches. |

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

### gages

Stream and reservoir gages used for calibration and observed data comparison.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `gage_id` | `str` | 🔑 ✱ |  | Authoritative gage identifier (e.g. USGS site number). |
| `gage_name` | `str` |  |  | Human-readable name of the gage station. |
| `gage_owner` | `str` |  |  | Agency or organization responsible for operating the gage (e.g. USGS, USACE). |
| `ams` | `array` |  |  | Annual maximum series — array of peak flow or stage values used for frequency analysis. |
| `geom` | `geom` |  |  | Point geometry of the gage location. |

### models

Hydrologic and hydraulic models (HEC-HMS, HEC-RAS, ResSim) organized by basin and version.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `model_id` | `int` | 🔑 ✱ |  | Unique model identifier. |
| `model_type` | `str` |  |  | Model software type (e.g. hec-hms, hec-ras, ressim). |
| `model_name` | `str` |  |  | Human-readable name identifying the model basin or domain. |
| `model_version` | `str` |  |  | Version string distinguishing calibration, conformance, and hotfix variants. |
| `geom` | `geom` |  |  | Polygon geometry representing the model domain or basin boundary. |
| `metadata` | `uri` |  |  | URI to a structured JSON/YAML document containing model-level metadata. Required keys: conformance_checks (array of {... |

### model_elements

Individual features within a model — junctions, subbasins, 2D flow areas, boundary conditions, reaches, etc.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `element_id` | `int` | 🔑 ✱ |  | Unique element identifier. |
| `model_id` | `int` | 🔗 | models.model_id | Model this element belongs to. |
| `structure_id` | `int` |  |  | Optional reference to a dam, levee, or building if this element represents a structure. |
| `structure_type` | `str` |  |  | Type of structure represented (e.g. dam, levee, building). Null if not a structure element. |
| `gage_id` | `str` | 🔗 | gages.gage_id | Associated gage for observed vs. modeled comparison. Null if no gage co-location. |
| `element` | `str` |  |  | Feature name as used in the model input file. Should match authoritative naming standards (NLD, NID, USGS). |
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

### runs

Individual simulation executions, each pairing one event with one model version.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `run_id` | `int` | 🔑 ✱ |  | Unique run identifier. |
| `event_id` | `int` | 🔗 | events.event_id | Stochastic or calibration event simulated in this run. |
| `model_id` | `int` | 🔗 | models.model_id | Model version used for this run. |
| `run_type` | `enum` |  |  | Classification of the run (e.g. calibration, conformance, hotfix, rerun). |
| `timestamp` | `datetime` |  |  | UTC timestamp when the run was initiated. |
| `success` | `bool` |  |  | Whether the run completed successfully without fatal errors. |
| `metadata` | `uri` |  |  | URI to a structured JSON/YAML document containing run-level metadata. Required keys: start_time (ISO 8601), end_time ... |

### output_ts

Modeled time series output values per element per run. Stores flows, stages, volumes, and other scalar time-varying outputs.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `run_id` | `int` | 🔗 | runs.run_id | Run that produced this output. |
| `element_id` | `int` | 🔗 | model_elements.element_id | Model element at which the output was recorded. |
| `timestamp` | `datetime` |  |  | UTC timestamp of the output value. |
| `variable` | `str` |  |  | Output variable name (e.g. flow, stage, storage, velocity). |
| `value` | `float` |  |  | Numeric value of the output variable at this timestep. |
| `units` | `str` |  |  | Units of the output value (e.g. cfs, ft, acre-ft). |

### output_grids

Gridded output files (depth, velocity, WSE) produced by a run. Stored externally and referenced by URI.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `output_grid_id` | `int` | 🔑 ✱ |  | Unique grid output identifier. |
| `run_id` | `int` | 🔗 | runs.run_id | Run that produced this grid. |
| `variable` | `str` |  |  | Gridded variable name (e.g. depth, velocity, wse, extent). |
| `uri` | `str` |  |  | Cloud storage URI pointing to the gridded output file (e.g. GeoTIFF, HDF5). |

### obs_ts

Observed time series from gages used for model calibration and validation.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `gage_id` | `str` | 🔗 | gages.gage_id | Gage that recorded this observation. |
| `timestamp` | `datetime` |  |  | UTC timestamp of the observation. |
| `variable` | `str` |  |  | Observed variable (e.g. flow, stage). |
| `value` | `float` |  |  | Numeric observed value. |
| `units` | `str` |  |  | Units of the observed value (e.g. cfs, ft). |

## Structures

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
| `breach_fid` | `str` |  |  | Feature identifier of the associated breach location element within the model (references model_elements.element). |
| `top_elev` | `float` |  |  | Top-of-levee elevation in feet (NAVD88). |
| `toe_elev` | `float` |  |  | Toe-of-levee elevation in feet (NAVD88). |
| `source` | `str` |  |  | Data source for this levee record (e.g. NLD, USACE, LiDAR survey). |

### structure_response

Fragility or response functions defining the probability of a structure failing at a given hazard level.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `structure_response_id` | `int` | 🔑 ✱ |  | Unique response function identifier. |
| `structure_id` | `int` | 🔗 |  | Dam or levee this response function applies to. References dams.structure_id or levees.structure_id. |
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

Building inventory used for consequence analysis. Includes structural, financial, occupancy, and demographic attributes.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `structure_id` | `int` | 🔑 ✱ |  | Unique structure identifier shared across dams, levees, and buildings. |
| `source_building_id` | `str` |  |  | Identifier for this building in its source inventory dataset. |
| `inventory_source` | `str` |  |  | Name of the building inventory dataset (e.g. NSI, HAZUS). |
| `inventory_version` | `str` |  |  | Version or vintage of the inventory dataset. |
| `latitude` | `float` |  |  | Latitude of the building centroid in decimal degrees (WGS84). |
| `longitude` | `float` |  |  | Longitude of the building centroid in decimal degrees (WGS84). |
| `geom` | `geom` |  |  | Point geometry of the building location. |
| `state_fips` | `str` |  |  | Two-digit FIPS code for the state. |
| `county_fips` | `str` |  |  | Five-digit FIPS code for the county. |
| `census_block_fips` | `str` |  |  | Full FIPS code for the census block. |
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
| `pop_2am` | `int` |  |  | Estimated occupant population at 2 AM (nighttime occupancy). |
| `pop_2pm` | `int` |  |  | Estimated occupant population at 2 PM (daytime occupancy). |
| `pop_2am_under65` | `int` |  |  | Estimated population under age 65 at 2 AM. |
| `pop_2am_over65` | `int` |  |  | Estimated population age 65 and over at 2 AM. |
| `pop_2pm_under65` | `int` |  |  | Estimated population under age 65 at 2 PM. |
| `pop_2pm_over65` | `int` |  |  | Estimated population age 65 and over at 2 PM. |
| `source` | `str` |  |  | Primary data source for this building record. |

## Management

### manifests

Execution manifests capturing the software configuration active for a set of runs, including linkage and plugin versions.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `manifest_id` | `int` | 🔑 ✱ |  | Unique manifest identifier. |
| `manifest_version` | `str` |  |  | Version string of the manifest document itself. |
| `linkage_version` | `str` |  |  | Version of the inter-model linkage configuration active for this manifest. |
| `uri` | `str` |  |  | Cloud storage URI pointing to the full manifest document. |
| `created_at` | `datetime` |  |  | UTC timestamp when this manifest was created or published. |

### plugins

Registry of software plugins and their versions used during cloud compute runs.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `plugin_id` | `int` | 🔑 ✱ |  | Unique plugin identifier. |
| `plugin_name` | `str` |  |  | Name of the plugin or software component. |
| `plugin_version` | `str` |  |  | Semantic version string of the plugin. |

### manifest_plugins

Join table recording which plugins were active under a given manifest.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `manifest_id` | `int` | 🔗 | manifests.manifest_id | Manifest this plugin association belongs to. |
| `plugin_id` | `int` | 🔗 | plugins.plugin_id | Plugin active under this manifest. |

### run_manifest

Join table linking each run to the manifest that governed its execution.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `run_id` | `int` | 🔗 | runs.run_id | Run associated with this manifest. |
| `manifest_id` | `int` | 🔗 | manifests.manifest_id | Manifest active when this run executed. |

### run_logs

Links each run to its cloud execution log for error review and performance diagnostics.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `log_id` | `int` | 🔑 ✱ |  | Unique log record identifier. |
| `run_id` | `int` | 🔗 | runs.run_id | Run this log belongs to. |
| `uri` | `str` |  |  | Cloud storage or logging service URI for the run's full execution log. |

### hotfixes

Tracks runs that required remediation, linking the original failing run to its rerun and recording the issue and resolution.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `hotfix_id` | `int` | 🔑 ✱ |  | Unique hotfix record identifier. |
| `original_run_id` | `int` | 🔗 | runs.run_id | The original run that failed or produced erroneous results. |
| `rerun_id` | `int` | 🔗 | runs.run_id | The corrective rerun that replaced the original. |
| `issue_description` | `str` |  |  | Plain-language description of the issue that triggered the hotfix. |
| `resolution_model_id` | `int` | 🔗 | models.model_id | Model version that resolved the issue and was used in the rerun. |
| `status` | `enum` |  |  | Current state of the hotfix (e.g. open, in_progress, resolved, verified). |
| `resolved_at` | `datetime` |  |  | UTC timestamp when the hotfix was confirmed resolved. |

### run_resources

Compute resource consumption and cost per run, used for budget tracking and forecasting.

| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `run_id` | `int` | 🔗 | runs.run_id | Run this resource record applies to. |
| `cpu_hours` | `float` |  |  | Total CPU core-hours consumed by the run. |
| `memory_gb` | `float` |  |  | Peak memory usage in gigabytes during the run. |
| `storage_gb` | `float` |  |  | Total cloud storage consumed by run outputs in gigabytes. |
| `compute_cost` | `float` |  |  | Estimated compute cost in USD for this run. |

### run_files

Raw model file artifacts associated with a run, stored as blobs with structured metadata. RDB implementation: data stored as blob with metadata blob. Lakehouse implementation: data stored externally; object_uri + file_format + metadata_json replace data/metadata blob.


| Column | Type | Constraints | References | Description |
|--------|------|-------------|------------|-------------|
| `run_file_id` | `int` | 🔑 ✱ |  | Unique file record identifier. |
| `run_id` | `int` | 🔗 | runs.run_id | Run (rdb) or run_catalog (lakehouse) this file belongs to. |
| `filename` | `str` |  |  | Original filename of the artifact. |
| `data` | `blob` |  |  | [rdb only] Raw binary content of the file. |
| `object_uri` | `str` |  |  | [lakehouse only] Cloud storage URI to the file object (replaces data blob). |
| `file_format` | `str` |  |  | [lakehouse only] File format classification (e.g. hms_project, ras_project, ressim_project, geotiff). |
| `metadata` | `blob` |  |  | [rdb only] Structured metadata blob for this file. Required keys: file_type (e.g. hms_project, ras_project, ressim_pr... |
| `metadata_json` | `str` |  |  | [lakehouse only] JSON string equivalent of metadata blob. Required keys: file_type, model_version, export_uri, expect... |
