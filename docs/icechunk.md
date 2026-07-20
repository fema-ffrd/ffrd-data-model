# Gridded Data — Icechunk Repositories

## Overview

Gridded (raster) outputs from flood models are stored in [Icechunk](https://icechunk.io) repositories rather than as relational tables. Icechunk is a chunked, cloud-native array store built on [Zarr](https://zarr.dev) conventions that provides Iceberg-compatible snapshot semantics and efficient multidimensional indexing. Metadata pointers to Icechunk repositories live in the relational schema (`observed_grids` and `output_grids` tables); the actual gridded data — characterized by dimensions like longitude, latitude, time, and variable — lives in three long-lived repos that accumulate snapshots over time.

See [../rdb/grids.mmd](../rdb/grids.mmd) for a conceptual diagram of the three repository types and how they relate to the relational catalog tables.

---

## Source Repositories

### 1. `observed_precip` — Observed Meteorology from NOAA AORC

Real-world precipitation and temperature observations.
* `storm_id` is a dimension for efficient slicing by storm.

```
<xarray.Dataset>
Dimensions:      (storm_id: 5000, lon: 2500, lat: 2500, time: 240)
Coordinates:
  * storm_id     (storm_id) int32 1 2 3 ... 5000
  * lon          (lon) float32 -97.5 -97.49 ... -87.5
  * lat          (lat) float32 24.5 24.51 ... 34.5
  * time         (time) datetime64 2017-08-25T00:00 ... 2017-09-02T23:00
Data variables:
    precip       (storm_id, time, lat, lon) float32 ...  [unit: mm]
    temperature  (storm_id, time, lat, lon) float32 ...  [unit: K]
    ...
Attributes:
    source: NOAA AORC
    crs: EPSG:4326
```

**Cataloged by:** `observed_grids` table

---

### 2. `hms_excess_precip` — HEC-HMS Synthetic Excess Precipitation

Gridded excess precipitation output from HEC-HMS runs, merged across all runs for each event (SST).
* `event_id` is a dimension for efficient slicing by event.
* `block_id` and `realization_id` are non-dimension coordinates (indexed along `event_id`) enabling efficient grouping by realization without introducing sparsity.

```
<xarray.Dataset>
Dimensions:         (event_id: 50000, lon: 2500, lat: 2500, time: 120)
Coordinates:
  * event_id        (event_id) str 'SST_2024_001' 'SST_2024_002' ...
    block_id        (event_id) int32 1 1 1 2 2 ... 500          # non-dimension coord
    realization_id  (event_id) int32 1 1 2 2 3 ... 500          # non-dimension coord
  * lon             (lon) float32 -97.5 -97.49 ... -87.5
  * lat             (lat) float32 24.5 24.51 ... 34.5
  * time            (time) int32 0 900 1800 ... 107100  [unit: seconds since event start]
Data variables:
    excess_precip   (event_id, time, lat, lon) float32 ...  [unit: mm]
Attributes:
    crs: EPSG:4326
```

**Cataloged by:** `output_grids` table

---

### 3. `ras_output` — HEC-RAS Maximum Depth and Velocity

Peak flood depths and velocities from HEC-RAS runs, merged across all runs for each event (no time dimension — spatial maximum values only). 
* `event_id` is a dimension for efficient slicing by event.
* `block_id` and `realization_id` are non-dimension coordinates enabling grouping by realization.

```
<xarray.Dataset>
Dimensions:       (event_id: 50000, lon: 5000, lat: 5000)
Coordinates:
  * event_id      (event_id) str 'SST_2024_001' 'SST_2024_002' ...
    block_id      (event_id) int32 1 1 1 2 2 ... 500           # non-dimension coord
    realization_id (event_id) int32 1 1 2 2 3 ... 500           # non-dimension coord
  * lon           (lon) float32 -97.5 -97.49 ... -87.5
  * lat           (lat) float32 24.5 24.51 ... 34.5
Data variables:
    max_depth     (event_id, lat, lon) float32 ...  [unit: m]
    max_velocity  (event_id, lat, lon) float32 ...  [unit: m/s]
Attributes:
    crs: EPSG:4326
```

**Cataloged by:** `output_grids` table

---

## Derived Repositories

Derived Icechunk repositories are materialized products computed from the source repositories above. Like Iceberg-based materialized views (see [../lakehouse/derived.mmd](../lakehouse/derived.mmd)), they are regenerated on demand and are not source-of-truth. They serve specific downstream use cases — particularly frequency/risk analysis and uncertainty quantification across the stochastic ensemble.

### `met_recurrence_grids` — Observed Precipitation Frequency Grids

Fits a frequency distribution to observed precipitation totals at each grid cell using historical storm data from NOAA AORC, then extracts values at standard recurrence intervals (10, 25, 50, 100, 250, 500-year).

**Computation:** Aggregate total precipitation per storm per cell, fit log-Pearson III (or standard precipitation frequency method) at each cell, interpolate to standard RI values.

```
<xarray.Dataset>
Dimensions:            (recurrence_interval: 6, lon: 2500, lat: 2500)
Coordinates:
  * recurrence_interval (recurrence_interval) int32 10 25 50 100 250 500  [unit: years]
  * lon                (lon) float32 -97.5 -97.49 ... -87.5
  * lat                (lat) float32 24.5 24.51 ... 34.5
Data variables:
    precip             (recurrence_interval, lat, lon) float32  [unit: mm]
    temperature        (recurrence_interval, lat, lon) float32  [unit: K]
Attributes:
    fit_method: "log-Pearson III per cell"
    source_repo: observed_precip
    storm_count: 5000
```

**Use cases:** Precipitation-frequency (DDF) curves, model input benchmarking, climate baseline comparisons.

---

### `hms_recurrence_grids` — HEC-HMS Excess Precipitation Frequency Grids by Realization

Fits a frequency distribution to excess precipitation totals at each grid cell **per realization**, then extracts values at standard recurrence intervals. Enables frequency analysis of synthetic model outputs.

**Computation:** For each realization separately, aggregate total excess precipitation per event per cell, fit frequency distribution at each cell, interpolate to standard RI values.

```
<xarray.Dataset>
Dimensions:            (realization_id: 500, recurrence_interval: 6, lon: 2500, lat: 2500)
Coordinates:
  * realization_id     (realization_id) int32 1 2 3 ... 500
  * recurrence_interval (recurrence_interval) int32 10 25 50 100 250 500  [unit: years]
  * lon                (lon) float32 -97.5 -97.49 ... -87.5
  * lat                (lat) float32 24.5 24.51 ... 34.5
Data variables:
    excess_precip      (realization_id, recurrence_interval, lat, lon) float32  [unit: mm]
Attributes:
    fit_method: "log-Pearson III per cell"
    source_repo: hms_excess_precip
    ensemble_count: 500
```

**Use cases:** Per-realization precipitation risk curves, validation of HMS-derived frequency distributions vs. observed, sensitivity to hydrologic parameterization.

---

### `inundation_probability_grids` — Probability of Inundation by Realization

Computes the empirical probability that any flooding occurs (depth > 0) at each grid cell, calculated per realization. This measures how often a location is inundated across the stochastic event sample within each realization.

**Computation:** For each realization and each cell, count how many events have `max_depth > 0`, divide by total event count in that realization.

```
<xarray.Dataset>
Dimensions:       (realization_id: 50, lon: 5000, lat: 5000)
Coordinates:
  * realization_id (realization_id) int32 1 2 3 ... 50
  * lon            (lon) float32 -97.5 -97.49 ... -87.5
  * lat            (lat) float32 24.5 24.51 ... 34.5
Data variables:
    inundation_prob (realization_id, lat, lon) float32  [unit: fraction, 0-1]
Attributes:
    source_repo: ras_output
    inundation_threshold: "depth > 0 ft"
```

**Use cases:** Per-realization inundation frequency maps, identification of permanently or frequently flooded zones, realization-specific hazard communication, sensitivity analysis to ensemble variation.

---

### `ras_recurrence_grids` — Frequency Grids by Realization

Fits a frequency distribution to the annual-max series at each grid cell **per realization**, then extracts values at standard recurrence intervals (10, 25, 50, 100, 250, 500-year). Each realization produces its own set of frequency grids, enabling per-realization risk curves and uncertainty assessment.

**Computation:** For each realization separately, collect all `max_depth` and `max_velocity` events, sort by annual maxima, fit log-Pearson III (or empirical Weibull) at each cell, interpolate to standard RI values.

```
<xarray.Dataset>
Dimensions:            (realization_id: 50, recurrence_interval: 10, lon: 5000, lat: 5000)
Coordinates:
  * realization_id      (realization_id) int32 1 2 3 ... 50
  * recurrence_interval (recurrence_interval) int32 2 5 10 25 50 ... 2000  [unit: years]
  * lon                 (lon) float32 -97.5 -97.49 ... -87.5
  * lat                 (lat) float32 24.5 24.51 ... 34.5
Data variables:
    depth              (realization_id, recurrence_interval, lat, lon) float32  [unit: m]
    velocity           (realization_id, recurrence_interval, lat, lon) float32  [unit: m/s]
Attributes:
    source_repo: ras_output
```

**Use cases:** Risk curves by realization, basin rollups, sensitivity to block/realization seed variations.

---

### `ras_recurrence_grids_stats` — Cross-Realization Confidence Bounds

Aggregates `ras_recurrence_grids` across all realizations to characterize epistemic uncertainty. Computes mean, median, standard deviation, and percentile bounds (e.g., 5th/95th) at each recurrence interval.

**Computation:** For each recurrence interval and each grid cell, extract the value across all realizations, compute distributional statistics.

```
<xarray.Dataset>
Dimensions:            (recurrence_interval: 6, lon: 5000, lat: 5000)
Coordinates:
  * recurrence_interval (recurrence_interval) int32 10 25 50 100 250 500  [unit: years]
  * lon                (lon) float32 -97.5 -97.49 ... -87.5
  * lat                (lat) float32 24.5 24.51 ... 34.5
Data variables:
    mean_depth         (recurrence_interval, lat, lon) float32  [unit: m]
    median_depth       (recurrence_interval, lat, lon) float32  [unit: m]
    std_depth          (recurrence_interval, lat, lon) float32  [unit: m]
    ci_5_depth         (recurrence_interval, lat, lon) float32  [unit: m]  # 5th percentile
    ci_95_depth        (recurrence_interval, lat, lon) float32  [unit: m]  # 95th percentile
    mean_velocity      (recurrence_interval, lat, lon) float32  [unit: m/s]
    median_velocity    (recurrence_interval, lat, lon) float32  [unit: m/s]
    std_velocity       (recurrence_interval, lat, lon) float32  [unit: m/s]
    ci_5_velocity      (recurrence_interval, lat, lon) float32  [unit: m/s]
    ci_95_velocity     (recurrence_interval, lat, lon) float32  [unit: m/s]
Attributes:
    realization_count: 500
    ci_bounds: "5th and 95th percentiles across realizations"
    source_repo: ras_recurrence_grids
```

**Use cases:** Risk maps with explicit uncertainty bands, decision-making under uncertainty, sensitivity analysis, communication of model confidence to stakeholders.


