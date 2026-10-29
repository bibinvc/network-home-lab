"""Generate native Kubernetes JSON resources. No secret values are included."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def resources(namespace, app_image, db_image, waf_image, include_waf=True):
    def obj(kind, name, **extra):
        return {'apiVersion': 'v1', 'kind': kind, 'metadata': {'name': name, 'namespace': namespace}, **extra}

    result = [{'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': namespace}}]
    result += [obj('ServiceAccount', 'workload', automountServiceAccountToken=False),
               obj('ServiceAccount', 'observer', automountServiceAccountToken=False)]
    result.append({'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'Role',
                   'metadata': {'name': 'observer', 'namespace': namespace}, 'rules': [
                       {'apiGroups': [''], 'resources': ['pods', 'services'], 'verbs': ['get', 'list', 'watch']},
                       {'apiGroups': ['apps'], 'resources': ['deployments'], 'verbs': ['get', 'list', 'watch']} ]})
    result.append({'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'RoleBinding',
                   'metadata': {'name': 'observer', 'namespace': namespace},
                   'roleRef': {'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'Role', 'name': 'observer'},
                   'subjects': [{'kind': 'ServiceAccount', 'name': 'observer', 'namespace': namespace}]})
    init = '#!/bin/sh\nset -eu\npsql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -v ON_ERROR_STOP=1 -v reader_password="$READER_PASSWORD" -f /docker-entrypoint-initdb.d/schema.txt\n'
    result.append(obj('ConfigMap', 'db-init', data={'10-init.sh': init, 'schema.txt': (ROOT / 'k8s/schema.sql').read_text()}))
    base_security = {'runAsNonRoot': True, 'seccompProfile': {'type': 'RuntimeDefault'}}
    container_security = {'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}}
    result.append({'apiVersion': 'apps/v1', 'kind': 'StatefulSet', 'metadata': {'name': 'postgres', 'namespace': namespace},
                   'spec': {'serviceName': 'postgres', 'replicas': 1, 'selector': {'matchLabels': {'app': 'postgres'}},
                            'template': {'metadata': {'labels': {'app': 'postgres'}}, 'spec': {
                                'serviceAccountName': 'workload', 'automountServiceAccountToken': False,
                                'securityContext': {**base_security, 'runAsUser': 999, 'runAsGroup': 999, 'fsGroup': 999},
                                'containers': [{'name': 'postgres', 'image': db_image, 'imagePullPolicy': 'IfNotPresent',
                                    'securityContext': container_security,
                                    'env': [{'name': 'POSTGRES_DB', 'value': 'ops'}, {'name': 'POSTGRES_USER', 'value': 'postgres'},
                                            {'name': 'PGDATA', 'value': '/var/lib/postgresql/data/pgdata'},
                                            {'name': 'POSTGRES_PASSWORD', 'valueFrom': {'secretKeyRef': {'name': 'database', 'key': 'admin-password'}}},
                                            {'name': 'READER_PASSWORD', 'valueFrom': {'secretKeyRef': {'name': 'database', 'key': 'reader-password'}}}],
                                    'ports': [{'containerPort': 5432}],
                                    'readinessProbe': {'exec': {'command': ['pg_isready', '-U', 'postgres', '-d', 'ops']}, 'initialDelaySeconds': 4, 'periodSeconds': 3},
                                    'resources': {'requests': {'cpu': '50m', 'memory': '128Mi'}, 'limits': {'cpu': '500m', 'memory': '512Mi'}},
                                    'volumeMounts': [{'name': 'data', 'mountPath': '/var/lib/postgresql/data'},
                                                     {'name': 'init', 'mountPath': '/docker-entrypoint-initdb.d', 'readOnly': True}]}],
                                'volumes': [{'name': 'init', 'configMap': {'name': 'db-init', 'defaultMode': 0o444}}]}},
                            'volumeClaimTemplates': [{'metadata': {'name': 'data'}, 'spec': {
                                'accessModes': ['ReadWriteOnce'], 'resources': {'requests': {'storage': '256Mi'}}}}]}})
    result.append(obj('Service', 'postgres', spec={'selector': {'app': 'postgres'}, 'ports': [{'port': 5432, 'targetPort': 5432}]}))
    app = {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': {'name': 'ops-app', 'namespace': namespace},
           'spec': {'replicas': 2 if include_waf else 1, 'revisionHistoryLimit': 5,
                    'strategy': {'type': 'RollingUpdate', 'rollingUpdate': {'maxUnavailable': 0, 'maxSurge': 1}},
                    'selector': {'matchLabels': {'app': 'ops-app'}}, 'template': {'metadata': {'labels': {'app': 'ops-app'}}, 'spec': {
                        'serviceAccountName': 'workload', 'automountServiceAccountToken': False,
                        'securityContext': {**base_security, 'runAsUser': 10001, 'runAsGroup': 10001},
                        'topologySpreadConstraints': [{'maxSkew': 1, 'topologyKey': 'kubernetes.io/hostname',
                            'whenUnsatisfiable': 'ScheduleAnyway', 'labelSelector': {'matchLabels': {'app': 'ops-app'}}}],
                        'containers': [{'name': 'app', 'image': app_image, 'imagePullPolicy': 'IfNotPresent',
                            'securityContext': {**container_security, 'readOnlyRootFilesystem': True},
                            'env': [{'name': 'PGHOST', 'value': 'postgres'}, {'name': 'PGPASSWORD',
                                     'valueFrom': {'secretKeyRef': {'name': 'database', 'key': 'reader-password'}}}],
                            'ports': [{'containerPort': 8080}],
                            'startupProbe': {'httpGet': {'path': '/healthz', 'port': 8080}, 'failureThreshold': 30, 'periodSeconds': 2},
                            'readinessProbe': {'httpGet': {'path': '/readyz', 'port': 8080}, 'periodSeconds': 2},
                            'livenessProbe': {'httpGet': {'path': '/healthz', 'port': 8080}, 'periodSeconds': 5},
                            'resources': {'requests': {'cpu': '50m', 'memory': '48Mi'}, 'limits': {'cpu': '300m', 'memory': '128Mi'}}}]}}}}
    result.append(app)
    result.append(obj('Service', 'ops-app', spec={'selector': {'app': 'ops-app'}, 'ports': [{'port': 8080, 'targetPort': 8080}]}))
    if include_waf:
        result.append({'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': {'name': 'waf', 'namespace': namespace},
                       'spec': {'replicas': 1, 'selector': {'matchLabels': {'app': 'waf'}},
                                'template': {'metadata': {'labels': {'app': 'waf'}}, 'spec': {
                                    'serviceAccountName': 'workload', 'automountServiceAccountToken': False,
                                    'securityContext': {**base_security, 'runAsUser': 101, 'runAsGroup': 101},
                                    'containers': [{'name': 'waf', 'image': waf_image, 'imagePullPolicy': 'IfNotPresent',
                                        'securityContext': container_security,
                                        'env': [{'name': 'BACKEND', 'value': 'http://ops-app:8080'},
                                                {'name': 'PORT', 'value': '8080'}, {'name': 'SSL_PORT', 'value': '8443'},
                                                {'name': 'MODSEC_RULE_ENGINE', 'value': 'On'},
                                                {'name': 'BLOCKING_PARANOIA', 'value': '1'},
                                                {'name': 'ANOMALY_INBOUND', 'value': '5'},
                                                {'name': 'MODSEC_AUDIT_LOG', 'value': '/dev/stdout'}],
                                        'ports': [{'containerPort': 8080}],
                                        'readinessProbe': {'httpGet': {'path': '/healthz', 'port': 8080}, 'periodSeconds': 3, 'initialDelaySeconds': 8},
                                        'resources': {'requests': {'cpu': '100m', 'memory': '128Mi'}, 'limits': {'cpu': '500m', 'memory': '512Mi'}}}]}}}})
        result.append(obj('Service', 'waf', spec={'selector': {'app': 'waf'}, 'ports': [{'port': 8080, 'targetPort': 8080}]}))
        result.append({'apiVersion': 'policy/v1', 'kind': 'PodDisruptionBudget', 'metadata': {'name': 'app-budget', 'namespace': namespace},
                       'spec': {'minAvailable': 1, 'selector': {'matchLabels': {'app': 'ops-app'}}}})
    # K3s includes a NetworkPolicy controller; the live test verifies enforcement.
    def policy(name, selector, **rules):
        return {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
                'metadata': {'name': name, 'namespace': namespace}, 'spec': {'podSelector': selector, **rules}}
    result.append(policy('default-deny', {}, policyTypes=['Ingress', 'Egress']))
    result.append(policy('allow-dns', {}, policyTypes=['Egress'], egress=[{
        'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
                'podSelector': {'matchLabels': {'k8s-app': 'kube-dns'}}}],
        'ports': [{'protocol': 'UDP', 'port': 53}, {'protocol': 'TCP', 'port': 53}]}]))
    result.append(policy('app-to-database', {'matchLabels': {'app': 'ops-app'}}, policyTypes=['Egress'],
                         egress=[{'to': [{'podSelector': {'matchLabels': {'app': 'postgres'}}}], 'ports': [{'port': 5432}]}]))
    result.append(policy('database-from-app', {'matchLabels': {'app': 'postgres'}}, policyTypes=['Ingress'],
                         ingress=[{'from': [{'podSelector': {'matchLabels': {'app': 'ops-app'}}}], 'ports': [{'port': 5432}]}]))
    if include_waf:
        result += [policy('app-from-waf', {'matchLabels': {'app': 'ops-app'}}, policyTypes=['Ingress'],
                          ingress=[{'from': [{'podSelector': {'matchLabels': {'app': 'waf'}}}], 'ports': [{'port': 8080}]}]),
                   policy('waf-to-app', {'matchLabels': {'app': 'waf'}}, policyTypes=['Egress'],
                          egress=[{'to': [{'podSelector': {'matchLabels': {'app': 'ops-app'}}}], 'ports': [{'port': 8080}]}]),
                   policy('waf-from-clients', {'matchLabels': {'app': 'waf'}}, policyTypes=['Ingress'],
                          ingress=[{'from': [{'podSelector': {}}], 'ports': [{'port': 8080}]}])]
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--namespace', default='bvc-platform')
    parser.add_argument('--app-image', default='bvc-ops:1.0.0')
    parser.add_argument('--db-image', default='postgres:17-bookworm')
    parser.add_argument('--waf-image', default='owasp/modsecurity-crs:nginx')
    parser.add_argument('--legacy', action='store_true')
    args = parser.parse_args()
    print(json.dumps({'apiVersion': 'v1', 'kind': 'List', 'items': resources(
        args.namespace, args.app_image, args.db_image, args.waf_image, not args.legacy)}, indent=2))
