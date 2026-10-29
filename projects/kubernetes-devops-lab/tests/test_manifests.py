import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('render', Path(__file__).parents[1] / 'scripts/render.py')
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)


class ManifestChecks(unittest.TestCase):
    def setUp(self):
        self.items = render.resources('bvc-platform', 'bvc-ops:1.0.0', 'postgres:17-bookworm', 'owasp/modsecurity-crs:nginx')

    def test_deployments_have_probes_limits_and_no_token(self):
        for resource in self.items:
            if resource['kind'] not in ['Deployment', 'StatefulSet']:
                continue
            pod = resource['spec']['template']['spec']
            self.assertFalse(pod['automountServiceAccountToken'])
            self.assertTrue(pod['securityContext']['runAsNonRoot'])
            for container in pod['containers']:
                self.assertIn('readinessProbe', container)
                self.assertIn('limits', container['resources'])
                self.assertFalse(container['securityContext']['allowPrivilegeEscalation'])

    def test_no_embedded_secret_or_public_service(self):
        self.assertFalse(any(item['kind'] == 'Secret' for item in self.items))
        for item in self.items:
            if item['kind'] == 'Service':
                self.assertNotIn(item['spec'].get('type'), ['NodePort', 'LoadBalancer'])

    def test_schema_is_not_run_twice(self):
        config = next(item for item in self.items if item['kind'] == 'ConfigMap')
        self.assertIn('schema.txt', config['data'])
        self.assertNotIn('schema.sql', config['data'])

    def test_default_deny_and_rolling_strategy(self):
        policy = next(item for item in self.items if item['metadata']['name'] == 'default-deny')
        self.assertEqual(policy['spec']['policyTypes'], ['Ingress', 'Egress'])
        app = next(item for item in self.items if item['kind'] == 'Deployment' and item['metadata']['name'] == 'ops-app')
        self.assertEqual(app['spec']['replicas'], 2)
        self.assertEqual(app['spec']['strategy']['rollingUpdate']['maxUnavailable'], 0)


if __name__ == '__main__':
    unittest.main()
