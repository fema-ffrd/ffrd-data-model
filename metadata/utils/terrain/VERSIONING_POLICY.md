# STAC Versioning Policy

## Purpose
This policy explains how new metadata releases are created from S3 source data assets, how unchanged and changed items are handled, and how older releases are deprecated.

This document is written for both:
- Developers who implement and operate the release scripts.
- Data users who need to understand what a version means and what to trust.

## Terminology and Scope
In this policy:
- Item: a single cataloged data unit in the release.
- Collection: a versioned grouping of items in the release.
- Data asset: a source [Amazon S3 object](https://docs.aws.amazon.com/AmazonS3/latest/userguide/upload-objects.html) referenced by an item (for example, a `.tif` file, HEC-RAS model files, and similar inputs).

Metadata format:
- Item metadata uses [STAC Item](https://docs.ogc.org/cs/25-004/25-004.html#item-object) JSON.
- Collection metadata uses [STAC Collection](https://docs.ogc.org/cs/25-004/25-004.html#collection-object) JSON.

## Plain-Language Summary
When we publish a new release, we compare current S3 TIFF objects against records from the previous release.

- If a data asset is unchanged, we copy its metadata item into the new release folder.
- If a data asset changed or is new, we generate a new metadata item with the new release version.
- If a data asset was removed, it is not included in the new collection.

A new collection version is created only when changes are detected, unless a release is forced. Deprecation of superseded assets is done in a second step.

## Key Concepts
- Release version: the version of the collection snapshot in major.minor format (for example, `1.1`).
- Item version: the version on each metadata item. Unchanged items keep their existing item version.
- Two-run process:
  - Run 1 creates the new release collection and item set.
  - Run 2 deprecates older collection/items that were superseded or removed.

## Source of Truth for Change Detection
Primary check:
- Compare `size` and `last_modified` from the previous release file.  If the file has been overwritten compare `size` and `last_modified` against the manifest record to current S3 object listing metadata.

Additional check:
- If size and timestamp are equal and both ETags are available in the manifest/current object, compare ETag.
- If no usable manifest record exists, compare current object ETag against previous item ETag as fallback.

Classification outcomes:
- unchanged
- changed
- new
- removed

Notes:
- `removed` is derived from set-difference between previous item source keys and current source keys.
- If no comparable metadata is available, the release builder classifies the item as changed (`missing_comparison_data`).

## Item Handling Rules
### Unchanged Data Asset
- The prior item is copied into the new release folder.
- The copied item is updated to the new collection context:
  - `collection` id is updated.
  - `self`, `collection`, `parent`, and `root` links are updated.
  - `latest-version` points to the copied item in the new release.
  - Any `successor-version` link is removed.
- Item `properties.version` remains unchanged.
- Item is not deprecated.

### Changed Data Asset
- A new metadata item is generated from the data asset.
- The new item gets the new release version in `properties.version`.
- The new item includes lineage:
  - `predecessor-version` points to the old item (when previous item exists).
  - `latest-version` points to the new item.
- Old item is deprecated later in Run 2.

### New Data Asset
- A new metadata item is generated.
- Item gets new release version in `properties.version`.
- `latest-version` points to itself.

### Removed Data Asset
- No item appears for it in the new collection.
- The old item is deprecated in Run 2 with reason `removed`.

## Collection Handling Rules
### New collection creation (Run 1)
- New collection is created with:
  - New release version.
  - Links to copied unchanged items and newly generated changed/new items.
  - Updated extent and temporal interval from included items.
  - `predecessor-version` link to the previous collection.
  - `latest-version` link to itself.
- Removed items are excluded.

### Old collection deprecation (Run 2)
- Previous collection is marked deprecated.
- Previous collection receives `successor-version` and `latest-version` links to the new collection.
- The updater also reconciles predecessor/successor/latest links recursively across the discovered version chain and normalizes those chain links before item links.

## Version Bump Rule
Default behavior:
- If changes are detected, bump Minor version (for example, `1.0 -> 1.1`).

Override behavior:
- If `--new-version` is provided, use that exact version.

Normalization:
- Versions are normalized to major.minor (`X.Y`).
- Legacy `X.Y.Z` values are accepted and normalized to `X.Y`.

## Forced Release Behavior
When no data-asset changes are detected:
- If `--new-version` is provided, a new collection version is still created.
- If `--force-new-release` is provided, a new collection version is also created.
- Unchanged items are copied into the new release and retain their existing item `properties.version`.
- No new item metadata is generated unless an asset is classified as changed/new.
- `change-report.json` records whether release was forced (`forced_release`).

## Safety Guard
To avoid accidental overwrite, Run 1 fails if `--new-collection-key` already exists.

## Lineage Invariants
The following invariants are intended after Run 2 completes:
- Every active item in the newest collection has one `latest-version` link.
- Every changed item in the new release has a `predecessor-version` link to the superseded item.
- Every deprecated item has `deprecated: true`, deprecation metadata, and either a `successor-version` (superseded) or reason `removed`.
- Collections in the discovered chain converge to consistent predecessor/successor/latest relationships.

## Deprecation Semantics
Deprecation is applied in Run 2 and includes:
- `deprecated: true` on superseded collection/items.
- A machine-readable reason: `superseded` or `removed`.
- A deprecation timestamp in UTC (`deprecated_at`).
- Successor linkage when applicable (`successor-version`, `latest-version`).

Reason usage:
- Use `superseded` when a newer item/collection replaces the old one.
- Use `removed` when an old item has no replacement in the new collection.

## Idempotency and Rerun Expectations
Run 1:
- Re-running with the same inputs and same target key does not overwrite an existing release (guarded by `--new-collection-key` check).
- Re-running with the same inputs and a new target version should produce equivalent manifest and change classifications, subject to source metadata timestamps/ETags at run time.

Run 2:
- Linkage updates are upserts and converge to the same predecessor/successor/latest values.
- Re-running is not a strict no-op for metadata timestamps on records that are patched again.

## Output Artifacts
Run 1 writes the following artifacts:
- New `collection.json` for the release.
- `manifest.json` with per-item tracking and detection metadata.
- `change-report.json` with classification summary and planned deprecations.

Manifest record fields produced by current scripts:
- `logical_id`
- `tif_key`
- `status` (`unchanged`, `changed`, `new`)
- `size`
- `last_modified`
- `etag`
- `item_version`
- `item_key`
- `item_href`
- `detection_method`

Change-report fields produced by current scripts include:
- `source_collection`
- `target_collection`
- `previous_collection`
- `new_collection`
- `new_version`
- `forced_release` (boolean)
- `summary` (counts by classification)
- `classification` (row-level classification)
- `planned_deprecations` (items/collection to deprecate, with reasons)
- `outputs`

No-change case:
- Without `--new-version` and without `--force-new-release`, the script writes a no-op change report (unless dry-run) and exits without creating a new collection.
- With `--new-version`, a forced release is created as defined above.

## Worked Example
Previous release contains item metadata for assets `a.tif`, `b.tif`, and `c.tif`.
Current S3 scan finds `a.tif`, `b.tif` (updated), and `d.tif`.

Classification:
- `a.tif` -> `unchanged`
- `b.tif` -> `changed`
- `d.tif` -> `new`
- `c.tif` -> `removed`

Expected Run 1 output:
- Copy metadata item for `a.tif` into new release and keep its item version.
- Generate new metadata items for `b.tif` and `d.tif` with the new release version.
- Exclude `c.tif` from the new collection.
- Write `manifest.json` and `change-report.json` reflecting these classifications.

Expected Run 2 output:
- Deprecate prior item for `b.tif` with reason `superseded`.
- Deprecate prior item for `c.tif` with reason `removed`.
- Deprecate prior collection and reconcile predecessor/successor/latest links across discovered versions.

## Operational Workflow
### Run 1: Incremental release builder
Script:
- `s3_incremental_release_builder.py`

Responsibilities:
- Detect changes.
- Copy unchanged items.
- Create new items for changed/new data assets.
- Build new collection.
- Write manifest and change report.

### Run 2: Deprecation updater
Script:
- `s3_incremental_deprecation_updater.py`

Responsibilities:
- Read `change-report.json`.
- Deprecate old collection.
- Deprecate old changed/removed items.
- Reconcile predecessor/successor/latest lineage links across discovered collection versions.

# Quick Start (Copy/Paste)
Run from `C:\development\fema\stac`.

## A) Create first metadata release (v1.0)
Tests `latest-template`.

```powershell
python .\s3-build_collection_from_item.py `
  --s3-bucket south-platte `
  --s3-prefix terrain-base/dem_south-platte_96ft `
  --s3-output-key stac-metadata/terrain-base/96ft-v1.0/collection.json `
  --s3-manifest-key stac-metadata/terrain-base/96ft-v1.0/manifest.json `
  --s3-gpkg-key terrain-base/dem_south-platte_96ft/SouthPlatte_FFRD_Metadata.gpkg `
  --s3-profile fema `
  --collection-id south-platte-terrain-base-96ft-v1.0 `
  --title "South Platte Terrain Base 96ft v1.0" `
  --description "Terrain base GeoTIFF tiles for the South Platte area (v1.0)." `
  --license proprietary `
  --root-href https://south-platte.s3.amazonaws.com/stac-metadata/terrain-base/catalog.json `
  --recursive `
  --item-version 1.0 `
  --deprecated false `
  --latest-template "{item_href}" `
  --providers-json "[{""name"":""FEMA"",""roles"": [""producer""],""url"":""https://www.fema.gov""}]" `
  --keywords "terrain,dem,elevation,south platte" `
  --summaries-json "{""gsd"":[96]}"
```

## B) Incremental two-run versioning (recommended operations path)
Run 1 preview:

```powershell
python .\s3_incremental_release_builder.py `
  --source-bucket south-platte `
  --source-prefix terrain-base/dem_south-platte_96ft `
  --stac-bucket south-platte `
  --current-collection-key stac-metadata/terrain-base/96ft-v1.0/collection.json `
  --current-manifest-key stac-metadata/terrain-base/96ft-v1.0/manifest.json `
  --new-collection-key stac-metadata/terrain-base/96ft-v1.1/collection.json `
  --recursive `
  --dry-run `
  --s3-profile fema
```

Run 1 publish:

```powershell
python .\s3_incremental_release_builder.py `
  --source-bucket south-platte `
  --source-prefix terrain-base/dem_south-platte_96ft `
  --stac-bucket south-platte `
  --current-collection-key stac-metadata/terrain-base/96ft-v1.0/collection.json `
  --current-manifest-key stac-metadata/terrain-base/96ft-v1.0/manifest.json `
  --new-collection-key stac-metadata/terrain-base/96ft-v1.1/collection.json `
  --recursive `
  --s3-profile fema
```

Run 2 deprecate previous release:

```powershell
python .\s3_incremental_deprecation_updater.py `
  --stac-bucket south-platte `
  --change-report-key stac-metadata/terrain-base/96ft-v1.1/change-report.json `
  --s3-profile fema
```

## Preflight Checks (Before Run 1)
```powershell
aws configure list-profiles
aws s3api head-bucket --bucket south-platte --profile fema
aws s3api head-object --bucket south-platte --key stac-metadata/terrain-base/96ft-v1.0/collection.json --profile fema
aws s3api head-object --bucket south-platte --key stac-metadata/terrain-base/96ft-v1.0/manifest.json --profile fema
aws s3 ls s3://south-platte/terrain-base/dem_south-platte_96ft/ --recursive --profile fema
```

## Troubleshooting (Top Issues)
### NoSuchBucket
- Use the real bucket in `--stac-bucket`.
- Put folder path in `--current-collection-key`.

### Refusing to overwrite existing key
- Choose a new `--new-collection-key` target path.

### No changes detected unexpectedly
- Verify source prefix and `--recursive`.
- Verify prior manifest key.
