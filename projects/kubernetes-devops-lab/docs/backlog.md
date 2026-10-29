# Project work board

This is a personal, iterative work list. It does not establish experience in an Agile team.

| Item | Acceptance evidence |
| --- | --- |
| Build a minimal read-only workload | Unit checks; no write API; read-only DB role |
| Describe and deploy the target environment | Kubernetes resources accepted by the API; nodes and workloads ready |
| Migrate synthetic application data | Empty target before import; ordered equality after restore |
| Restrict application traffic | Normal WAF request succeeds; direct app/DB probe is blocked |
| Add application-layer filtering | SQLi/XSS fixtures denied; ordinary request still succeeds |
| Exercise release/recovery operations | v2 rollout, forced readiness failure, rollback and pod/PVC recovery |
| Record a repeatable CI path | Workflow and the same pipeline script; inspect the actual Actions run |
| Document limits and cleanup | Runbook, scope statements, cluster ownership guard |
