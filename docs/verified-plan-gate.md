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


## LATS integration

LATS now accepts an optional deterministic candidate validator. When configured, each
candidate is checked before it is inserted into the search tree. Invalid JSON plans,
blocked operations, malformed plans, and any validator exception are rejected. Rejected
candidates are counted and are never passed to the critic. If every candidate is rejected,
the search returns the last safe parent/root state rather than promoting a rejected branch.

The RHNS agent connects this gate to `symbolic.plan_verifier.verify_plan`. The current
candidate generator is a deterministic demonstration stub that emits structured
`propose` plans; it is not an LLM or production planner. The LATS gate is only as
meaningful as the candidate schema and upstream plan-generation quality. It does not
prove that a proposal is factually correct or authorize execution.

New tests cover pre-critic rejection, all-candidates-rejected behavior, and compatibility
when no validator is configured.


## Persistent audit ledger

The API can use the standard-library SQLite ledger by setting
`RHNS_AUDIT_DB_PATH` to a writable database file on persistent storage. If the
variable is absent, the API deliberately retains the in-memory ledger and reports
`persistent_audit_storage: false` from `GET /`.

The SQLite ledger:
- uses WAL mode and FULL synchronous commits for file-backed databases;
- stores structured JSON payloads and SHA-256 hash-chain links;
- reloads prior entries after process restart;
- installs SQLite triggers that reject ordinary UPDATE and DELETE statements;
- exposes chain verification and JSON export.

Example environment configuration:

```sh
RHNS_AUDIT_DB_PATH=/var/lib/rhns/audit.sqlite3
```

The directory must exist or be creatable by the service account, writable, and backed
by persistent storage. A container's ephemeral filesystem is not sufficient.

This is not certified WORM storage. A privileged actor who can replace the database
file, alter its schema, or remove triggers can bypass database-level append-only
protections. Production hardening still requires restricted filesystem permissions,
encrypted backups, off-host replication or immutable archival, key management, and
independent monitoring. The hash chain detects content changes when verified; it
does not prevent a privileged attacker from rewriting the entire database and chain.


## API safety hardening

The verification endpoint now:
- compares bearer tokens with a constant-time comparison and remains disabled when no token is configured;
- accepts only `application/json` requests;
- limits request bodies to 64 KiB, including streamed bodies without a Content-Length header;
- does not echo submitted plans or goal text in its response;
- verifies the existing audit chain before appending a decision;
- returns HTTP 503 rather than a normal decision if audit verification or persistence fails;
- keeps execution disabled.

Audit payloads are now serialized as canonical finite JSON before hashing. The SQLite reader rejects payload rows that are not stored in canonical form. This detects certain privileged database edits that bypass ordinary row triggers.

These controls reduce risk but do not make the API production-secure by themselves. Still required before exposure to untrusted networks: TLS termination, secret-manager-backed token rotation, rate limiting, request monitoring, restricted database filesystem permissions, encrypted off-host backups, immutable external checkpoints, and independent security review. The API's health and architecture endpoints remain unauthenticated and should not be treated as private operational consoles.
