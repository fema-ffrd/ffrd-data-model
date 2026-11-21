# Portable collection utilities

Command-line utility for creating a standalone STAC collection with a STAC GeoParquet item archive.

## Files

| File | Purpose |
| --- | --- |
| `build_portable_geoparquet_collection.py` | Reads a source catalog+collection (local or S3), resolves item links for that collection, converts those items to STAC GeoParquet, and writes a standalone `collection.json` with the parquet mirror asset attached. |
| `example.sh` | Example environment-variable-driven workflow for creating a portable collection mirror. |

## Requirements

Python 3.13 with `boto3`, `pystac`, and `stac-geoparquet`.

## Usage

Run from this directory. Inputs and outputs may be local paths or `s3://` URIs.

```bash
python build_portable_geoparquet_collection.py \
  s3://south-platte/stac-metadata/catalog.json \
  gages

./example.sh
```

Collection input accepts:

- Collection `id` found via catalog `child` links.
- A collection href relative to the catalog.

Output includes:

- `collection-<version>.json` (standalone portable copy)
- `<collection-id>-<version>.parquet` (or `--parquet-name`)

By default, both output files are written as siblings of the source `collection.json`.
When `--output` is provided, both output files are written to that local folder
or `s3://` prefix with the source collection's nested path structure preserved
relative to the catalog root.

The source collection must include a top-level `version` field. The script fails if `version` is missing or empty.

Optional flags:

- `--parquet-name` to override the output parquet filename.
- `--output` to choose output folder or `s3://` prefix (with mirrored nested structure).
- `--asset-key` to override the collection asset key (default: `items-geoparquet`).
- `--schema-version` to select GeoParquet schema version (`1.0.0` or `1.1.0`).
- `--no-validate` to skip PySTAC validation.

The output collection adds the GeoParquet with media type `application/vnd.apache.parquet` and role `collection-mirror`, consistent with the STAC GeoParquet reference guidance.
