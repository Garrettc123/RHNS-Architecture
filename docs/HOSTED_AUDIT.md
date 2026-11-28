# RHNS stateless-host audit persistence

An ephemeral Vercel filesystem cannot support the required hash-chain audit.
`main:app` now supports `RHNS_AUDIT_DATABASE_URL`, a privately managed
PostgreSQL DSN. When running on Vercel, SQLite is **not** accepted as durable,
even if `RHNS_REQUIRE_PERSISTENT_AUDIT=false`.

1. Review and separately authorize `infra/postgres_audit_schema.sql` against
   a dedicated PostgreSQL database. Never run the migration automatically at
   application import.
2. Use a least-privilege runtime database user with SELECT and INSERT on
   `rhns_audit_entries`, no schema ownership/UPDATE/DELETE.
3. Store `RHNS_AUDIT_DATABASE_URL` and `RHNS_API_TOKEN` in the protected
   server environment only. Do not copy other project secrets.
4. Verify chain continuity, valid signatures where applicable, and negative
   unauthorized requests after cold restart and separate function invocations.
5. Verify the DB connection uses TLS, the network/role is restricted,
   and the audit database has documented backup/restore controls.

The Postgres ledger serializes appends via an advisory transaction lock and
rechecks the hash chain during every plan validation. The trigger blocks
ordinary row mutation; it does **not** constitute immutable external
anchoring, WORM certification or a tamper-proof database administrator.
No hosted connection or migration was exercised in this change.
