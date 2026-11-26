#!/usr/bin/env bash
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
STREAM_NAME="${STREAM_NAME:-airline-events-team01}"

if aws kinesis describe-stream-summary \
    --region "$REGION" \
    --stream-name "$STREAM_NAME" >/dev/null 2>&1; then
    SUMMARY="$(aws kinesis describe-stream-summary \
        --region "$REGION" \
        --stream-name "$STREAM_NAME" \
        --query 'StreamDescriptionSummary.[StreamModeDetails.StreamMode,OpenShardCount,RetentionPeriodHours,ConsumerCount]' \
        --output text)"
    read -r MODE SHARDS RETENTION CONSUMERS <<<"$SUMMARY"
    if [[ "$MODE" != "PROVISIONED" || "$SHARDS" != "1" || "$RETENTION" -gt 24 || "$CONSUMERS" -ne 0 ]]; then
        printf 'Existing stream does not meet the minimal profile: mode=%s shards=%s retention=%s consumers=%s\n' \
            "$MODE" "$SHARDS" "$RETENTION" "$CONSUMERS" >&2
        exit 1
    fi
    printf 'Stream %s already exists and meets the minimal profile.\n' "$STREAM_NAME"
    exit 0
fi

aws kinesis create-stream \
    --region "$REGION" \
    --stream-name "$STREAM_NAME" \
    --shard-count 1
aws kinesis wait stream-exists --region "$REGION" --stream-name "$STREAM_NAME"
aws kinesis describe-stream-summary \
    --region "$REGION" \
    --stream-name "$STREAM_NAME" \
    --query 'StreamDescriptionSummary.[StreamName,StreamModeDetails.StreamMode,OpenShardCount,RetentionPeriodHours,ConsumerCount]' \
    --output table
