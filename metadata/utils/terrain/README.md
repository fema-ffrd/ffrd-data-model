# Terrain metadata utilities

Command-line utilities for building and versioning STAC metadata for GeoTIFF terrain data.

## Files

| File | Purpose |
| --- | --- |
| `s3-stac_item_from_tiff.py` | Creates and uploads one STAC Item for an S3 GeoTIFF. |
| `s3-build_collection_from_item.py` | Builds Items, a Collection, and a manifest from local or S3 TIFF/VRT data; optional GeoPackage tables become Collection assets. |
| `s3-build_catalog_from_collection.py` | Builds a top-level Catalog from a local or S3 Collection. |
| `s3_incremental_release_builder.py` | Compares current S3 TIFFs with the prior release and creates the next release, manifest, and change report. |
| `s3_incremental_deprecation_updater.py` | Applies the change report to superseded Items after a successful release. |
| `stac_item_shared.py` | Shared raster inspection and STAC Item construction. |
| `requirements.txt` | Runtime and STAC validation dependencies. |
| `requirements-lock.txt` | Pinned dependency versions. |

## Setup

```bash
python -m pip install -r requirements.txt
```

S3 commands require AWS credentials with read/write access to the relevant buckets. Use `--s3-profile` when a named profile is needed.

## Usage

Create an initial Collection from S3 terrain files:

```bash
python s3-build_collection_from_item.py \
  --s3-bucket bucket-name \
  --s3-prefix terrain/v1.0 \
  --s3-output-key stac/terrain/v1.0/collection.json \
  --item-version 1.0 \
  --latest-template '{item_json}'
```

Build and then finalize an incremental release:

```bash
python s3_incremental_release_builder.py \
  --source-bucket bucket-name \
  --source-prefix terrain/current \
  --stac-bucket bucket-name \
  --current-collection-key stac/terrain/v1.0/collection.json \
  --new-collection-key stac/terrain/v1.1/collection.json

python s3_incremental_deprecation_updater.py \
  --stac-bucket bucket-name \
  --change-report-key stac/terrain/v1.1/change-report.json
```

Use `--dry-run` before either incremental command and `python <script> --help` for all options. See `../VERSIONING_POLICY.md` for release behavior.

## Assumptions and limitations

- Release versions use `Major.Minor` (`X.Y`); patch components are not retained.
- Raster bounds are transformed to EPSG:4326 for STAC geometry and bbox values.
- Incremental change detection depends on S3 object size, modification time, and ETag; multipart ETags are not content hashes.
- Deprecation is a separate second step and should run only after the new release is verified.
- Local mode is supported by the Collection and Catalog builders; single-item and incremental workflows are S3-oriented.
- GeoPackage support reads table metadata only and does not validate feature geometry.
