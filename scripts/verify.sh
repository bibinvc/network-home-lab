#!/usr/bin/env bash
# Active tests use only the four private lab subnets.
set -uo pipefail
ROOT=${HLAB_ROOT:?Run through lab.sh}
RUN=${HLAB_RUN:?Run through lab.sh}
PASS=0; FAIL=0
exec > >(tee "$RUN/results.txt") 2>&1
ns() { ip netns exec "bvc-hl-$1" "${@:2}"; }
expect() {
    local label=$1 expected=$2 code
    shift 2
    printf '\nTEST: %s\n' "$label"
    "$@" > "$RUN/last-test.txt" 2>&1; code=$?
    cat "$RUN/last-test.txt"
    if { [[ $expected == pass ]] && [[ $code -eq 0 ]]; } || { [[ $expected == fail ]] && [[ $code -ne 0 ]]; }; then
        printf 'PASS: %s (exit=%s)\n' "$label" "$code"; ((PASS+=1))
    else
        printf 'FAIL: %s (exit=%s)\n' "$label" "$code"; ((FAIL+=1))
    fi
}
http() { ns "$1" curl --noproxy '*' -fsS --connect-timeout 1 --max-time 3 "$2"; }
dns_lookup() {
    ns "$1" busybox nslookup files.lab.test "$2" | tee "$RUN/dns-$1.txt" &&
        grep -F '10.77.20.10' "$RUN/dns-$1.txt"
}
echo 'Network Home Lab — actual connectivity checks'
date -u '+UTC: %Y-%m-%dT%H:%M:%SZ'
expect 'DHCP client address' pass grep -Fx ip=10.77.30.100 "$RUN/lease-client.txt"
expect 'DHCP guest address' pass grep -Fx ip=10.77.40.100 "$RUN/lease-guest.txt"
expect 'DHCP client gateway' pass grep -Fx router=10.77.30.1 "$RUN/lease-client.txt"
expect 'DHCP guest DNS option' pass grep -Fx dns=10.77.40.1 "$RUN/lease-guest.txt"
expect 'Client gateway reachable' pass ns client ping -c 1 -W 1 10.77.30.1
expect 'Client resolves private DNS' pass dns_lookup client 10.77.30.1
expect 'Guest resolves private DNS' pass dns_lookup guest 10.77.40.1
expect 'Client reaches file service' pass http client http://10.77.20.10:8080
expect 'Admin reaches file service' pass http admin http://10.77.20.10:8080
expect 'Admin reaches guest (stateful return)' pass ns admin ping -c 1 -W 1 10.77.40.100
expect 'Admin management service positive control' pass http admin http://10.77.10.10:8081
expect 'Guest cannot reach file service' fail http guest http://10.77.20.10:8080
expect 'Client cannot reach management service' fail http client http://10.77.10.10:8081
expect 'Guest cannot ping management' fail ns guest ping -c 1 -W 1 10.77.10.10
expect 'Services cannot initiate a client connection' fail ns services ping -c 1 -W 1 10.77.30.100
expect 'Router has no Internet route' fail ip -n bvc-hl-router route get 1.1.1.1
# Try a forbidden VLAN tag on the guest access port, then remove only this test interface.
if ip -n bvc-hl-guest link add link eth0 name probe30 type vlan id 30 &&
   ip -n bvc-hl-guest addr add 10.77.30.222/24 dev probe30 &&
   ip -n bvc-hl-guest link set probe30 up; then
    expect 'Guest tagged VLAN 30 cannot reach that VLAN gateway' fail ns guest ping -I probe30 -c 1 -W 1 10.77.30.1
    ip -n bvc-hl-guest link del probe30 || ((FAIL+=1))
else
    echo 'FAIL: could not configure the tagged-VLAN test'; ((FAIL+=1))
    ip -n bvc-hl-guest link del probe30 2>/dev/null || true
fi
echo; printf 'RESULT: %s passed, %s failed\n' "$PASS" "$FAIL"
[[ $FAIL -eq 0 ]]
