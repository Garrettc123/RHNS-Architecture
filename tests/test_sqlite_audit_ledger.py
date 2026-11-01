import json
import sqlite3

import pytest

from audit.ledger import SQLiteAuditLedger


def test_sqlite_ledger_survives_restart(tmp_path):
    database = tmp_path / "rhns-audit.sqlite3"
    first = SQLiteAuditLedger(str(database))
    first.record("policy", "approved", {"plan_id": "p-1", "approved": True})
    first.record("policy", "rejected", {"plan_id": "p-2", "approved": False})
    expected_hash = first.entries[-1].hash
    assert first.verify_chain()
    first.close()

    reopened = SQLiteAuditLedger(str(database))
    assert len(reopened.entries) == 2
    assert reopened.entries[-1].hash == expected_hash
    assert reopened.verify_chain()
    reopened.close()


def test_sqlite_ledger_blocks_update_and_delete(tmp_path):
    database = tmp_path / "append-only.sqlite3"
    ledger = SQLiteAuditLedger(str(database))
    ledger.record("audit", "event", {"value": 1})

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger._connection.execute(
            "UPDATE audit_entries SET event = 'tampered' WHERE entry_index = 0"
        )
    ledger._connection.rollback()

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger._connection.execute(
            "DELETE FROM audit_entries WHERE entry_index = 0"
        )
    ledger._connection.rollback()
    assert ledger.verify_chain()
    ledger.close()


def test_sqlite_ledger_rejects_non_json_payload(tmp_path):
    ledger = SQLiteAuditLedger(str(tmp_path / "payload.sqlite3"))
    with pytest.raises(ValueError, match="JSON-serializable"):
        ledger.record("audit", "bad_payload", {"not_json": object()})
    assert ledger.entries == []
    ledger.close()


def test_sqlite_ledger_exports_audit_records(tmp_path):
    ledger = SQLiteAuditLedger(str(tmp_path / "export.sqlite3"))
    ledger.record("api", "plan_check", {"approved": True})
    exported = json.loads(ledger.export_json())
    assert exported[0]["module"] == "api"
    assert exported[0]["event"] == "plan_check"
    ledger.close()
