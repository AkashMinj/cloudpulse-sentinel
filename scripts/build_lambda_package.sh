#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build/lambda"
OUTPUT="$ROOT_DIR/incident_processor.zip"

command -v docker >/dev/null 2>&1 || {
  echo "Docker is required to build a Lambda-compatible dependency package." >&2
  exit 1
}

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$ROOT_DIR:/workspace" \
  -w /workspace \
  python:3.12-slim \
  bash -euc '
    python -m pip install --no-cache-dir -r app/lambda-requirements.txt -t build/lambda
    cp app/incident_processor_lambda.py build/lambda/
    cp app/incident_engine.py build/lambda/
  '

python3 - "$BUILD_DIR" "$OUTPUT" <<'PY'
import os
import sys
import zipfile

source, output = sys.argv[1:]
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for base, dirs, files in os.walk(source):
        dirs[:] = [directory for directory in dirs if directory not in {"__pycache__", "tests", "test"}]
        for name in files:
            if name.endswith((".pyc", ".pyo")) or name == "RECORD":
                continue
            path = os.path.join(base, name)
            archive.write(path, os.path.relpath(path, source))

print(f"Created {output} ({os.path.getsize(output) / 1024 / 1024:.2f} MB)")
PY
