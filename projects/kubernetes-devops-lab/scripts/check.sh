#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$ROOT"
python3 -m py_compile app/app.py scripts/*.py tests/*.py
python3 -m unittest discover -s tests -v
python3 scripts/render.py > /dev/null
for script in scripts/*.sh; do bash -n "$script"; done
