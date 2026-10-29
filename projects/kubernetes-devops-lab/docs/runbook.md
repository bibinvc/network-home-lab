# Operator runbook

1. Run `bash scripts/check.sh` before creating a cluster.
2. Confirm Docker points to the intended local engine and no `bvc-devops` cluster already exists.
3. Run `KEEP_LAB=1 bash scripts/pipeline.sh` if interactive inspection is required. Otherwise let the default cleanup run.
4. Inspect the generated kubeconfig only locally; do not commit or copy it into evidence.
5. Use `kubectl -n bvc-platform get pods` and `kubectl -n bvc-platform logs deployment/ops-app` for app readiness problems. Query `postgres-0` logs if the database has not initialised.
6. For WAF errors, compare a normal `/healthz` request with the synthetic attack fixtures and inspect the WAF log. Do not turn the rule engine off to make a failed security test pass.
7. For denied traffic, check the NetworkPolicy selectors and DNS positive control. A connection refusal is not accepted as evidence of a policy drop; the test requires a timeout against a separately healthy target.
8. For a bad app revision, use `kubectl -n bvc-platform rollout history deployment/ops-app`, then `rollout undo`; check readiness and the version endpoint afterwards.
9. Compare ordered data before retiring the legacy namespace. A successful import command alone is not enough.
10. End with `bash scripts/cleanup.sh`. Never remove an unrelated cluster, Docker network or volume to free space for this lab.

CPU/memory limits are lab settings, not a sizing recommendation. HTTP sampling during the short rollout is an observation, not a load test or availability SLA.
