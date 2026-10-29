#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
export PATH="$ROOT/.runtime/tools:$PATH"
export KUBECONFIG="$ROOT/.runtime/kubeconfig"
CLUSTER=bvc-devops
K3S_IMAGE=rancher/k3s:v1.36.5-k3s1
k() { kubectl --kubeconfig "$KUBECONFIG" "$@"; }
owned() { [[ -f "$ROOT/.runtime/owner" ]] && [[ $(cat "$ROOT/.runtime/owner") == "kubernetes-devops-lab-v1:$ROOT" ]]; }
