# RHNS Verified Plan Gate

## Scope

This change adds a deterministic, fail-closed validator for proposed plans and wires it to
`POST /reason`. The endpoint validates and audits; it does not execute actions.

## Request

```json
{
  "goal": "Review a lead record",
  "actions": [
    {
      "action_id": "a1",
      "operation": "read",
      "target": "lead:123"
    }
  ]
}
```

Send `Authorization: Bearer <RHNS_API_TOKEN>`. The endpoint returns HTTP 503 when
`RHNS_API_TOKEN` is not configured and HTTP 401 for a missing or incorrect token.
The token must be supplied through the deployment secret manager; do not commit it.

## Policy

Allowed operations: `read`, `calculate`, `classify`, `validate`, `draft`, `propose`.

Blocked operations include sending messages, charging, transferring funds, purchasing,
deploying, deleting, publishing, and arbitrary external writes. Plans are rejected when
they contain an unapproved operation, duplicate action IDs, missing required fields,
external effects, human-approval requirements, or more than 25 actions.

## Limitations

- This is deterministic policy validation, not formal proof of the real-world truth of a plan.
- It does not execute actions or connect to an LLM.
- The existing audit ledger is in-memory; records do not survive process restart.
- Authentication is bearer-token based. Production deployment still requires TLS, secret
  management, rate limiting, monitoring, and a persistent audit backend.
- The allowlist is intentionally narrow. Extend it only with explicit policy and tests.
