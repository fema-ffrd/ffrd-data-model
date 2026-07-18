# User Stories — Data Model Validation

This document maps each of the 33 user stories to the tables, columns, and relationships in the FFRD data model that support them. Every story is assessed for coverage level:

| Coverage | Meaning |
|----------|---------|
| **Direct** | Fully queryable from relational (PG) or Iceberg tables and materialized views |
| **Via STAC** | Supported by following a `stac_metadata` URI to an external STAC document |
| **Computable** | Raw data is present; requires application-layer joins or aggregation |

---

## Summary

| # | Story | Persona | Coverage |
|---|-------|---------|----------|
| 1 | All Versions | CC Admin | Direct |
| 2 | Reliability and Performance | CC Admin | Direct |
| 3 | Re-runs and Hotfixes | CC Admin | Direct |
| 4 | Resources and Cost Estimates | CC Admin | Direct |
| 5 | Conformance Metrics | Conformance Lead | Direct |
| 6 | Event Filtering | Conformance Lead | Direct |
| 7 | Result Provenance | Conformance Lead / Leadership / FEMA | Direct |
| 8 | At-Risk Structures | Consequences Analyst | Direct |
| 9 | Damage and Risk Reporting | Consequences Analyst | Computable |
| 10 | Hazard Grids and Frequencies | Consequences Analyst | Direct |
| 11 | Uncertainty (Damages) | Consequences Analyst | Computable |
| 12 | Authoritative Dataset Completion | Data Prep Lead | Via STAC |
| 13 | Dam Scoping Table | Data Prep Lead | Direct + Via STAC |
| 14 | Data Source Traceability | Data Prep Lead | Via STAC |
| 15 | Comparison of Observed vs Computed Data | H&H Engineer | Direct |
| 16 | Export Models | H&H Engineer | Via STAC |
| 17 | Flood Validation | H&H Engineer | Direct |
| 18 | Dam and Levee Breach Locations | H&H Engineer | Direct |
| 19 | Input Datasets | H&H Engineer | Via STAC |
| 20 | Model Features | H&H Engineer | Direct |
| 21 | Model Versions | H&H Engineer | Direct |
| 22 | RAS Parameters Outside RAS | H&H Engineer | Via STAC |
| 23 | Starting Conditions | H&H Engineer | Via STAC |
| 24 | Validate HMS and RAS Flows | H&H Engineer | Direct |
| 25 | Verify Naming Conventions | H&H Engineer | Direct |
| 26 | Errors and Events | H&H Engineer / Conformance Lead | Direct |
| 27 | Model Connections | H&H Engineer / Integration Lead | Direct |
| 28 | Trace Results | Hazard Analyst | Direct |
| 29 | Diffs Between Model Versions | Integration Lead | Direct |
| 30 | Linkage Diffs | Integration Lead | Direct |
| 31 | Uncertainty (Frequency) | Leadership / FEMA | Direct |
| 32 | Understand Risk | Leadership / FEMA | Direct |
| 33 | Export Results | Non-PTS Data Scientist | Direct |

**Totals:** 25 Direct, 6 Via STAC, 2 Computable

---

## Detailed Validation

### CC Admin

#### 1 — All Versions

> *Determine which manifest, linkage version, and plugin versions were used for an event.*

| Table | Columns Used |
|-------|-------------|
| `run_catalog` | `run_id`, `event_id`, `model_id` |
| `manifests` | `manifest_version`, `plugin_name`, `plugin_version`, `linkage_version` |

**Path:** `events` → `run_catalog.event_id` → `manifests.run_id`

---

#### 2 — Reliability and Performance

> *Understand how long a model or event took to run, identify failed events, and review error messages.*

| Table | Columns Used |
|-------|-------------|
| `run_catalog` | `success`, `timestamp` |
| `run_logs` | `uri` (link to full execution log) |
| `mv_run_performance` | `duration_sec`, `status`, `cpu_hours` |

**Path:** `run_catalog.success = false` → `run_logs.uri` for error details; `mv_run_performance` for aggregate timing.

---

#### 3 — Re-runs and Hotfixes

> *Identify which events required hot-fix reruns, understand the underlying issue, and determine which model version resolves it.*

| Table | Columns Used |
|-------|-------------|
| `hotfixes` | `model_id`, `model_version`, `issue_description`, `status`, `resolved_at` |
| `run_catalog` | `run_type` (filter `= 'hotfix'`), `model_id` |

**Path:** `hotfixes.model_id` → `models` → `run_catalog` (run_type = hotfix) → `events`

---

#### 4 — Resources and Cost Estimates

> *Evaluate run costs, basin costs, month-to-date spending, projected completion costs, and resource utilization.*

| Table | Columns Used |
|-------|-------------|
| `run_resources` | `cpu_hours`, `memory_gb`, `storage_gb` |
| `mv_run_performance` | `compute_cost`, `cpu_hours`, `duration_sec` |
| `mv_basin_cost_rollup` | `total_compute_cost`, `total_cpu_hours`, `total_storage_gb`, `run_count`, `failed_run_count`, `billing_month` |

**Path:** Per-run costs via `run_resources`; basin-month rollups via `mv_basin_cost_rollup`.

---

### Conformance Lead

#### 5 — Conformance Metrics

> *Determine whether a basin meets conformance metrics and identify failing checks.*

| Table | Columns Used |
|-------|-------------|
| `mv_conformance_summary` | `model_id`, `model_version`, `check_name`, `threshold`, `result_value`, `pass` |
| `models` | `stac_metadata` (detailed conformance context) |

**Path:** `mv_conformance_summary` filtered by `model_id`; drill into `models.stac_metadata` for full conformance documentation.

---

#### 6 — Event Filtering

> *Perform statistical analysis on model outputs and workflow stages to support event filtering.*

| Table | Columns Used |
|-------|-------------|
| `mv_event_variable_stats` | `event_id`, `variable`, `mean_value`, `max_value`, `min_value`, `std_value`, `element_count` |
| `output_ts` | Raw time series for custom filtering logic |

**Path:** `mv_event_variable_stats` provides pre-aggregated stats per event; `output_ts` for ad-hoc analysis.

---

### Conformance Lead / Leadership / FEMA

#### 7 — Result Provenance

> *Trace a hazard, flow, precipitation, or depth result back to the event that produced it.*

| Table | Columns Used |
|-------|-------------|
| `output_ts` | `run_id`, `event_id`, `model_id`, `element_id` |
| `output_grids` | `repo_uri`, `index_key` (event_id) |
| `run_catalog` | `run_id` → `event_id` → `model_id` |
| `events` | `storm_id`, `fishnet_point_id` |
| `storms` | `stac_metadata`, `netcdf`, `icechunk_repo` |

**Path:** result value → `output_ts.run_id` → `run_catalog` → `events.storm_id` → `storms` (full precipitation provenance via `netcdf` and `icechunk_repo` URIs). For grids: `output_grids.index_key = event_id`.

---

### Consequences Analyst

#### 8 — At-Risk Structures

> *Evaluate losses at selected AEP frequencies for individual structures and entire basins.*

| Table | Columns Used |
|-------|-------------|
| `buildings_impacted` | `structure_id`, `event_id`, `inundation_depth` |
| `buildings` | All cost/attribute columns (`building_cost`, `content_cost`, `occupancy_type`, etc.) |
| `structure_failure_elev` | `structure_response_id`, `event_id`, `failure_elev` |
| `events` | `block_id`, `realization_id` (frequency weighting) |
| `fishnet_points` | `weight` |
| `mv_aep_frequency_stats` | `aep_label`, `aep_value` (frequency context) |

**Path:** `buildings_impacted` joined to `buildings` for per-structure damages; `events.block_id` + `fishnet_points.weight` provide frequency weighting for AEP binning.

---

#### 9 — Damage and Risk Reporting (AAL)

> *Calculate Average Annualized Loss (AAL) for structures and basins.*

| Table | Columns Used |
|-------|-------------|
| `buildings_impacted` | `structure_id`, `event_id`, `inundation_depth` |
| `buildings` | Cost columns, `occupancy_type`, `first_floor_height_ft` |
| `events` | `block_id`, `realization_id` |
| `fishnet_points` | `weight` |

**Coverage: Computable.** The data model stores all inputs needed for AAL: inundation depths per building per event, building attributes for depth-damage function application, and stochastic frequency weights. Depth-damage functions themselves are external to this data model (applied by HEC-FIA or equivalent consequence tools). Dollar damages and AAL are computed at the application layer.

---

#### 10 — Hazard Grids and Frequencies

> *Identify which hazard grid versions were used in consequence analyses.*

| Table | Columns Used |
|-------|-------------|
| `output_grids` | `repo_name`, `repo_uri`, `variables`, `index_key` |
| `run_catalog` | `run_id`, `event_id`, `model_id` |

**Path:** `output_grids` → `run_catalog` provides full provenance of which grid repo, indexed by event_id, was generated by which run and model version.

---

#### 11 — Uncertainty (Damages)

> *Calculate mean damages and standard deviations across realizations for each AEP.*

| Table | Columns Used |
|-------|-------------|
| `buildings_impacted` | `structure_id`, `event_id`, `inundation_depth` |
| `events` | `realization_id`, `block_id` |
| `mv_aep_frequency_stats` | `mean_peak`, `std_peak`, `pct_10_peak`, `pct_50_peak`, `pct_90_peak`, `realization_count` |

**Coverage: Computable.** Flow/stage uncertainty is directly available via `mv_aep_frequency_stats`. Damage uncertainty requires grouping `buildings_impacted.inundation_depth` by `events.realization_id` and `events.block_id`, applying depth-damage functions, then computing cross-realization statistics. Raw data is fully present.

---

### Data Prep Lead

#### 12 — Authoritative Dataset Completion

> *Determine whether all required preparation and scoping datasets are complete and correctly named.*

| Table | Columns Used |
|-------|-------------|
| `models` | `stac_metadata` |

**Coverage: Via STAC.** The `stac_metadata` URI points to a STAC document that includes input dataset inventories, naming conventions, and completion status. The data model does not store a per-dataset checklist as relational rows — dataset tracking lives in the STAC metadata layer.

---

#### 13 — Dam Scoping Table

> *Visualize the Dam Scoping Table spatially.*

| Table | Columns Used |
|-------|-------------|
| `dams` | `structure_id`, `nid_id`, `nid_dam_name`, `geom` |
| `model_elements` | `structure_id`, `structure_type`, `geom` |
| `models` | `stac_metadata` (scoping decisions: include/exclude, rationale, analyst) |

**Coverage: Direct + Via STAC.** Dam locations and geometry are directly queryable for spatial visualization. Scoping decisions (include/exclude rationale) are stored in the STAC metadata document.

---

#### 14 — Data Source Traceability

> *Identify the source, version, and acquisition date of datasets such as terrain and NLCD.*

| Table | Columns Used |
|-------|-------------|
| `models` | `stac_metadata` |

**Coverage: Via STAC.** Input dataset provenance (source, version, acquisition_date, URI) is stored in the STAC metadata document referenced by `models.stac_metadata`.

---

### H&H Engineer

#### 15 — Comparison of Observed vs Computed Data

> *Compare modeled frequency results against observed gage data.*

| Table | Columns Used |
|-------|-------------|
| `mv_gage_model_comparison` | `gage_id`, `event_id`, `observed_peak`, `modeled_peak`, `bias`, `percent_error`, `variable`, `units` |
| `gages` | `gage_name`, `geom` (for spatial context) |

**Path:** `mv_gage_model_comparison` provides pre-computed observed vs. modeled peak comparison at co-located gages. Join to `gages` for gage metadata and spatial display.

---

#### 16 — Export Models

> *Export or download models for additional analysis within HEC-HMS and HEC-RAS.*

| Table | Columns Used |
|-------|-------------|
| `models` | `stac_metadata` (URI to model artifacts) |
| `run_files` | `uri` (raw model output files) |

**Coverage: Via STAC.** Model input files are referenced through `models.stac_metadata`; raw output files via `run_files.uri`.

---

#### 17 — Flood Validation

> *View modeled flood extents for events of interest.*

| Table | Columns Used |
|-------|-------------|
| `output_grids` | `repo_uri`, `variables` (e.g. max_depth, max_velocity), `index_key` (event_id) |
| `events` | `event_id` (filter by event of interest) |
| `run_catalog` | `run_id`, `event_id` |

**Path:** `output_grids` Icechunk repos store gridded flood depth/velocity results indexed by `event_id`. Query the repo for a specific event to retrieve spatial flood extents.

---

#### 18 — Dam and Levee Breach Locations

> *Identify where dams and levees fail during events.*

| Table | Columns Used |
|-------|-------------|
| `structure_failure_elev` | `structure_response_id`, `event_id`, `failure_elev` |
| `structure_response` | `structure_id`, `failure_mode` |
| `dams` | `geom`, `nid_dam_name` |
| `levees` | `geom`, `breach_fid`, `nld_system_name` |

**Path:** `structure_failure_elev` → `structure_response.structure_id` → `dams`/`levees` (with geom for spatial display). The `failure_elev` + `failure_mode` identify which structures failed and by what mechanism.

---

#### 19 — Input Datasets

> *Identify supporting datasets and versions used by a model.*

| Table | Columns Used |
|-------|-------------|
| `models` | `stac_metadata` |
| `manifests` | `plugin_name`, `plugin_version`, `linkage_version` |

**Coverage: Via STAC.** Input dataset provenance is in the STAC metadata document. Software configuration is in `manifests`.

---

#### 20 — Model Features

> *Verify feature connectivity and linkages across RAS, HMS, and ResSim models.*

| Table | Columns Used |
|-------|-------------|
| `model_linkages` | `donor_model_id`, `donor_site_type`, `donor_site_id`, `receiver_model_id`, `receiver_site_type`, `receiver_site_id` |
| `model_elements` | `element_id`, `model_id`, `element`, `geom` |

**Path:** `model_linkages` defines every donor→receiver connection. Join to `model_elements` on `donor_site_id`/`receiver_site_id` for element geometry and names.

---

#### 21 — Model Versions

> *Identify which model version produced a result.*

| Table | Columns Used |
|-------|-------------|
| `output_ts` | `run_id`, `model_id` |
| `run_catalog` | `run_id`, `model_id` |
| `models` | `model_version`, `model_name`, `model_type` |

**Path:** `output_ts.run_id` → `run_catalog.model_id` → `models.model_version`.

---

#### 22 — RAS Parameters Outside RAS

> *View key model parameters (Manning's n, timestep, simulation window) outside of RAS.*

| Table | Columns Used |
|-------|-------------|
| `models` | `stac_metadata` |
| `run_files` | `uri` |

**Coverage: Via STAC.** Model parameters are stored in model input files referenced by `stac_metadata` and/or available in `run_files`. These are not extracted into queryable columns — retrieval requires parsing model files or the STAC document.

---

#### 23 — Starting Conditions

> *Review initial conditions such as reservoir elevations for a run.*

| Table | Columns Used |
|-------|-------------|
| `models` | `stac_metadata` |
| `run_files` | `uri` |

**Coverage: Via STAC.** Initial conditions (reservoir elevations, antecedent moisture, etc.) are part of model input files accessible via `stac_metadata` or `run_files.uri`.

---

#### 24 — Validate HMS and RAS Flows

> *Compare peak flows between HMS and RAS at the same location.*

| Table | Columns Used |
|-------|-------------|
| `model_linkages` | `donor_model_id`, `donor_site_id`, `receiver_model_id`, `receiver_site_id` |
| `mv_peak_output_by_element` | `element_id`, `model_id`, `variable`, `peak_value` |
| `model_elements` | `element_id`, `model_id` |

**Path:** `model_linkages` identifies co-located HMS→RAS handoff points. Join `mv_peak_output_by_element` on both the donor and receiver `element_id` + `model_id` to compare peak flows at the same physical location across the two models.

---

#### 25 — Verify Naming Conventions

> *Verify feature names against authoritative naming standards.*

| Table | Columns Used |
|-------|-------------|
| `model_elements` | `element` |
| `dams` | `nid_dam_name` |
| `levees` | `nld_system_name`, `nld_segment_id` |
| `gages` | `gage_id`, `gage_name` |

**Path:** Compare `model_elements.element` names against authoritative identifiers in `dams`, `levees`, and `gages`. Naming validation is application logic using these stored values.

---

### H&H Engineer / Conformance Lead

#### 26 — Errors and Events

> *Review volume errors, failed events, and failure causes.*

| Table | Columns Used |
|-------|-------------|
| `run_catalog` | `success`, `event_id`, `run_type` |
| `run_logs` | `uri` (full execution log with error messages) |
| `mv_run_performance` | `status` |

**Path:** `run_catalog.success = false` identifies failures; `run_logs.uri` provides detailed error messages and volume error diagnostics.

---

### H&H Engineer / Integration Lead

#### 27 — Model Connections

> *Identify upstream and downstream model relationships.*

| Table | Columns Used |
|-------|-------------|
| `model_linkages` | `donor_model_id`, `donor_model_type`, `receiver_model_id`, `receiver_model_type` |
| `models` | `model_name`, `model_type` |

**Path:** `model_linkages` directly encodes the directed graph of model-to-model connections. Query all linkages for a model to see its upstream donors and downstream receivers.

---

### Hazard Analyst

#### 28 — Trace Results

> *Determine which events contributed to a 100-year or 2,000-year hazard result.*

| Table | Columns Used |
|-------|-------------|
| `mv_aep_frequency_stats` | `element_id`, `aep_label`, `aep_value`, `mean_peak` |
| `output_ts` | `event_id`, `element_id`, `variable`, `value` |
| `events` | `block_id`, `realization_id`, `storm_id` |
| `storms` | `storm_type`, `mean_precip`, `centroid` |

**Path:** `mv_aep_frequency_stats` identifies the AEP band; join back to `output_ts` to find which `event_id` values produced peaks near the AEP threshold; trace through `events` to the originating `storms`.

---

### Integration Lead

#### 29 — Diffs Between Model Versions

> *Identify differences between calibration and conformance model variants.*

| Table | Columns Used |
|-------|-------------|
| `models` | `model_id`, `model_version` |
| `model_elements` | All columns (compare element sets between versions) |
| `model_linkages` | All columns (compare linkage configurations) |

**Path:** Query `model_elements` and `model_linkages` for two `model_version` values of the same `model_name` and diff the result sets.

---

#### 30 — Linkage Diffs

> *Review changes between linkage versions.*

| Table | Columns Used |
|-------|-------------|
| `manifests` | `linkage_version` |
| `model_linkages` | All columns |

**Path:** Compare `model_linkages` rows across two model versions identified via `manifests.linkage_version`.

---

### Leadership / FEMA

#### 31 — Uncertainty (Frequency)

> *Understand uncertainty ranges associated with estimates.*

| Table | Columns Used |
|-------|-------------|
| `mv_aep_frequency_stats` | `mean_peak`, `std_peak`, `pct_10_peak`, `pct_50_peak`, `pct_90_peak`, `realization_count` |

**Path:** `mv_aep_frequency_stats` directly provides uncertainty bounds (mean, std, 10th/50th/90th percentiles) per element, variable, and AEP band.

---

#### 32 — Understand Risk

> *Understand flood hazard at standard frequencies for a basin.*

| Table | Columns Used |
|-------|-------------|
| `mv_aep_frequency_stats` | `aep_label`, `aep_value`, `mean_peak`, `element_id`, `variable` |
| `mv_event_variable_stats` | `event_id`, `variable`, `mean_value`, `max_value` |
| `models` | `model_name`, `geom` (basin boundary) |

**Path:** `mv_aep_frequency_stats` provides standard-frequency hazard values (100-yr, 500-yr, etc.) per element. Aggregate across elements within a `model_id` for basin-level risk summaries.

---

### Non-PTS Data Scientist

#### 33 — Export Results

> *Export run results for independent analyses using cloud-compute outputs.*

| Table | Columns Used |
|-------|-------------|
| `output_ts` | All columns (tabular time series) |
| `output_grids` | `repo_uri` (Icechunk gridded data) |
| `run_files` | `uri` (raw model output files) |
| `obs_ts` | All columns (observed time series) |

**Path:** `output_ts` for tabular exports; `output_grids.repo_uri` for gridded Zarr/Icechunk data; `run_files.uri` for raw HEC-RAS/HMS output files.

---

## Notes

1. **STAC Metadata Pattern** — Stories 12, 13, 14, 16, 19, 22, and 23 rely on the `stac_metadata` URI field present on `models`, `dams`, `levees`, `gages`, and `storms`. The STAC documents are external to the relational/Iceberg data model but are explicitly referenced and discoverable through these URI columns. This is a deliberate design choice keeping rich, semi-structured metadata outside the tabular schema.

2. **Depth-Damage Functions** — Stories 9 and 11 require depth-damage functions to convert `buildings_impacted.inundation_depth` into dollar damages. These functions are external to the data model (applied by consequence tools). The data model stores all required inputs: inundation depths, building attributes, and stochastic frequency weights.

3. **Materialized Views** — Seven `mv_*` tables in `lakehouse/derived.mmd` pre-compute the most common analytical queries. The comments in that file document the source tables, refresh triggers, partition/sort strategies, and which user stories each view serves.
