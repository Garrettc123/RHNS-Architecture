# RHNS audit production bootstrap

The separate private Railway deployment project
`garcar-rhns-runtime-production` has three deliberately different roles:

- **Postgres:** Railway-generated admin connection and dedicated DB volume
- **rhns-audit-bootstrap:** one-shot SQL migration; has admin DSN and a generated
  runtime-role password; must be removed/disabled after a successful run
- **rhns-governance-api:** runs `main:app` with a URL using the separate
  `rhns_audit_runtime` role, not Postgres admin credentials

The migration code `scripts/migrate_rhns_audit.py` applies
`infra/postgres_audit_schema.sql`, verifies its append-only trigger, and
grants the runtime role only database CONNECT, schema USAGE, and table
SELECT/INSERT. It serializes migrations with a PostgreSQL advisory lock and
does not write fake audit entries.

Never place `RHNS_AUDIT_MIGRATION_URL` on the web service.
The short-lived migration service may reference `Postgres.DATABASE_URL`;
the runtime service must use the lesser privileged connection URL, stored
as an encrypted variable. All values must remain within server secret stores.
Audit trigger protection is not full DBA-proof WORM immutability.

Acceptance sequence: deploy DB, run migration to completion, verify the
trigger and grants, deploy the API, GET /health returns 200, deny missing
token, submit and verify one explicitly approved policy-only plan, restart,
confirm durable hash-chain continuity, then disable the migration service.
Only activate routing to production after that evidence passes.

Staging resources without accepting their environment patch does NOT create
a running database or worker. Paid Railway capacity must be authorized
before accepting the staged changes.
