#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-/home/slawler/venvs/py312/bin/python}"

BUCKET=${BUCKET:-south-platte}
COLLECTION=${COLLECTION:-test-south-platte-terrain-base-96ft}

CATALOG=${CATALOG:-s3://$BUCKET/stac-metadata/catalog.json}
OUTPUT=${OUTPUT:-s3://south-platte/stac-portable/}

PARQUET_NAME=${PARQUET_NAME:-}
ASSET_KEY=${ASSET_KEY:-items-geoparquet}
SCHEMA_VERSION=${SCHEMA_VERSION:-1.1.0}

# Example S3 override:
# BUCKET=my-bucket COLLECTION=my-collection CATALOG=s3://my-bucket/stac-metadata/catalog.json "$0"

if [[ ! -x "$PYTHON" ]]; then
    echo "Python executable not found: $PYTHON" >&2
    echo "Set PYTHON to the environment containing boto3, pystac, and stac-geoparquet." >&2
    exit 1
fi

cmd=(
    "$PYTHON" "build_portable_geoparquet_collection.py"
    "$CATALOG"
    "$COLLECTION"
    --output "$OUTPUT"
    --asset-key "$ASSET_KEY"
    --schema-version "$SCHEMA_VERSION"
)

if [[ -n "$PARQUET_NAME" ]]; then
    cmd+=(--parquet-name "$PARQUET_NAME")
fi

"${cmd[@]}"
