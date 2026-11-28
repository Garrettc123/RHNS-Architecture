"""Persistence gate contracts without hosted credentials or network."""
import main
from audit.ledger import AuditLedger, SQLiteAuditLedger


def test_vercel_rejects_ephemeral_sqlite(tmp_path, monkeypatch):
    db = SQLiteAuditLedger(str(tmp_path / "local.db"))
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("RHNS_REQUIRE_PERSISTENT_AUDIT", "false")
    monkeypatch.setattr(main, "ledger", db)
    assert main._storage_ready() is False
    assert main._persistence_required() is True
    db.close()


def test_default_durability_gate_rejects_in_memory(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("RHNS_REQUIRE_PERSISTENT_AUDIT", raising=False)
    monkeypatch.setattr(main, "ledger", AuditLedger())
    assert main._storage_ready() is False
    assert main._persistence_required() is True
