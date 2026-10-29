"""Integration checks against the dedicated local cluster; only synthetic data."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:19880'
NS = 'bvc-platform'
checks = []


def command(*args, namespace=None, data=None, expected=0, timeout=180):
    cmd = ['kubectl', '--kubeconfig', str(ROOT / '.runtime/kubeconfig')]
    if namespace:
        cmd += ['-n', namespace]
    run = subprocess.run(cmd + list(args), input=data, capture_output=True, timeout=timeout)
    if expected is not None and run.returncode != expected:
        raise RuntimeError('kubectl action failed: ' + ' '.join(args[:3]) + '\n' + run.stderr.decode(errors='replace'))
    return run


def kjson(*args, namespace=NS):
    return json.loads(command(*args, '-o', 'json', namespace=namespace).stdout)


def http(path, expected=200, method='GET'):
    try:
        response = urllib.request.urlopen(urllib.request.Request(URL + path, method=method), timeout=8)
    except urllib.error.HTTPError as error:
        response = error
    body = response.read()
    assert response.status == expected, (path, response.status, body[:100])
    return body


def check(name, test):
    result = test()
    item = {'name': name, 'status': 'passed'}
    if result is not None:
        item['observation'] = result
    checks.append(item)
    print('PASS ' + name, flush=True)


def dataset(namespace):
    query = 'COPY (SELECT hostname,purpose,status FROM inventory ORDER BY hostname) TO STDOUT WITH CSV'
    return command('exec', 'postgres-0', '--', 'psql', '-U', 'postgres', '-d', 'ops', '-Atc', query, namespace=namespace).stdout


def wait_http_records(count, seconds=45):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            result = json.loads(http('/records'))
            if result['count'] == count:
                return result
        except Exception:
            pass
        time.sleep(1)
    raise AssertionError('Expected inventory count did not recover')


def assert_equal(actual, expected):
    assert actual == expected, (actual, expected)


def deploy_probe():
    pod = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': 'untrusted-probe', 'namespace': NS, 'labels': {'app': 'untrusted-probe'}},
           'spec': {'restartPolicy': 'Never', 'serviceAccountName': 'workload', 'automountServiceAccountToken': False,
                    'securityContext': {'runAsNonRoot': True, 'runAsUser': 10001, 'seccompProfile': {'type': 'RuntimeDefault'}},
                    'containers': [{'name': 'probe', 'image': 'bvc-ops:1.0.0', 'imagePullPolicy': 'IfNotPresent',
                                    'command': ['python', '-c', 'import time;time.sleep(900)'],
                                    'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}},
                                    'resources': {'requests': {'cpu': '10m', 'memory': '24Mi'}, 'limits': {'cpu': '100m', 'memory': '64Mi'}}}]}}
    command('apply', '-f', '-', data=json.dumps(pod).encode())
    command('wait', '--for=condition=Ready', 'pod/untrusted-probe', '--timeout=90s', namespace=NS)


def probe(script, expected=0):
    return command('exec', 'untrusted-probe', '--', 'python', '-c', script, namespace=NS, expected=expected, timeout=20).stdout.decode().strip()


def connection_blocked(host, port):
    script = "import socket,sys\ntry:\n s=socket.create_connection((%r,%d),3);s.close();print('CONNECTED');sys.exit(0)\nexcept TimeoutError:\n print('TIMEOUT_BLOCKED');sys.exit(2)\n" % (host, port)
    assert_equal(probe(script, 2), 'TIMEOUT_BLOCKED')


def rollout():
    failures, observations = [], []
    stop = threading.Event()
    def poll():
        while not stop.is_set():
            try:
                observations.append(json.loads(http('/version'))['release'])
            except Exception as error:
                failures.append(type(error).__name__)
            time.sleep(0.2)
    thread = threading.Thread(target=poll, daemon=True)
    thread.start()
    try:
        command('set', 'image', 'deployment/ops-app', 'app=bvc-ops:2.0.0', namespace=NS)
        command('rollout', 'status', 'deployment/ops-app', '--timeout=120s', namespace=NS)
    finally:
        stop.set()
        thread.join()
    assert not failures, failures
    assert observations, 'No availability samples'
    assert_equal(json.loads(http('/version'))['release'], '2.0.0')
    return {'http_samples': len(observations), 'sample_failures': len(failures), 'release_after': '2.0.0'}


def bad_release_and_rollback():
    command('set', 'env', 'deployment/ops-app', 'APP_FORCE_UNREADY=1', namespace=NS)
    result = command('rollout', 'status', 'deployment/ops-app', '--timeout=18s', namespace=NS, expected=None, timeout=30)
    assert result.returncode != 0, 'Readiness failure was not observed'
    assert_equal(json.loads(http('/version'))['release'], '2.0.0')
    command('rollout', 'undo', 'deployment/ops-app', namespace=NS)
    command('rollout', 'status', 'deployment/ops-app', '--timeout=120s', namespace=NS)
    deployment = kjson('get', 'deployment', 'ops-app')
    assert_equal(deployment['status']['availableReplicas'], 2)
    assert all(item['name'] != 'APP_FORCE_UNREADY' for item in deployment['spec']['template']['spec']['containers'][0]['env'])
    return 'Unready revision failed to complete; previous healthy specification restored.'


def recover_app_pod():
    pod = kjson('get', 'pods', '-l', 'app=ops-app')['items'][0]
    old_uid = pod['metadata']['uid']
    command('delete', 'pod', pod['metadata']['name'], namespace=NS)
    command('rollout', 'status', 'deployment/ops-app', '--timeout=120s', namespace=NS)
    assert all(p['metadata']['uid'] != old_uid for p in kjson('get', 'pods', '-l', 'app=ops-app')['items'])
    wait_http_records(3)


def recover_database():
    before = dataset(NS)
    command('delete', 'pod', 'postgres-0', namespace=NS)
    end = time.monotonic() + 120
    while time.monotonic() < end:
        result = command('wait', '--for=condition=Ready', 'pod/postgres-0', '--timeout=5s', namespace=NS, expected=None, timeout=10)
        if result.returncode == 0:
            break
        time.sleep(1)
    else:
        raise AssertionError('Database pod did not recover')
    assert_equal(dataset(NS), before)
    wait_http_records(3)
    return 'Same synthetic records retained on the persistent volume.'


def main():
    check('two Kubernetes nodes are Ready', lambda: assert_equal(sum(any(c['type']=='Ready' and c['status']=='True' for c in n['status']['conditions']) for n in kjson('get', 'nodes', namespace=None)['items']), 2))
    check('server-side deployment validation', lambda: command('apply', '--dry-run=server', '-f', str(ROOT / '.runtime/bvc-platform.json')) and None)
    check('two application replicas are available', lambda: assert_equal(kjson('get', 'deployment', 'ops-app')['status']['availableReplicas'], 2))
    check('WAF forwards a normal health request', lambda: http('/healthz') and None)
    check('application rejects mutations', lambda: http('/records', 405, 'POST') and None)
    check('legacy inventory has three synthetic records', lambda: assert_equal(len(dataset('bvc-legacy').splitlines()), 3))
    check('target inventory is empty before migration', lambda: assert_equal(dataset(NS), b''))
    dump = command('exec', 'postgres-0', '--', 'pg_dump', '-U', 'postgres', '-d', 'ops', '--data-only', '--no-owner', '--no-privileges', '--table=inventory', namespace='bvc-legacy').stdout
    (ROOT / '.runtime/migration.sql').write_bytes(dump)
    command('exec', '-i', 'postgres-0', '--', 'psql', '-U', 'postgres', '-d', 'ops', '-v', 'ON_ERROR_STOP=1', namespace=NS, data=dump)
    check('logical database migration preserves all records', lambda: assert_equal(dataset('bvc-legacy'), dataset(NS)))
    check('target application reads migrated data', lambda: wait_http_records(3) and None)
    denied = command('exec', 'postgres-0', '--', 'sh', '-c', 'PGPASSWORD="$READER_PASSWORD" psql -h 127.0.0.1 -U app_reader -d ops -v ON_ERROR_STOP=1 -c "INSERT INTO inventory VALUES (\'forbidden\',\'test\',\'healthy\')"', namespace=NS, expected=None)
    check('application database role cannot insert records', lambda: assert_equal(denied.returncode != 0 and b'permission denied' in denied.stderr.lower(), True))
    check('SQL injection test string is blocked by WAF', lambda: http('/?q=' + urllib.parse.quote("1' OR 1=1 --"), 403) and None)
    check('XSS test string is blocked by WAF', lambda: http('/?q=' + urllib.parse.quote('<script>alert(1)</script>'), 403) and None)
    check('normal request still works after WAF probes', lambda: http('/') and None)
    deploy_probe()
    time.sleep(3)
    check('untrusted pod can resolve cluster DNS', lambda: probe("import socket;print(socket.gethostbyname('ops-app'))") and None)
    check('untrusted pod may reach WAF', lambda: assert_equal(probe("import urllib.request;print(urllib.request.urlopen('http://waf:8080/healthz',timeout=5).status)"), '200'))
    check('untrusted pod cannot bypass WAF to reach app', lambda: connection_blocked('ops-app', 8080))
    check('untrusted pod cannot connect to database', lambda: connection_blocked('postgres', 5432))
    check('app runs as non-root UID 10001', lambda: assert_equal(command('exec', 'deployment/ops-app', '--', 'python', '-c', 'import os;print(os.getuid())', namespace=NS).stdout.strip(), b'10001'))
    read_only = command('exec', 'deployment/ops-app', '--', 'python', '-c', "open('/app/write-test','w').write('test')", namespace=NS, expected=None)
    check('application root filesystem is read-only', lambda: assert_equal(read_only.returncode != 0 and b'Read-only file system' in read_only.stderr, True))
    no_token = command('exec', 'deployment/ops-app', '--', 'python', '-c', "from pathlib import Path;print(Path('/var/run/secrets/kubernetes.io/serviceaccount/token').exists())", namespace=NS)
    check('workload has no mounted service-account token', lambda: assert_equal(no_token.stdout.strip(), b'False'))
    identity = 'system:serviceaccount:bvc-platform:observer'
    check('observer RBAC permits pod inspection', lambda: assert_equal(command('auth', 'can-i', 'get', 'pods', '--as', identity, namespace=NS).stdout.strip(), b'yes'))
    check('observer RBAC denies reading secrets', lambda: assert_equal(command('auth', 'can-i', 'get', 'secrets', '--as', identity, namespace=NS, expected=1).stdout.strip(), b'no'))
    check('rolling deployment updates release without sampled HTTP errors', rollout)
    check('failed readiness revision can be rolled back', bad_release_and_rollback)
    check('deleted app pod is replaced and service recovers', recover_app_pod)
    check('database pod replacement preserves migrated data', recover_database)
    check('metrics endpoint reports the three records', lambda: assert_equal('ops_inventory_records 3' in http('/metrics').decode(), True))
    logs = command('logs', 'deployment/ops-app', '--tail=40', namespace=NS).stdout.decode()
    check('application produces structured request logs', lambda: assert_equal('http_request' in logs, True))
    command('delete', 'namespace', 'bvc-legacy', '--wait=true')
    check('target remains usable after legacy namespace retirement', lambda: wait_http_records(3) and None)
    result = {'verified_at_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'local two-node k3d/K3s lab, synthetic data only',
              'live_checks_passed': len(checks), 'live_checks_failed': 0, 'checks': checks,
              'migration': {'records': 3, 'data_sha256': hashlib.sha256(dataset(NS)).hexdigest(), 'dump_sha256': hashlib.sha256(dump).hexdigest()},
              'limits': ['single local host', 'one database instance', 'one WAF replica', 'no production SLA, VM migration or cloud deployment verified']}
    (ROOT / 'evidence/verification.json').write_text(json.dumps(result, indent=2) + '\n')
    (ROOT / 'evidence/dashboard.html').write_bytes(http('/'))
    (ROOT / 'evidence/app-logs.txt').write_text(logs)
    print('SUMMARY: %d live checks passed, 0 failed' % len(checks), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        (ROOT / 'evidence/verification.json').write_text(json.dumps({'verified_at_utc': datetime.now(timezone.utc).isoformat(),
            'live_checks_passed': len(checks), 'live_checks_failed': 1, 'error': str(error), 'checks': checks}, indent=2) + '\n')
        raise
