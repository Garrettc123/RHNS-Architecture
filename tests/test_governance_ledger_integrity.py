"""Regression tests for the pre-existing RHNS approval ledger verifier."""
import sqlite3

from rhns_adapter.ledger import GovernanceLedger
from rhns_adapter.schemas import GateDecision


def test_governance_ledger_hashes_recalculated(tmp_path):
    ledger = GovernanceLedger(str(tmp_path / "governance.sqlite"))
    ledger.append(
        {"id": "p1", "trace_id": "t1", "provider": "other", "model": "baseline"},
        GateDecision.ALLOW,
        [],
    )
    assert ledger.verify_chain()["valid"]
    with sqlite3.connect(ledger.db_path) as conn:
        conn.execute(
            "UPDATE governance_ledger SET canonical_payload_json=? WHERE seq=1",
            ('{"record_type":"PROPOSAL_DECISION","decision":"ALLOW"}',),
        )
    result = ledger.verify_chain()
    assert result["valid"] is False
    assert result["failed_seq"] == 1


def test_proposal_metadata_modification_detected(tmp_path):
    ledger = GovernanceLedger(str(tmp_path / "governance.sqlite"))
    ledger.append(
        {"id": "p2", "trace_id": "t2", "provider": "other", "model": "baseline"},
        GateDecision.ALLOW,
        [],
    )
    with sqlite3.connect(ledger.db_path) as conn:
        conn.execute("UPDATE governance_ledger SET model='changed' WHERE seq=1")
    assert ledger.verify_chain()["valid"] is False


def test_approval_override_chain_still_valid(tmp_path):
    ledger = GovernanceLedger(str(tmp_path / "governance.sqlite"))
    ledger.append(
        {"id": "p3", "trace_id": "t3", "provider": "other", "model": "baseline"},
        GateDecision.ESCALATE_HUMAN,
        ["financial_action"],
    )
    ledger.record_approval_override(
        proposal_id="p3",
        reviewer_id="reviewer",
        verdict="APPROVE",
        justification="Approved following operator review",
        signature_hex="",
    )
    result = ledger.verify_chain()
    assert result["valid"] is True
    assert result["entries_verified"] == 2
