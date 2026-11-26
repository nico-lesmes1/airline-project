#!/usr/bin/env bash
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
STREAM_NAME="${STREAM_NAME:-airline-events-team01}"

if [[ "${DELETE_STREAM_CONFIRM:-}" != "yes" ]]; then
    echo "Set DELETE_STREAM_CONFIRM=yes to delete stream $STREAM_NAME in $REGION." >&2
    exit 2
fi

if ! aws kinesis describe-stream-summary \
    --region "$REGION" \
    --stream-name "$STREAM_NAME" >/dev/null 2>&1; then
    printf 'Stream %s does not exist; nothing to delete.\n' "$STREAM_NAME"
    exit 0
fi

aws kinesis delete-stream \
    --region "$REGION" \
    --stream-name "$STREAM_NAME" \
    --enforce-consumer-deletion
aws kinesis wait stream-not-exists --region "$REGION" --stream-name "$STREAM_NAME"
printf 'Deleted stream %s in %s.\n' "$STREAM_NAME" "$REGION"
