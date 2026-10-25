# Basin data STAC utility

Builds a STAC Collection with one Item per zip file under an input S3 prefix.

## Behavior

- Remote-first: reads directly from S3 using GDAL VSI paths.
- Two-pass zip handling:
  1. Lists zip members.
  2. Opens the selected internal dataset for geospatial metadata.
- Fail-fast: exits with explicit errors when a zip cannot be interpreted.

## Files

- `create_basin_data_stac.py`: main utility.
- `example.sh`: sample command-line invocation.

## Run

```bash
./example.sh
```

Or run directly:

```bash
/home/ubuntu/south-platte/.venv313/bin/python create_basin_data_stac.py \
  s3://south-platte/basin-data/transportation/ \
  --output-root s3://south-platte/stac-metadata/basin-data/ \
  --mirror-anchor basin-data \
  --collection-id transportation
```

Mirror example:

- Input: `s3://south-platte/basin-data/fema/`
- Output root: `s3://south-platte/stac-metadata/basin-data/`
- Resolved output: `s3://south-platte/stac-metadata/basin-data/fema/`
