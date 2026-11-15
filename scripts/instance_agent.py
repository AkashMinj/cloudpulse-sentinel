#!/usr/bin/env python3
"""Periodically push EC2/system resource metrics to a central CloudPulse API."""

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import psutil

BACKEND_URL = os.getenv("CLOUDPULSE_INGEST_URL", "").rstrip("/")
INGEST_TOKEN = os.getenv("METRICS_INGEST_TOKEN", "")
INTERVAL_SECONDS = max(10, int(os.getenv("COLLECTION_INTERVAL_SECONDS", "30")))


def instance_id() -> str:
    configured = os.getenv("INSTANCE_ID")
    if configured:
        return configured
    try:
        token_request = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            data=b"",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
            method="PUT",
        )
        with urllib.request.urlopen(token_request, timeout=2) as response:
            token = response.read().decode("utf-8")
        request = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/instance-id",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.read().decode("utf-8").strip()
    except Exception:
        return os.getenv("HOSTNAME", "unknown-instance")


def collect_payload() -> dict:
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "instance_id": instance_id(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cpu_usage_percent": cpu,
        "cpu_count": psutil.cpu_count() or 1,
        "memory_usage_percent": memory.percent,
        "memory_total_gb": round(memory.total / (1024 ** 3), 2),
        "memory_available_gb": round(memory.available / (1024 ** 3), 2),
        "disk_usage_percent": disk.percent,
        "disk_total_gb": round(disk.total / (1024 ** 3), 2),
        "disk_free_gb": round(disk.free / (1024 ** 3), 2),
    }


def send_once() -> None:
    payload = collect_payload()
    request = urllib.request.Request(
        BACKEND_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Metrics-Token": INGEST_TOKEN,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        result = json.loads(response.read().decode("utf-8"))
        print(
            f"[cloudpulse-agent] instance={payload['instance_id']} "
            f"metric_id={result.get('metric_id')} "
            f"incidents={result.get('incidents_created', 0)}",
            flush=True,
        )


def main() -> int:
    if not BACKEND_URL or not INGEST_TOKEN:
        raise SystemExit("Set CLOUDPULSE_INGEST_URL and METRICS_INGEST_TOKEN")

    if len(INGEST_TOKEN) < 32:
        raise SystemExit("METRICS_INGEST_TOKEN must contain at least 32 characters")

    endpoint = BACKEND_URL
    if not endpoint.endswith("/api/v1/metrics/ingest"):
        print("[cloudpulse-agent] warning: endpoint should end in /api/v1/metrics/ingest", flush=True)

    print(
        f"[cloudpulse-agent] target={BACKEND_URL} interval={INTERVAL_SECONDS}s",
        flush=True,
    )

    while True:
        started = time.monotonic()
        try:
            send_once()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            print(f"[cloudpulse-agent] HTTP {exc.code}: {detail}", flush=True)
        except urllib.error.URLError as exc:
            print(f"[cloudpulse-agent] API unavailable: {exc.reason}", flush=True)
        except Exception as exc:
            print(f"[cloudpulse-agent] collection failed: {type(exc).__name__}: {exc}", flush=True)

        elapsed = time.monotonic() - started
        time.sleep(max(1, INTERVAL_SECONDS - elapsed))


if __name__ == "__main__":
    raise SystemExit(main())
