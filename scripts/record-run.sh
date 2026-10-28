#!/usr/bin/env bash
# Reproduce the whole exercise in one Linux session, including capture and cleanup.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
"$ROOT/lab.sh" up
trap '"$ROOT/lab.sh" down' EXIT
"$ROOT/lab.sh" verify
"$ROOT/scripts/fault-drill.sh"
"$ROOT/scripts/capture-evidence.sh"
"$ROOT/lab.sh" down
trap - EXIT
echo 'Complete: checks, fault drill, evidence and cleanup.'
