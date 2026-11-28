-- RHNS audit database migration. Run only with explicit infrastructure approval.
-- Use separate migration credentials; runtime service should have SELECT/INSERT only.
CREATE TABLE IF NOT EXISTS rhns_audit_entries (
    entry_index BIGINT PRIMARY KEY,
    timestamp DOUBLE PRECISION NOT NULL,
    module TEXT NOT NULL,
    event TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    entry_hash TEXT UNIQUE NOT NULL
);

CREATE OR REPLACE FUNCTION rhns_reject_audit_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'RHNS audit entries are append-only';
END;
$$;

DROP TRIGGER IF EXISTS rhns_audit_no_mutation ON rhns_audit_entries;
CREATE TRIGGER rhns_audit_no_mutation
BEFORE UPDATE OR DELETE ON rhns_audit_entries
FOR EACH ROW EXECUTE FUNCTION rhns_reject_audit_mutation();
