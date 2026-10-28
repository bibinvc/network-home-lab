#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
RUN="$ROOT/run"
[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
[[ -f "$RUN/owner" && $(cat "$RUN/owner") == "network-home-lab-v1:$ROOT" ]] || { echo 'Start and verify this lab first.' >&2; exit 1; }
if [[ -n ${HLAB_TOOLS:-} ]]; then
    export PATH="$HLAB_TOOLS/usr/sbin:$HLAB_TOOLS/usr/bin:$HLAB_TOOLS/bin:$PATH"
    export LD_LIBRARY_PATH="$HLAB_TOOLS/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
fi
mkdir -p "$ROOT/evidence"
# Signal only a tcpdump process that belongs to our switch namespace.
while read -r pid; do
    if [[ -n $pid && -r /proc/$pid/comm && $(cat "/proc/$pid/comm") == tcpdump ]]; then
        kill -INT "$pid"
    fi
done < <(ip netns pids bvc-hl-switch)
sleep 1
cp -- "$RUN/results.txt" "$ROOT/evidence/connectivity.txt"
cp -- "$RUN/fault-drill.txt" "$ROOT/evidence/fault-drill.txt"
cp -- "$RUN/validation.pcap" "$ROOT/evidence/validation.pcap"
"$ROOT/lab.sh" show > "$ROOT/evidence/network-state.txt"
(cd "$ROOT" && TZ=UTC tcpdump -nn -e -r evidence/validation.pcap -c 60 'vlan and ip') > "$ROOT/evidence/packet-excerpt.txt" 2>&1
tcpdump -nn -r "$ROOT/evidence/validation.pcap" 'vlan and ip' > "$RUN/decoded-ipv4.txt" 2>/dev/null
for expected in 'BOOTP/DHCP' 'files.lab.test' '10.77.20.10.8080'; do
    grep -F "$expected" "$RUN/decoded-ipv4.txt" >/dev/null || { echo "Capture missing expected traffic: $expected" >&2; exit 1; }
done
{
    date -u '+UTC: %Y-%m-%dT%H:%M:%SZ'
    grep '^PRETTY_NAME=' /etc/os-release
    uname -r
    uname -m
    ip -V
    nft --version
    dnsmasq --version | head -n 2
    busybox 2>&1 | head -n 2
    tcpdump --version | head -n 2
} > "$ROOT/evidence/environment.txt"
echo 'Saved isolated lab outputs and trunk capture in evidence/.'
