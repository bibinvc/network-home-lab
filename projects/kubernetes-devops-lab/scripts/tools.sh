#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
mkdir -p "$ROOT/.runtime/tools"
cd "$ROOT/.runtime/tools"
[[ $(uname -m) == x86_64 && $(uname -s) == Linux ]] || { echo 'This helper supports Linux amd64; see official installation links for other platforms.' >&2; exit 1; }
curl -fsSLo k3d https://github.com/k3d-io/k3d/releases/download/v5.9.0/k3d-linux-amd64
curl -fsSLo k3d-checksums.txt https://github.com/k3d-io/k3d/releases/download/v5.9.0/checksums.txt
expected=$(awk '$2 ~ /(^|\/)k3d-linux-amd64$/ {print $1}' k3d-checksums.txt)
[[ -n $expected ]] || { echo 'Missing official checksum.' >&2; exit 1; }
echo "$expected  k3d" | sha256sum -c -
curl -fsSLo kubectl https://dl.k8s.io/release/v1.36.5/bin/linux/amd64/kubectl
curl -fsSLo kubectl.sha256 https://dl.k8s.io/release/v1.36.5/bin/linux/amd64/kubectl.sha256
echo "$(cat kubectl.sha256)  kubectl" | sha256sum -c -
chmod +x k3d kubectl
echo "Add $ROOT/.runtime/tools to PATH for this shell. Docker Engine must already be available."
