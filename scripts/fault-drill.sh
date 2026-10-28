#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
RUN="$ROOT/run"
[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
[[ -f "$RUN/owner" && $(cat "$RUN/owner") == "network-home-lab-v1:$ROOT" ]] || { echo 'Start this lab first.' >&2; exit 1; }
exec > >(tee "$RUN/fault-drill.txt") 2>&1
restore() { ip -n bvc-hl-switch link set p-client up; }
trap restore EXIT
probe() { ip netns exec bvc-hl-client curl --noproxy '*' -fsS --connect-timeout 1 --max-time 3 http://10.77.20.10:8080; }
echo 'FAULT DRILL: client access-port shutdown and recovery'
date -u '+UTC: %Y-%m-%dT%H:%M:%SZ'
echo '1. Positive control: service must be reachable.'
probe
echo '2. Shut down only the client access port in the virtual switch.'
ip -n bvc-hl-switch link set p-client down
if probe; then echo 'FAIL: request unexpectedly succeeded with the port down.'; exit 1; fi
echo '3. Inspect the link state and client neighbour table.'
ip -br -n bvc-hl-switch link show p-client
ip -n bvc-hl-client neigh show
echo '4. Restore the access port and verify the original service.'
restore
sleep 1
probe
echo 'PASS: access-port fault reproduced, diagnosed and recovered.'
