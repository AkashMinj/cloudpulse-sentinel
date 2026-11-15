#!/usr/bin/env python3
"""Export recent system metrics to a CSV analytical dataset."""
import csv
import os
import sys

import psycopg2

required = ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")
missing = [name for name in required if not os.getenv(name)]
if missing:
    sys.exit("Missing environment variables: " + ", ".join(missing))

days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
if not 1 <= days <= 90:
    sys.exit("days must be between 1 and 90")

query = """
SELECT instance_id, timestamp, cpu_usage_percent, memory_usage_percent,
       disk_usage_percent, latency_ms, error_rate_percent, request_rate
FROM system_metrics
WHERE timestamp >= NOW() - (%s * INTERVAL '1 day')
ORDER BY timestamp ASC;
"""
with psycopg2.connect(
    host=os.environ["DB_HOST"],
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.environ["DB_NAME"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    connect_timeout=5,
) as connection:
    with connection.cursor() as cursor:
        cursor.execute(query, (days,))
        rows = cursor.fetchall()
        output = f"metrics-last-{days}-days.csv"
        with open(output, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "instance_id", "timestamp", "cpu_usage_percent",
                "memory_usage_percent", "disk_usage_percent", "latency_ms",
                "error_rate_percent", "request_rate",
            ])
            writer.writerows(rows)

print(f"Exported {len(rows)} metric rows to {output}")
