# RHNS Cross-Repository Read-Only Health Contracts

Run from the RHNS-Architecture repository checkout:

```bash
python -m tools.rhns_probe
```

The probe requires explicit environment variables for any service you want
checked. Missing services are marked `missing`, not silently invented.

| Source repository | Environment variable | Health route | Exact expected fields |
| --- | --- | --- | --- |
| RHNS-Architecture | `RHNS_ARCHITECTURE_URL` | GET /health | status=healthy, mode=analysis_only |
| garcar-rhns-core | `RHNS_COGNITIVE_URL` | GET /cognitive/health | status=PROCESS_ALIVE, cognition_verified=false |
| rhns-agent-core | `RHNS_AGENT_RUNTIME_URL` | GET /ready | ready=true, external_actions_enabled=false |
| garcar-rhns-edge | `RHNS_EDGE_URL` | GET /health | status=ok, broken_at=null |

These contracts are based on the reviewed 2026-11-21 code versions:
architecture PR #4, cognitive PR #3, edge PR #2; the governed-agent
contract is from its existing main branch. The actual deployments may
still run older code. No URL is asserted to be currently serving it.

The probe makes GET requests only; it neither authenticates nor invokes
agents, payment endpoints, customer data, GitOps reconciliation, outbound
messaging, or deployments. HTTPS is required outside localhost. Results
do not establish end-to-end integration, tenant trust, training accuracy,
durability, or independently verified provider effects.

All service URLs must be supplied by the operator through environment
configuration. Do not paste credentials or private URLs into commits,
logs, chat or CI artifacts. **Do not point this script at untrusted endpoints.**

Integration release additionally needs a signed approval-dispatch contract,
durable receipt reconciliation, tenant-scoped identity, and controlled
negative-path tests between services.
