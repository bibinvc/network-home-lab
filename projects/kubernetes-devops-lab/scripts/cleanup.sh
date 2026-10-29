#!/usr/bin/env bash
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
owned || { echo 'No matching ownership record; refusing to delete a cluster.' >&2; exit 1; }
if [[ -f "$ROOT/.runtime/portforward.pid" ]]; then
    pf_pid=$(cat "$ROOT/.runtime/portforward.pid")
    if [[ -r /proc/$pf_pid/cmdline ]] && tr '\0' ' ' < "/proc/$pf_pid/cmdline" | grep -Fq 'port-forward'; then
        kill "$pf_pid" 2>/dev/null || true
    fi
fi
k3d cluster delete "$CLUSTER"
rm -f -- "$ROOT/.runtime/kubeconfig" "$ROOT/.runtime/owner" "$ROOT/.runtime/portforward.pid" "$ROOT/.runtime/database.secret"
echo 'Deleted only the named lab cluster and its local credential files.'
