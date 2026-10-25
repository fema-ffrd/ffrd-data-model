#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-$SCRIPT_DIR/.venv313/bin/python}"

BUCKET=${BUCKET:-south-platte}

MODEL=${MODEL:-big-thompson}

VERSION=${VERSION:-v1.0}

RAS_ROOT=s3://$BUCKET/calibration/hydraulics/$MODEL/$VERSION
RAS_PROJECT=${RAS_PROJECT:-$RAS_ROOT/$MODEL.prj}
RAS_PROJECTION=${RAS_PROJECTION:-$RAS_ROOT/Projection/Big_Thompson_Basin.prj}

# HMS_ROOT=s3://$BUCKET/calibration/hydrology/$MODEL/$VERSION
# HMS_PROJECT=${HMS_PROJECT:-$HMS_ROOT/Big_Thompson.hms}
# HMS_PROJECTION=${HMS_PROJECTION:-$HMS_ROOT/data/big_thompson_subbasins.prj}

if [[ ! -x "$PYTHON" ]]; then
    echo "Python executable not found: $PYTHON" >&2
    echo "Set PYTHON to the Python 3.13 environment containing hecstac." >&2
    exit 1
fi

"$PYTHON" "$SCRIPT_DIR/create_ras_stac.py" \
    $RAS_PROJECT \
    --output s3://$BUCKET/stac-metadata/calibration/hydraulics/$MODEL/$VERSION/ \
    --projection $RAS_PROJECTION \
    --scope both \
    --id $MODEL-$VERSION

# "$PYTHON" "$SCRIPT_DIR/create_hms_stac.py" \
#     $HMS_PROJECT \
#     --output s3://$BUCKET/stac-metadata/calibration/hydrology/$MODEL/$VERSION/ \
#     --projection $HMS_PROJECTION \
#     --id $MODEL-hms-$VERSION
