# Model metadata utilities

Command-line utilities for creating standalone STAC Items for HEC-HMS and HEC-RAS models and attaching derived Parquet outputs.

## Files

| File | Purpose |
| --- | --- |
| `create_hms_stac.py` | Creates one STAC Item containing the input files beside an HEC-HMS `.hms` project. |
| `create_ras_stac.py` | Creates HEC-RAS STAC Items for the active plan, all discovered assets, or both. |
| `update_stac_with_parquet.py` | Adds a DSS-derived Parquet asset and version metadata to an existing Item. |
| `stac_utils.py` | Shared local/S3 I/O, AWS, CRS, and path helpers. |
| `example.sh` | Example S3 workflow for a HEC-RAS project. |

## Requirements

Python 3.13 with `boto3`, `hecstac`, `pyproj`, and `pystac`. S3 operations also require AWS credentials with access to the requested objects and output prefixes.

## Usage

Run commands from this directory. Inputs and outputs may be local paths or `s3://` URIs.

```bash
python create_hms_stac.py /path/to/model.hms \
  --output /path/to/stac/ \
  --projection EPSG:5070 \
  --id model-v1.0

python create_ras_stac.py s3://bucket/models/model.prj \
  --output s3://bucket/stac/ \
  --projection s3://bucket/models/projection.prj \
  --scope both \
  --id model-v1.0

python update_stac_with_parquet.py \
  --item s3://bucket/stac/model-v1.0.json \
  --source-dss s3://bucket/models/input.dss \
  --parquet s3://bucket/derived/input.parquet \
  --version v1.1
```

Use `python <script> --help` for all options. The variables in `example.sh` can be overridden to run its sample workflow.

## Assumptions and limitations

- Model files are discovered relative to the project file; HMS discovery is recursive, while RAS requires `--recursive` for nested assets.
- HMS excludes known result directories and suffixes, but otherwise includes every file beside the project.
- RAS active scope requires a current plan and its referenced geometry and flow files.
- CRS must be supplied as CRS text or a local/S3 WKT file when it cannot be inferred.
- `--lightweight` skips the RAS footprint calculation; `--no-validate` skips STAC validation.
- Items are standalone; these scripts do not create a STAC Collection or Catalog.
- The Parquet updater requires the source DSS URI to match an existing asset exactly and updates the Item in place unless `--output` is provided.
