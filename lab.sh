#!/usr/bin/env bash
# Four isolated IPv4 VLANs. Nothing is attached to a host interface.
set -Eeuo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
RUN="$ROOT/run"
NAMES=(bvc-hl-switch bvc-hl-router bvc-hl-admin bvc-hl-services bvc-hl-client bvc-hl-guest)
if [[ -n ${HLAB_TOOLS:-} ]]; then
    export PATH="$HLAB_TOOLS/usr/sbin:$HLAB_TOOLS/usr/bin:$HLAB_TOOLS/bin:$PATH"
    export LD_LIBRARY_PATH="$HLAB_TOOLS/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
fi
export HLAB_ROOT="$ROOT" HLAB_RUN="$RUN"
need_root() { [[ $EUID -eq 0 ]] || { echo 'Run with sudo in Linux/WSL2.' >&2; exit 1; }; }
ns() { ip netns exec "bvc-hl-$1" "${@:2}"; }
owned() { [[ -f "$RUN/owner" ]] && [[ $(cat "$RUN/owner") == "network-home-lab-v1:$ROOT" ]]; }
down() {
    owned || { echo 'No matching ownership record; refusing cleanup.' >&2; return 1; }
    while IFS= read -r name; do
        case " ${NAMES[*]} " in *" $name "*) ;; *) echo 'Invalid state record.' >&2; return 1 ;; esac
        [[ $name == bvc-hl-* ]] || return 1
        if ip netns list | cut -d' ' -f1 | grep -Fxq "$name"; then
            while read -r pid; do [[ -z $pid ]] || kill "$pid" 2>/dev/null || true; done < <(ip netns pids "$name")
            ip netns del "$name"
        fi
    done < "$RUN/created"
    rm -f -- "$RUN/owner" "$RUN/created"
    echo 'Removed the six lab namespaces; host routes and firewall were not changed.'
}
up() {
    local tool name role vid mac
    for tool in ip bridge nft dnsmasq busybox curl tcpdump timeout ping; do
        command -v "$tool" >/dev/null || { echo "Missing tool: $tool. See README prerequisites." >&2; return 1; }
    done
    busybox udhcpc --help >/dev/null 2>&1 || { echo 'BusyBox needs the udhcpc applet.' >&2; return 1; }
    [[ ! -f "$RUN/owner" ]] || { echo 'Existing run state: inspect it or run ./lab.sh down first.' >&2; return 1; }
    for name in "${NAMES[@]}"; do
        if ip netns list | cut -d' ' -f1 | grep -Fxq "$name"; then
            echo "Namespace $name already exists; refusing to overwrite it." >&2; return 1
        fi
    done
    mkdir -p "$RUN"
    printf '%s\n' "network-home-lab-v1:$ROOT" > "$RUN/owner"
    : > "$RUN/created"
    trap 'echo "Setup failed; cleaning up this run." >&2; down || true' ERR
    for name in "${NAMES[@]}"; do
        ip netns add "$name"
        printf '%s\n' "$name" >> "$RUN/created"
        ip -n "$name" link set lo up
    done
    ip -n bvc-hl-switch link add br0 type bridge vlan_filtering 1 vlan_default_pvid 0
    ip -n bvc-hl-switch link set br0 up
    ip -n bvc-hl-switch link add p-router type veth peer name rt0 netns bvc-hl-router
    ip -n bvc-hl-switch link set p-router master br0
    ip -n bvc-hl-switch link set p-router up
    ip -n bvc-hl-router link set rt0 up
    for vid in 10 20 30 40; do
        ns switch bridge vlan add dev p-router vid "$vid"
        ip -n bvc-hl-router link add link rt0 name "rt0.$vid" type vlan id "$vid"
        ip -n bvc-hl-router addr add "10.77.$vid.1/24" dev "rt0.$vid"
        ip -n bvc-hl-router link set "rt0.$vid" up
    done
    while read -r role vid mac; do
        ip -n bvc-hl-switch link add "p-$role" type veth peer name eth0 netns "bvc-hl-$role"
        ip -n bvc-hl-switch link set "p-$role" master br0
        ns switch bridge vlan add dev "p-$role" vid "$vid" pvid untagged
        ip -n bvc-hl-switch link set "p-$role" up
        ip -n "bvc-hl-$role" link set eth0 address "$mac"
        ip -n "bvc-hl-$role" link set eth0 up
    done <<'PORTS'
admin 10 02:77:00:10:00:10
services 20 02:77:00:20:00:10
client 30 02:77:00:30:00:10
guest 40 02:77:00:40:00:10
PORTS
    ip -n bvc-hl-admin addr add 10.77.10.10/24 dev eth0
    ip -n bvc-hl-admin route add default via 10.77.10.1
    ip -n bvc-hl-services addr add 10.77.20.10/24 dev eth0
    ip -n bvc-hl-services route add default via 10.77.20.1
    ns router sysctl -qw net.ipv4.ip_forward=1
    ns router nft -f "$ROOT/config/router.nft"
    ns router dnsmasq --test --conf-file="$ROOT/config/dnsmasq.conf"
    nohup ip netns exec bvc-hl-router dnsmasq --keep-in-foreground --user=root --conf-file="$ROOT/config/dnsmasq.conf" \
        --dhcp-leasefile="$RUN/dhcp.leases" --pid-file="$RUN/dnsmasq.pid" \
        --log-facility="$RUN/dnsmasq.log" > "$RUN/dnsmasq.stderr" 2>&1 &
    nohup ip netns exec bvc-hl-services busybox httpd -f -p 10.77.20.10:8080 -h "$ROOT/services/files" > "$RUN/files.log" 2>&1 &
    nohup ip netns exec bvc-hl-admin busybox httpd -f -p 10.77.10.10:8081 -h "$ROOT/services/management" > "$RUN/management.log" 2>&1 &
    nohup ip netns exec bvc-hl-switch tcpdump -U -nn -i p-router -w "$RUN/validation.pcap" > "$RUN/tcpdump.log" 2>&1 &
    sleep 1
    for role in client guest; do
        ns "$role" env HLAB_LEASE_FILE="$RUN/lease-$role.txt" busybox udhcpc -f -q -n -t 5 -T 1 \
            -i eth0 -s "$ROOT/scripts/dhcp-hook.sh" > "$RUN/dhcp-$role.log" 2>&1
    done
    trap - ERR
    echo 'Lab ready: VLAN 10 management, 20 services, 30 clients, 40 guests.'
    echo 'Next: ./lab.sh verify, ./lab.sh show, ./lab.sh down'
}
show() {
    owned || { echo 'Lab is not running from this directory.' >&2; return 1; }
    echo '--- VLAN membership ---'; ns switch bridge vlan show
    echo '--- Router interfaces ---'; ip -br -n bvc-hl-router address
    echo '--- Router routes ---'; ip -n bvc-hl-router route
    echo '--- Firewall and counters ---'; ns router nft list ruleset
    echo '--- DHCP leases ---'; cat "$RUN/dhcp.leases"
}
need_root
case "${1:-help}" in
    up) up ;;
    down) down ;;
    verify) owned || { echo 'Run ./lab.sh up first.' >&2; exit 1; }; "$ROOT/scripts/verify.sh" ;;
    show) show ;;
    client-port-down|client-port-up)
        owned || exit 1
        state=down; [[ $1 == client-port-up ]] && state=up
        ip -n bvc-hl-switch link set p-client "$state"
        echo "Client access port is $state."
        ;;
    *) echo 'Usage: sudo ./lab.sh {up|verify|show|client-port-down|client-port-up|down}' ;;
esac
