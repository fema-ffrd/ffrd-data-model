#!/usr/bin/env bash
set -euo pipefail


# transportation
# landcover
# government-boundaries --collection boundary wrong
# fema
# nhd

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-$SCRIPT_DIR/../../../../.venv313/bin/python}"

BUCKET=${BUCKET:-south-platte}
DATASET=${DATASET:-nhd}

INPUT_PREFIX=${INPUT_PREFIX:-s3://$BUCKET/basin-data/$DATASET/}
OUTPUT_ROOT=${OUTPUT_ROOT:-s3://$BUCKET/stac-metadata/basin-data/}
COLLECTION_ID=${COLLECTION_ID:-$DATASET}

if [[ ! -x "$PYTHON" ]]; then
    echo "Python executable not found: $PYTHON" >&2
    echo "Set PYTHON to the Python 3.13 environment containing boto3, pystac, and pyproj." >&2
    exit 1
fi

"$PYTHON" "$SCRIPT_DIR/create_basin_data_stac.py" \
    "$INPUT_PREFIX" \
    --output-root "$OUTPUT_ROOT" \
    --mirror-anchor basin-data \
    --collection-id "$COLLECTION_ID"
