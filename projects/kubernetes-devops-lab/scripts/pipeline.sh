#!/usr/bin/env bash
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
cd "$ROOT"
umask 077
mkdir -p .runtime evidence
for tool in docker k3d kubectl python3 curl; do command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 1; }; done
[[ ! -f .runtime/owner ]] || { echo 'Existing lab state: inspect it or make clean.' >&2; exit 1; }
if k3d cluster list -o json | python3 -c 'import json,sys; sys.exit(0 if any(x["name"]=="bvc-devops" for x in json.load(sys.stdin)) else 1)'; then
    echo 'A bvc-devops cluster already exists; refusing to overwrite it.' >&2; exit 1
fi
printf '%s\n' "kubernetes-devops-lab-v1:$ROOT" > .runtime/owner
finish() {
    rc=$?
    trap - EXIT
    if [[ -f .runtime/kubeconfig ]]; then
        k get nodes -o wide > evidence/nodes.txt 2>&1 || true
        k -n bvc-platform get pods,deploy,sts,svc,pvc,networkpolicy -o wide > evidence/resources.txt 2>&1 || true
        k -n bvc-platform logs deployment/waf --tail=120 > evidence/waf-log.txt 2>&1 || true
    fi
    if [[ ${KEEP_LAB:-0} != 1 ]]; then bash scripts/cleanup.sh || true; fi
    exit "$rc"
}
trap finish EXIT
bash scripts/check.sh 2>&1 | tee evidence/unit-tests.txt
docker version --format '{{.Server.Version}}' > evidence/docker-version.txt
k3d version > evidence/k3d-version.txt
kubectl version --client -o json > evidence/kubectl-version.json
for name in python:3.12-slim-bookworm postgres:17-bookworm owasp/modsecurity-crs:nginx busybox:1.37.0; do docker pull "$name"; done
python3 - <<'PY'
import json,subprocess
names={'python':'python:3.12-slim-bookworm','postgres':'postgres:17-bookworm','waf':'owasp/modsecurity-crs:nginx','probe':'busybox:1.37.0'}
data={k:json.loads(subprocess.check_output(['docker','image','inspect',v]))[0]['RepoDigests'][0] for k,v in names.items()}
open('.runtime/images.json','w').write(json.dumps(data,indent=2)+'\n')
open('evidence/images.lock.json','w').write(json.dumps(data,indent=2)+'\n')
PY
BASE_IMAGE=$(python3 -c 'import json;print(json.load(open(".runtime/images.json"))["python"])')
for release in 1.0.0 2.0.0; do
    docker build --network=host --build-arg "BASE_IMAGE=$BASE_IMAGE" --build-arg "RELEASE=$release" -t "bvc-ops:$release" .
done
k3d cluster create "$CLUSTER" --servers 1 --agents 1 --image "$K3S_IMAGE" --api-port 127.0.0.1:16550 --no-lb \
    --subnet "${LAB_SUBNET:-10.92.10.0/24}" \
    --kubeconfig-update-default=false --kubeconfig-switch-context=false \
    --k3s-arg '--disable=traefik@server:*' --k3s-arg '--disable=servicelb@server:*' --k3s-arg '--disable=metrics-server@server:*' --wait --timeout 180s
k3d kubeconfig get "$CLUSTER" > "$KUBECONFIG"
chmod 600 "$KUBECONFIG"
k wait --for=condition=Ready nodes --all --timeout=180s
# Stream the image archive directly; works with a custom DOCKER_HOST socket too.
k3d image import bvc-ops:1.0.0 bvc-ops:2.0.0 postgres:17-bookworm owasp/modsecurity-crs:nginx busybox:1.37.0 --cluster "$CLUSTER" --mode direct
python3 - <<'PY'
import json,subprocess
images=json.load(open('.runtime/images.json'))
for ns,legacy in [('bvc-legacy',True),('bvc-platform',False)]:
    args=['python3','scripts/render.py','--namespace',ns,'--db-image',images['postgres'],'--waf-image',images['waf']]
    if legacy: args+=['--legacy']
    data=subprocess.check_output(args)
    open('.runtime/'+ns+'.json','wb').write(data)
PY
python3 - <<'PY'
import secrets
open('.runtime/database.secret','w').write('admin-password='+secrets.token_hex(24)+'\nreader-password='+secrets.token_hex(24)+'\n')
PY
for ns in bvc-legacy bvc-platform; do
    k create namespace "$ns"
    k -n "$ns" create secret generic database --from-env-file=.runtime/database.secret
    k apply -f ".runtime/$ns.json"
    k -n "$ns" rollout status statefulset/postgres --timeout=180s
    k -n "$ns" rollout status deployment/ops-app --timeout=180s
done
k -n bvc-platform rollout status deployment/waf --timeout=180s
k -n bvc-legacy exec -i postgres-0 -- psql -U postgres -d ops -v ON_ERROR_STOP=1 < k8s/seed.sql
k -n bvc-platform port-forward --address 127.0.0.1 service/waf 19880:8080 > .runtime/portforward.log 2>&1 &
echo "$!" > .runtime/portforward.pid
for attempt in $(seq 1 30); do curl -fsS http://127.0.0.1:19880/healthz >/dev/null && break; sleep 1; done
python3 scripts/verify_live.py 2>&1 | tee evidence/verification.txt
