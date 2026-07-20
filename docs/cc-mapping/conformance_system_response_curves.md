# Lakehouse Mapping README

This document maps source conformance records to the lakehouse structures model.

Source file:
- `conformance_system_response_curves.json`

Target diagram/model:
- `structures.mmd`

## Entity Mapping

1. Dams (`dams`)
- Use when `location` starts with `nid_` and/or `nidid` is populated.
- Typical source fields:
  - `hydraulic_model_unit` -> `dams.hydraulic_model_unit`
  - `location` -> `dams.location`
  - `nidid` -> `dams.nid_id`
  - `nid_dam_name` -> `dams.nid_dam_name`
  - `top_elev` -> `dams.top_elev` (cast to float)
  - `toe_elev` -> `dams.toe_elev` (cast to float)
  - `source` -> `dams.source`

2. Levees (`levees`)
- Use when `location` starts with `nld_` and/or NLD fields are populated.
- Typical source fields:
  - `hydraulic_model_unit` -> `levees.hydraulic_model_unit`
  - `location` -> `levees.location`
  - `breach_fid` -> `levees.breach_fid`
  - `nld_system_id` -> `levees.nld_system_id`
  - `nld_system_name` -> `levees.nld_system_name`
  - `nld_segment_id` -> `levees.nld_segment_id`
  - `top_elev` -> `levees.top_elev` (cast to float)
  - `toe_elev` -> `levees.toe_elev` (cast to float)
  - `source` -> `levees.source`

3. Response curve points (`structure_response_curves`)
- Each source location has a `probability-stage` object with:
  - `xvalues[]`
  - `ydistributions[]`
- Build one row per aligned index `i`:
  - `point_order` = `i`
  - `probability` = normalized probability value for point `i`
  - `distribution_type` = `ydistributions[i].type`
  - `distribution_params_json` = JSON string of `ydistributions[i].parameters`
  - `stage_value` = normalized stage value for point `i`
  - `failure_mode` = location-level `failure_mode`
  - `source` = location-level `source`

4. Event-linked failure elevations (`structure_failure_elev`)
- Join structure response identifiers to event-specific failure elevations when provided by event processing.
- Grain intent: one row per (`structure_response_id`, `event_id`).

## Normalization Rules

- Iceberg has no enforced PK/FK constraints; keys are logical.
- Cast numeric strings to numeric columns where possible.
- Preserve raw source values in ingestion metadata when casts fail.
- Validate `xvalues` and `ydistributions` lengths before expanding points.

## Known Source Caveat

Some levee records appear to have mixed semantics between source fields and probability-stage arrays. Use profile-based normalization:
- If `xvalues` behaves like stage and `ydistributions.parameters.value` behaves like probability, map accordingly.
- Keep the raw payload for audit and reprocessing.

## Example Classification

- Dam-like record example: `location = nid_tx00001`, `nidid = TX00001`.
- Levee-like record example: `location = nld_1605557001_1`, `nld_system_id = 1605557001`.
