# Data Model Traceability
## How the FFRD Data Model Supports Each User Story

This document maps each user story to the specific tables and relationships in the data model that enable it. References point to the four domain diagrams: **Events** (`events.mmd`), **Models** (`models.mmd`), **Structures** (`structures.mmd`), and **Management** (`management.mmd`).

---

## CC Admin

### Story 1 — All Versions
> *Determine which manifest, linkage version, and plugin versions were used for an event.*

| Table | Role |
|-------|------|
| `runs` | Entry point — identifies the specific execution for an event + model combination |
| `run_manifest` | Join table linking a run to the manifest that governed it |
| `manifests` | Records `manifest_version`, `linkage_version`, and source `uri` |
| `manifest_plugins` | Associates a manifest with the plugins active at execution time |
| `plugins` | Records each `plugin_name` and `plugin_version` |

**Query path:** `runs` → `run_manifest` → `manifests` + `manifest_plugins` → `plugins`

---

### Story 2 — Reliability and Performance
> *Understand how long a model or event took to run, identify failed events, and review error messages.*

| Table | Role |
|-------|------|
| `runs` | `success bool` flags failed runs; `timestamp` records execution time |
| `run_logs` | Links each run to its cloud log `uri` for full error message retrieval |

**Query path:** Filter `runs` on `success = false`, join `run_logs` to retrieve the log URI for error detail.

> **Gap noted:** `runs` currently lacks `start_time` / `end_time` fields for duration tracking. Consider adding these to `runs` to fully support this story.

---

### Story 3 — Re-runs and Hotfixes
> *Identify which events required hot-fix reruns, understand the underlying issue, and determine which model version resolves it.*

| Table | Role |
|-------|------|
| `hotfixes` | Records `original_run_id`, `rerun_id`, `issue_description`, `status`, and `resolved_at` |
| `runs` | Provides context for both the original failing run and the rerun |
| `models` | `resolution_model_id` FK identifies which model version resolved the issue |
| `events` | (via `runs.event_id`) identifies which event triggered the hotfix |

**Query path:** `hotfixes` → `runs` (original + rerun) → `events`; `hotfixes.resolution_model_id` → `models`

---

### Story 4 — Resources and Cost Estimates
> *Evaluate run costs, basin costs, month-to-date spending, projected completion costs, and resource utilization.*

| Table | Role |
|-------|------|
| `run_resources` | Records `cpu_hours`, `memory_gb`, `storage_gb`, and `compute_cost` per run |
| `runs` | Links resource records to specific events and models |
| `models` | `geom` field enables spatial rollup to basin-level cost summaries |

**Query path:** Aggregate `run_resources.compute_cost` grouped by `runs.event_id` or model basin geometry for basin-level and period-level rollups.

---

## Conformance Lead

### Story 5 — Conformance Metrics
> *Determine whether a basin meets conformance metrics and identify failing checks.*

| Table | Role |
|-------|------|
| `runs` | `run_type enum` can distinguish conformance runs from calibration runs |
| `output_ts` | Provides the modeled time series values that conformance checks are computed against |
| `output_grids` | Provides gridded hazard outputs for spatial conformance checks |
| `models` | `geom` identifies basin extent for aggregating pass/fail by basin |

> **Gap noted:** A `conformance_checks` table (check name, threshold, pass/fail, run_id) is not yet modeled and would be needed to store check results directly rather than deriving them at query time.

---

### Story 6 — Event Filtering
> *Perform statistical analysis on model outputs and workflow stages to support event filtering.*

| Table | Role |
|-------|------|
| `output_ts` | Full time series per `element_id` and `run_id` — primary input for statistical analysis |
| `output_grids` | Gridded outputs for spatial statistical analysis |
| `events` | `realization_id` and `block_id` enable filtering by stochastic block or realization |
| `runs` | Links outputs back to specific events for filtering decisions |

**Query path:** Join `output_ts` → `runs` → `events` to compute statistics grouped by event attributes.

---

## Conformance Lead / Leadership / FEMA

### Story 7 — Result Provenance
> *Trace a hazard, flow, precipitation, or depth result back to the event that produced it.*

| Table | Role |
|-------|------|
| `output_ts` | Time series result anchored to `run_id` and `element_id` |
| `output_grids` | Gridded hazard result anchored to `run_id` |
| `runs` | Links result to its `event_id` and `model_id` |
| `events` | Links back to `storm_id` and `fishnet_point_id` — the stochastic inputs |
| `storms` | Provides storm metadata (type, rank, datetime, precip) for the producing event |
| `run_manifest` / `manifests` | Records the exact software versions active when the result was produced |

**Query path:** Any result in `output_ts` or `output_grids` → `runs` → `events` → `storms`; separately → `run_manifest` → `manifests` + `plugins` for software provenance.

---

## Consequences Analyst

### Story 8 — At-Risk Structures
> *Evaluate losses at selected AEP frequencies for individual structures and entire basins.*

| Table | Role |
|-------|------|
| `buildings` | Full inventory with cost fields (`building_cost`, `content_cost`) and location (`geom`) |
| `output_grids` | Hazard grids (depth, velocity) at AEP frequencies |
| `structure_response` | Fragility/response functions relating hazard to damage |
| `events` | `realization_id` supports AEP frequency assignment |

> **Gap noted:** A `structure_losses` table linking `structure_id` + `event_id` + computed loss values would support direct per-structure querying at AEP frequencies.

---

### Story 9 — Damage and Risk Reporting
> *Calculate Average Annualized Loss (AAL) for structures and basins.*

| Table | Role |
|-------|------|
| `buildings` | Structure inventory with cost basis for loss calculations |
| `structure_response` | Damage functions per structure type and failure mode |
| `events` | `realization_id` and `block_id` support AAL integration across the probability space |
| `output_grids` | Hazard grids provide depth inputs for damage computation |

> **Gap noted:** Same as Story 8 — a `structure_losses` or `aep_losses` table with pre-computed AAL values would make reporting queries efficient.

---

### Story 10 — Hazard Grids and Frequencies
> *Identify which hazard grid versions were used in consequence analyses.*

| Table | Role |
|-------|------|
| `output_grids` | Records `run_id`, `variable`, and `uri` for each gridded output |
| `runs` | Links grids to their `model_id` and `event_id` |
| `models` | `model_version` identifies the model that produced the grid |

**Query path:** `output_grids` → `runs` → `models` to retrieve model version and grid URI for any consequence input.

---

### Story 11 — Uncertainty
> *Calculate mean damages and standard deviations across realizations for each AEP.*

| Table | Role |
|-------|------|
| `events` | `realization_id` groups runs into realizations for statistical aggregation |
| `seeds` | Records per-process random seeds, enabling replication of any realization |
| `output_grids` / `output_ts` | Outputs per realization that feed into uncertainty calculations |

**Query path:** Group `output_grids` or `output_ts` by AEP band via `runs` → `events.realization_id` to compute mean and standard deviation across realizations.

---

## Data Prep Lead

### Story 12 — Authoritative Dataset Completion
> *Determine whether all required preparation and scoping datasets are complete and correctly named.*

| Table | Role |
|-------|------|
| `models` | `model_name` and `model_version` provide the naming reference for each model artifact |
| `run_files` | Records filenames and metadata for files associated with a run |

> **Gap noted:** A `datasets` or `prep_datasets` table (dataset name, expected name, status, completeness flag) is not yet modeled and would be needed to track dataset readiness against a checklist.

---

### Story 13 — Dam Scoping Table
> *Visualize the Dam Scoping Table spatially.*

| Table | Role |
|-------|------|
| `dams` | Records dam name, NID identifier, source, and `model_id` |
| `model_elements` | Associates dams with their model element and geometry (`geom`) |
| `models` | Provides basin-level spatial context |

**Query path:** `dams` → `model_elements` (for `geom`) to render dam locations alongside scoping decisions.

> **Gap noted:** A `dam_scoping` table with explicit scoping decision fields (include/exclude, rationale, analyst) would formalize the scoping workflow beyond what `dams` currently captures.

---

### Story 14 — Data Source Traceability
> *Identify the source, version, and acquisition date of datasets such as terrain and NLCD.*

| Table | Role |
|-------|------|
| `levees` | `source` field records the data origin |
| `dams` | `source` field records the data origin |
| `buildings` | `inventory_source` and `inventory_version` track structure inventory provenance |

> **Gap noted:** A general `input_datasets` table (dataset type, source, version, acquisition date, uri) would provide a consistent provenance record for terrain, NLCD, and other raster/vector inputs that are not currently tracked.

---

## H&H Engineer

### Story 15 — Comparison of Observed vs Computed Data
> *Compare modeled frequency results against observed gage data.*

| Table | Role |
|-------|------|
| `obs_ts` | Observed time series keyed to `gage_id` |
| `output_ts` | Modeled time series keyed to `element_id` and `run_id` |
| `gages` | Links observed data to location; `ams` array stores annual maximum series |
| `model_elements` | `gage_id` FK co-locates a model element with its corresponding gage |

**Query path:** Join `model_elements` on `gage_id` → `obs_ts` and `output_ts` at the same location and variable for direct observed vs. modeled comparison.

---

### Story 16 — Export Models
> *Export or download models.*

| Table | Role |
|-------|------|
| `run_files` | Stores raw model file blobs and metadata for download |
| `models` | Identifies model name, type, and version |
| `runs` | Links files to specific run instances |

**Query path:** `models` → `runs` → `run_files` to retrieve downloadable model artifacts.

---

### Story 17 — Flood Validation
> *View modeled flood extents for events of interest.*

| Table | Role |
|-------|------|
| `output_grids` | Stores gridded outputs (depth, extent) keyed to `run_id` and `variable` |
| `runs` | Links grids to `event_id` for filtering by event of interest |
| `events` | Identifies the event (storm, realization) for which extents are requested |

**Query path:** `events` → `runs` → `output_grids` filtered by `variable = 'depth'` or `'extent'`.

---

### Story 18 — Dam and Levee Breach Locations
> *Identify where dams and levees fail during events.*

| Table | Role |
|-------|------|
| `structure_failure_elev` | Records failure elevation per structure per event |
| `dams` / `levees` | Provide structure identity and location |
| `model_elements` | Provides `geom` for spatial rendering of breach locations |
| `events` | Scopes failures to specific simulated events |

**Query path:** `events` → `structure_failure_elev` → `dams` or `levees` → `model_elements` for geometry.

---

### Story 19 — Input Datasets
> *Identify supporting datasets and versions used by a model.*

| Table | Role |
|-------|------|
| `models` | `model_version` identifies the version of the model |
| `model_linkages` | Records upstream donor model connections and versions |
| `run_manifest` / `manifests` | Records linkage version and plugin versions active at run time |

> **Gap noted:** Same as Story 14 — an `input_datasets` table with explicit model-to-dataset relationships would fully support this story.

---

### Story 20 — Model Features
> *Verify feature connectivity and linkages across RAS, HMS, and ResSim models.*

| Table | Role |
|-------|------|
| `model_elements` | Records all features (junctions, subbasins, 2D flow areas, BCs) per model |
| `model_linkages` | Records donor/receiver site connections across model types |
| `models` | Identifies model type (`hec-hms`, `hec-ras`, `ressim`) |

**Query path:** `model_linkages` joined to `models` on both donor and receiver sides to traverse the full inter-model connectivity graph.

---

### Story 21 — Model Versions
> *Identify which model version produced a result.*

| Table | Role |
|-------|------|
| `runs` | `model_id` FK links any result to its producing model |
| `models` | `model_version` records the version string |
| `manifests` | Records `linkage_version` active for the run |

**Query path:** Any result in `output_ts` or `output_grids` → `runs.model_id` → `models.model_version`.

---

### Story 22 — RAS Parameters Outside RAS
> *View key model parameters (Manning's n, timestep, simulation window) outside of RAS.*

| Table | Role |
|-------|------|
| `runs` | `metadata uri` points to a structured metadata document for the run |
| `run_files` | Raw model files can be parsed to extract parameter values |
| `models` | `model_version` scopes parameters to the correct version |

> **Gap noted:** A `model_parameters` table (model_id, parameter_name, parameter_value, units) would allow direct querying of Manning's n, timestep, and simulation window without parsing raw files.

---

### Story 23 — Starting Conditions
> *Review initial conditions such as reservoir elevations for a run.*

| Table | Role |
|-------|------|
| `runs` | `metadata uri` can reference a structured initial conditions document |
| `run_files` | Stores the initial conditions file for a run |

> **Gap noted:** A `run_initial_conditions` table (run_id, element_id, variable, value, units) would allow direct querying of reservoir elevations and other initial conditions.

---

### Story 24 — Validate HMS and RAS Flows
> *Compare peak flows between HMS and RAS at the same location.*

| Table | Role |
|-------|------|
| `output_ts` | Flow time series keyed to `element_id` and `run_id` |
| `model_elements` | Identifies element type and model; `geom` enables spatial co-location |
| `model_linkages` | `donor_site_id` / `receiver_site_id` explicitly names the hand-off point |
| `models` | Distinguishes HMS vs. RAS runs for the same event |

**Query path:** At a linkage point, query `output_ts` for the `donor_site_id` element (HMS run) and the `receiver_site_id` element (RAS run) for the same event and compare peak values.

---

### Story 25 — Verify Naming Conventions
> *Verify feature names against authoritative naming standards.*

| Table | Role |
|-------|------|
| `model_elements` | `element` field holds the feature name as modeled |
| `levees` | `nld_name` and `nld_segment_id` provide the authoritative NLD name for comparison |
| `dams` | `nid_name` provides the authoritative NID name for comparison |
| `gages` | `gage_name` and `gage_owner` provide authoritative gage identifiers |

**Query path:** Compare `model_elements.element` against `levees.nld_name`, `dams.nid_name`, or `gages.gage_name` to flag naming mismatches.

---

## H&H Engineer / Conformance Lead

### Story 26 — Errors and Events
> *Review volume errors, failed events, and failure causes.*

| Table | Role |
|-------|------|
| `runs` | `success bool` identifies failed runs |
| `run_logs` | Log URI provides error messages and volume error details |
| `events` | Links failed runs to the specific stochastic event |
| `hotfixes` | `issue_description` records the diagnosed cause of failure |

**Query path:** Filter `runs` on `success = false` → `run_logs` for error messages; join `hotfixes` on `original_run_id` to see if a cause has been recorded.

---

## H&H Engineer / Integration Lead

### Story 27 — Model Connections
> *Identify upstream and downstream model relationships.*

| Table | Role |
|-------|------|
| `model_linkages` | Explicitly records donor model → receiver model relationships with site-level detail |
| `models` | `model_type` and `model_name` identify each node in the network |

**Query path:** Graph traversal on `model_linkages` using `donor_model_id` and `receiver_model_id` to walk upstream or downstream from any model.

---

## Hazard Analyst

### Story 28 — Trace Results
> *Determine which events contributed to a 100-year or 2,000-year hazard result.*

| Table | Role |
|-------|------|
| `output_grids` | Hazard grids at AEP frequencies keyed to `run_id` |
| `runs` | Links each grid to its `event_id` |
| `events` | `realization_id` and `block_id` identify the stochastic contributor |
| `storms` | Storm metadata (rank, type, precip) characterizes the contributing event |

**Query path:** Identify the `output_grids` records representing the target AEP → `runs.event_id` → `events` → `storms` to characterize what drove the hazard level.

---

## Integration Lead

### Story 29 — Diffs Between Model Versions
> *Identify differences between calibration and conformance model variants.*

| Table | Role |
|-------|------|
| `models` | `model_version` distinguishes calibration from conformance variants |
| `model_elements` | Element inventory can be compared across `model_id` values to detect additions, removals, or changes |
| `model_linkages` | Linkage configurations can be compared across versions |
| `manifests` | `linkage_version` tracks which linkage was active per run |

**Query path:** Join `model_elements` for two `model_id` values (calibration vs. conformance) and diff the element lists; similarly diff `model_linkages` donor/receiver pairs.

---

### Story 30 — Linkage Diffs
> *Review changes between linkage versions.*

| Table | Role |
|-------|------|
| `manifests` | `linkage_version` field identifies the linkage version |
| `model_linkages` | Records donor/receiver site pairs; diffing across versions shows what changed |
| `run_manifest` | Associates runs with specific manifests for version attribution |

**Query path:** Compare `model_linkages` records associated with two different `manifests.linkage_version` values to identify changed, added, or removed connections.

---

## Leadership / FEMA

### Story 31 — Uncertainty
> *Understand uncertainty ranges associated with estimates.*

| Table | Role |
|-------|------|
| `events` | `realization_id` groups the stochastic ensemble |
| `seeds` | Enables full replication of any realization for uncertainty decomposition |
| `output_grids` / `output_ts` | Per-realization outputs for computing spread across the ensemble |

**Query path:** Aggregate `output_grids` or `output_ts` by AEP band grouped on `events.realization_id` to compute mean, standard deviation, and confidence intervals.

---

### Story 32 — Understand Risk
> *Understand flood hazard at standard frequencies for a basin.*

| Table | Role |
|-------|------|
| `output_grids` | Frequency-based hazard grids (100-yr, 500-yr, etc.) keyed to `run_id` |
| `models` | `geom` identifies basin extent |
| `runs` | Links grids to events and models |
| `events` | `event_type` or `realization_id` scopes to the relevant frequency band |

**Query path:** Filter `output_grids` by frequency variable → `runs` → `models.geom` to render basin-level hazard maps at standard return periods.

---

## Non-PTS Data Scientist

### Story 33 — Export Results
> *Export run results for independent analyses.*

| Table | Role |
|-------|------|
| `output_ts` | Time series results exportable by run, element, or variable |
| `output_grids` | Gridded results with `uri` pointing to cloud-stored files for direct download |
| `run_files` | Raw model files and metadata available for download |
| `runs` | Entry point for scoping exports to specific events or model versions |

**Query path:** Select desired `run_id` values → retrieve `output_ts` rows or follow `output_grids.uri` / `run_files.data` for file-based exports.

---

## Required Metadata

Several user stories are supported by existing tables that already carry a `metadata` field. The table below defines what structured content that metadata must contain to fully satisfy each story. Where the anchor table and field are identified, no new table is needed — the metadata document at that URI or blob must conform to the schema described.

---

### `runs.metadata` — *uri pointing to a structured JSON/YAML document per run*

Stories supported: **2, 22, 23**

| Story | Required Metadata Keys |
|-------|----------------------|
| 2 — Reliability & Performance | `start_time` (ISO 8601), `end_time` (ISO 8601), `duration_sec` (float) |
| 22 — RAS Parameters Outside RAS | `parameters`: array of `{ name, value, units }` — must include at minimum `mannings_n`, `timestep`, `simulation_window_start`, `simulation_window_end` |
| 23 — Starting Conditions | `initial_conditions`: array of `{ element_id, variable, value, units }` — must include reservoir pool elevations and any non-default initial states |

---

### `run_files.metadata` — *blob of structured metadata per file artifact*

Stories supported: **12, 16**

| Story | Required Metadata Keys |
|-------|----------------------|
| 12 — Authoritative Dataset Completion | `expected_filename` (str), `actual_filename` (str), `complete` (bool), `sop_reference` (str) |
| 16 — Export Models | `file_type` (e.g. `hms_project`, `ras_project`, `ressim_project`), `model_version` (str), `export_uri` (str) |

---

### `models.metadata` — *recommend adding a `metadata uri` field to the `models` table*

Stories supported: **5, 13, 14, 19**

| Story | Required Metadata Keys |
|-------|----------------------|
| 5 — Conformance Metrics | `conformance_checks`: array of `{ check_name, threshold, result, pass }` — one entry per check evaluated against the basin |
| 13 — Dam Scoping Table | `dam_scoping`: array of `{ structure_id, dam_name, include, rationale, analyst }` — one entry per dam in the basin scoping review |
| 14 — Data Source Traceability | `input_datasets`: array of `{ dataset_type, source, version, acquisition_date, uri }` — must cover terrain, NLCD, and any other authoritative raster/vector inputs |
| 19 — Input Datasets | Same `input_datasets` array as Story 14, with an additional `model_id` reference linking each dataset to the model that consumed it |

---

### Metadata Anchor Summary

| Metadata Field | Table | Stories |
|----------------|-------|---------|
| `runs.metadata` (uri) | `runs` | 2, 22, 23 |
| `run_files.metadata` (blob) | `run_files` | 12, 16 |
| `models.metadata` (uri — *add field*) | `models` | 5, 13, 14, 19 |
