# Lakehouse Model Notes

This folder contains the lakehouse-oriented Mermaid diagrams:

- `events.mmd`
- `models.mmd`
- `structures.mmd`
- `derived.mmd`
- `unified.mmd`
- `unified-exec.mmd`
- `example-mapping.md` (source-to-lakehouse mapping for structures data)

## Next steps

Enum enforcement note:
- Iceberg does not provide a native enum type.
- Use `string` or `int` columns for enum-like fields (for example `run_type`, `model_type`).
- Enforce allowed values in ingestion/ETL checks and/or query engine constraints.
- Keep a small lookup/reference table for code-to-label mapping when numeric codes are used.

1. Lifecycle operations notes
- Add compaction cadence guidance and target file size ranges by table family.
- Add snapshot retention policy and cleanup interval recommendations.

2. Data quality checks
- Add required checks for `output_ts` and `obs_ts`:
  - null checks on key fields
  - duplicate key checks at table grain
  - monotonic timestamp checks where expected
  - other?

3. Run-type contract
- Add explicit allowed values/examples for `run_type` and expected meaning.
- Add rules for how reruns (`run_id`, `run_version`) update derived tables.
- other?

4. Observability and SLAs
- Add freshness expectations for each derived table.
- Add failure/retry behavior for materialization jobs.
- other?



## Notes
 - seasonal distributions needed
 - other?
 - runtime / errors / metadata / etc.
 - run_type vs event_type
 - model_event_files: str vs blob
 - https://github.com/sozip/sozip-spec
 - filter out hms vars?
