# RHNS Compute Governance — operator runbook

**Status:** Internal compute-budget API. This is not an independently audited Verified Compute Allocation Disclosure (VCAD), production deployment, hardware telemetry collector, or evidence of external compute use.

## Integration and policy

The existing mount_into_supernova_os adds /v1/governance/compute/* to the same durable SQLite database path as the governance ledger. Use persistent storage, HTTPS and a trusted service network.

Required settings:

- RHNS_COMPUTE_API_TOKEN — privileged Bearer service token from an approved secret manager. Do not commit it or expose it to browsers, customers or agents.
- RHNS_COMPUTE_POLICY_JSON — JSON policy with daily_gpu_equivalent_hour_budget (positive decimal), gpu_equivalence (nonempty server-controlled hardware/conversion map) and optional capabilities_share_cap (decimal between 0 and 1). Capability-development jobs are denied if the cap is absent. No particular cap or GPU conversion ratios are assumed.
- RHNS_LEDGER_DB — persistent SQLite location.

The quota is a fraction of the operator-configured daily capacity, not the share of observed jobs. Budgets are per tenant, per UTC day. CPU seconds and token counts are auxiliary evidence, not automatically converted to GPU time.

A **trusted scheduler** calls reserve before starting work and must dispatch only if allowed=true. A separate trusted metering worker settles actual consumption afterward. The API itself never dispatches jobs.

## Authenticated API

| Method | Route | Function |
| --- | --- | --- |
| POST | /v1/governance/compute/reserve | Atomic budget authorization; records allowed and denied decisions |
| POST | /v1/governance/compute/settle | Actual consumption with evidence pointer; reports overruns |
| POST | /v1/governance/compute/cancel | Cancel and release an unstarted reservation |
| POST | /v1/governance/compute/reconcile | Record an attributed external-meter **claim**, not auditor verification |
| GET | /v1/governance/compute/report | Per-tenant/day allocation, pending jobs and metering claims |
| GET | /v1/governance/compute/pending | List overdue unsettled reservations, without auto-releasing budget |
| GET | /v1/governance/compute/verify | Recompute all event hashes and chain links |

Every endpoint requires an operator-only Authorization Bearer token. Each state-changing operation verifies the receipt chain and materialized usage within the same locked SQLite transaction *before* it authorizes or records a change; reporting uses a consistent verification snapshot. Missing token or missing compute policy fails closed for reservations. Unknown GPU types and unclassified workloads are refused.

Reservation fields: tenant_id, job_id, agent_id, category, gpu_type, estimated_gpu_hours, workload_ref. Supported categories: capabilities_rd, customer_inference_trained_on, customer_inference, safeguard_classifiers and non_capabilities_rd. The first two count against capabilities limits.

Settlement fields: tenant_id, job_id, actual_gpu_hours, meter_evidence_ref; optional cpu_seconds, input_tokens and output_tokens. Actual usage exceeding the reservation is logged and flagged rather than hidden. Identical retries are idempotent, conflicting retries return HTTP 409, and cancelled jobs cannot be settled.

This is a privileged operator API with a shared service secret for all tenants, not customer-specific authorization. Only trusted metering and classification components may submit records.

## Verification limits

- Hash-chain validation detects many record edits but does not prove that all compute was recorded. A database administrator could rehash or truncate the ledger; anchor chain tips in a separately controlled immutable store.
- Reconciliation entries are attributed claims and are not automatically checked against cloud invoices, GPU inventories, scheduler logs, external R&D or third-party inference.
- Reports explicitly return independently_verified=false and accounting_completeness=UNVERIFIED.
- GPU conversion factors, workload classification and idle capacity require separate independent measurement. Do not assert VCAD audit compliance based on this component alone.
- Compute authorization does not authorize payouts, messages, charges, or deployment. Existing human approval gates remain intact.

Use GET /v1/governance/compute/pending?tenant_id=<tenant>&older_than_seconds=86400 for an authenticated list of unfinished jobs. This is an investigation queue, not proof of non-use: reservations remain charged to their original UTC day until legitimately settled or cancelled. Pending results include agent ID, category, reservation hash, age and reserved GPU-equivalent hours. Do not cancel an already dispatched or possibly running job to reclaim budget without verified termination and measurement.

Before regulated production usage, add independent telemetry reconciliation, data retention and backups, external cryptographic anchoring, privileged-token rotation, automated alert delivery, enforced scheduler start/stop acknowledgments, and per-tenant authenticated access where necessary. Full-ledger verification is currently O(number of events + jobs) on every write; use a verified checkpoint/indexed architecture for higher throughput.

## Tests

Run from repository root:

    python -m pytest -q tests/test_compute_governance.py tests/test_governance_ledger_integrity.py rhns_adapter/test_approval_mount.py

Tests use isolated SQLite storage and deterministic fixture quantities, not real compute-use claims.
