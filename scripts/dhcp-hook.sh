#!/usr/bin/env bash
set -eu
[[ ${interface:-} == eth0 ]] || exit 1
[[ -n ${HLAB_LEASE_FILE:-} ]] || exit 1
case "${1:-}" in
    bound|renew)
        [[ ${subnet:-} == 255.255.255.0 ]] || exit 1
        ip address replace "$ip/24" dev eth0
        for gateway in ${router:-}; do ip route replace default via "$gateway" dev eth0; break; done
        printf 'ip=%s\nrouter=%s\ndns=%s\n' "$ip" "${router:-}" "${dns:-}" > "$HLAB_LEASE_FILE"
        ;;
    deconfig) : ;;
esac
