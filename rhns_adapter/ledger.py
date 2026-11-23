from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .schemas import (
    GateDecision,
    GovernanceReceipt,
    LedgerRecordType,
    ProviderType,
)

GENESIS_HASH = "0" * 64


def canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class GovernanceLedger:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS governance_ledger (
                    seq INTEGER PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    violated_rules_json TEXT NOT NULL,
                    canonical_payload_json TEXT NOT NULL,
                    canonical_hash TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    entry_hash TEXT NOT NULL,
                    recorded_at_utc TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def _compute_entry_hash(
        self,
        *,
        seq: int,
        proposal_id: str,
        trace_id: str,
        decision: str,
        canonical_hash: str,
        prev_hash: str,
        recorded_at_utc: str,
    ) -> str:
        payload = f"{seq}|{proposal_id}|{trace_id}|{decision}|{canonical_hash}|{prev_hash}|{recorded_at_utc}"
        return sha256_hex(payload.encode("utf-8"))

    def get_latest_proposal_record(self, proposal_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT * FROM governance_ledger
                WHERE proposal_id = ? AND record_type = 'PROPOSAL_DECISION'
                ORDER BY seq DESC LIMIT 1;
                """,
                (proposal_id,),
            ).fetchone()

    def record_approval_override(
        self,
        *,
        proposal_id: str,
        reviewer_id: str,
        verdict: str,
        justification: str,
        signature_hex: str,
    ) -> GovernanceReceipt:
        prior = self.get_latest_proposal_record(proposal_id)
        if prior is None:
            raise KeyError(f"Unknown proposal_id: {proposal_id}")

        if str(prior["decision"]) != GateDecision.ESCALATE_HUMAN.value:
            raise ValueError(
                f"Proposal {proposal_id} is in state '{prior['decision']}', not ESCALATE_HUMAN"
            )

        override_payload = {
            "record_type": LedgerRecordType.APPROVAL_OVERRIDE.value,
            "target_proposal_id": proposal_id,
            "target_entry_hash": str(prior["entry_hash"]),
            "reviewer_id": reviewer_id,
            "verdict": verdict,
            "justification": justification,
            "signature_hex": signature_hex,
        }
        canonical_bytes = canonical_json_bytes(override_payload)
        canonical_hash = sha256_hex(canonical_bytes)
        recorded_at = datetime.now(timezone.utc).isoformat()
        resolved_decision = (
            GateDecision.ALLOW.value if verdict == "APPROVE" else GateDecision.DENY.value
        )

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            row = conn.execute(
                "SELECT seq, entry_hash FROM governance_ledger ORDER BY seq DESC LIMIT 1;"
            ).fetchone()
            next_seq = 1 if row is None else int(row["seq"]) + 1
            prev_hash = GENESIS_HASH if row is None else str(row["entry_hash"])

            entry_hash = self._compute_entry_hash(
                seq=next_seq,
                proposal_id=proposal_id,
                trace_id=str(prior["trace_id"]),
                decision=f"{LedgerRecordType.APPROVAL_OVERRIDE.value}:{resolved_decision}",
                canonical_hash=canonical_hash,
                prev_hash=prev_hash,
                recorded_at_utc=recorded_at,
            )

            conn.execute(
                """
                INSERT INTO governance_ledger (
                    seq, proposal_id, trace_id, provider, model, decision,
                    record_type, violated_rules_json, canonical_payload_json,
                    canonical_hash, prev_hash, entry_hash, recorded_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    next_seq,
                    proposal_id,
                    str(prior["trace_id"]),
                    str(prior["provider"]),
                    str(prior["model"]),
                    resolved_decision,
                    LedgerRecordType.APPROVAL_OVERRIDE.value,
                    "[]",
                    canonical_bytes.decode("utf-8"),
                    canonical_hash,
                    prev_hash,
                    entry_hash,
                    recorded_at,
                ),
            )
            conn.execute("COMMIT;")

            return GovernanceReceipt(
                ledger_seq=next_seq,
                proposal_id=proposal_id,
                trace_id=str(prior["trace_id"]),
                provider=ProviderType(str(prior["provider"])),
                model=str(prior["model"]),
                decision=GateDecision(resolved_decision),
                violated_rules=[f"OVERRIDE_BY:{reviewer_id}:{verdict}"],
                canonical_hash=canonical_hash,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
                recorded_at_utc=recorded_at,
            )
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    def append(self, canonical: dict[str, Any], decision: GateDecision, violations: list[str]) -> GovernanceReceipt:
        # Minimal append for PROPOSAL_DECISION so the approval path can be exercised.
        proposal_id = canonical.get("id") or canonical.get("proposal_id") or "unknown"
        trace_id = canonical.get("trace_id", "trace")
        provider = canonical.get("provider", "other")
        model = canonical.get("model", "unknown")

        payload = {
            "record_type": LedgerRecordType.PROPOSAL_DECISION.value,
            "proposal_id": proposal_id,
            "decision": decision.value,
            "violations": violations,
        }
        canonical_bytes = canonical_json_bytes(payload)
        canonical_hash = sha256_hex(canonical_bytes)
        recorded_at = datetime.now(timezone.utc).isoformat()

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            row = conn.execute(
                "SELECT seq, entry_hash FROM governance_ledger ORDER BY seq DESC LIMIT 1;"
            ).fetchone()
            next_seq = 1 if row is None else int(row["seq"]) + 1
            prev_hash = GENESIS_HASH if row is None else str(row["entry_hash"])

            entry_hash = self._compute_entry_hash(
                seq=next_seq,
                proposal_id=proposal_id,
                trace_id=trace_id,
                decision=decision.value,
                canonical_hash=canonical_hash,
                prev_hash=prev_hash,
                recorded_at_utc=recorded_at,
            )

            conn.execute(
                """
                INSERT INTO governance_ledger (
                    seq, proposal_id, trace_id, provider, model, decision,
                    record_type, violated_rules_json, canonical_payload_json,
                    canonical_hash, prev_hash, entry_hash, recorded_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    next_seq,
                    proposal_id,
                    trace_id,
                    provider,
                    model,
                    decision.value,
                    LedgerRecordType.PROPOSAL_DECISION.value,
                    json.dumps(violations),
                    canonical_bytes.decode("utf-8"),
                    canonical_hash,
                    prev_hash,
                    entry_hash,
                    recorded_at,
                ),
            )
            conn.execute("COMMIT;")

            return GovernanceReceipt(
                ledger_seq=next_seq,
                proposal_id=proposal_id,
                trace_id=trace_id,
                provider=ProviderType(provider) if provider in ProviderType._value2member_map_ else ProviderType.OTHER,
                model=model,
                decision=decision,
                violated_rules=violations,
                canonical_hash=canonical_hash,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
                recorded_at_utc=recorded_at,
            )
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    def verify_chain(self) -> dict[str, object]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT seq, entry_hash, prev_hash FROM governance_ledger ORDER BY seq ASC;"
            ).fetchall()
        if not rows:
            return {"valid": True, "entries_verified": 0}
        prev = GENESIS_HASH
        for row in rows:
            if str(row["prev_hash"]) != prev:
                return {"valid": False, "entries_verified": int(row["seq"]) - 1, "reason": "hash mismatch"}
            prev = str(row["entry_hash"])
        return {"valid": True, "entries_verified": len(rows)}
