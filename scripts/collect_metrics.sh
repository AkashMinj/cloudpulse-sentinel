#!/bin/bash

LOG_FILE="$HOME/cloudpulse-sentinel/logs/metrics.log"
URL="http://localhost:8000/api/v1/metrics/collect"
MAX_RETRIES=3
RETRY_DELAY=5

for attempt in $(seq 1 $MAX_RETRIES); do

    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Collection attempt $attempt/$MAX_RETRIES" >> "$LOG_FILE"

    response=$(curl -sS -w "\nHTTP_STATUS:%{http_code}" \
        --connect-timeout 5 \
        --max-time 30 \
        -X POST "$URL" 2>&1)

    status=$(echo "$response" | sed -n 's/HTTP_STATUS://p')
    body=$(echo "$response" | sed '/HTTP_STATUS:/d')

    if [ "$status" = "200" ]; then
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] SUCCESS: $body" >> "$LOG_FILE"
        exit 0
    fi

    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ERROR HTTP $status: $body" >> "$LOG_FILE"

    if [ "$attempt" -lt "$MAX_RETRIES" ]; then
        sleep "$RETRY_DELAY"
    fi
done

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] FAILED: All collection attempts exhausted" >> "$LOG_FILE"
exit 1
