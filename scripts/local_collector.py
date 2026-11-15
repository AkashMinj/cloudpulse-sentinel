#!/usr/bin/env python3
"""Local Compose collector that stores one backend/container sample periodically."""

import json
import os
import time
import urllib.error
import urllib.request

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000").rstrip("/")
INTERVAL = max(10, int(os.getenv("COLLECTION_INTERVAL_SECONDS", "30")))


def collect_once() -> None:
    request = urllib.request.Request(
        f"{BACKEND_URL}/api/v1/metrics/collect",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=35) as response:
        result = json.loads(response.read().decode("utf-8"))
        print(
            f"[local-collector] stored metric_id={result.get('metric_id')} "
            f"instance={result.get('instance_id')}",
            flush=True,
        )


def main() -> None:
    print(
        f"[local-collector] target={BACKEND_URL} interval={INTERVAL}s",
        flush=True,
    )
    while True:
        started = time.monotonic()
        try:
            collect_once()
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"[local-collector] collection failed: {exc}", flush=True)
        except Exception as exc:
            print(
                f"[local-collector] unexpected error: {type(exc).__name__}: {exc}",
                flush=True,
            )
        elapsed = time.monotonic() - started
        time.sleep(max(1, INTERVAL - elapsed))


if __name__ == "__main__":
    main()
