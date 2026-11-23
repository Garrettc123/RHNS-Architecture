# RHNS Universal AI Governance Adapter

Live package on `main`. Human-approval resolution + garcar-supernova-os mount.

## Endpoints (mounted at `/v1/governance`)

- `POST /v1/governance/evaluate` — submit proposal, returns GovernanceReceipt (may be ESCALATE_HUMAN)
- `POST /v1/governance/approve/{proposal_id}` — resolve ESCALATE_HUMAN into hash-chained APPROVAL_OVERRIDE (ALLOW or DENY)
- `GET /v1/governance/ledger/verify` — verify SHA-256 chain

## Mount into garcar-supernova-os

```python
from fastapi import FastAPI
from rhns_adapter.supernova_mount import mount_into_supernova_os

app = FastAPI(title="Garcar Sovereign One")
mount_into_supernova_os(app, db_path="rhns_governance_ledger.db")
# runs on port 8090 by default; port 8000 is prohibited
```

## Quick verify

```bash
pytest rhns_adapter/test_approval_mount.py -q
```

## Rules

- Only ESCALATE_HUMAN proposals can be overridden.
- Override is linked to the original proposal_id and prior entry_hash.
- Cash is not cash until Stripe paid=true and last4 != 4242.
- Baseline proof_hash: 2398aa32e69202313aeccadacb6638f32eb7e9df5697ad93f080a4fcc05a3060

SKU: AI-AUDIT-299 https://buy.stripe.com/14A5kD3IF9Sqdrd05l43S2l
