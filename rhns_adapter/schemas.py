from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApprovalVerdict(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class LedgerRecordType(str, Enum):
    PROPOSAL_DECISION = "PROPOSAL_DECISION"
    APPROVAL_OVERRIDE = "APPROVAL_OVERRIDE"


class GateDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ESCALATE_HUMAN = "ESCALATE_HUMAN"


class ProviderType(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OTHER = "other"


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_id: str = Field(..., min_length=2, max_length=128)
    verdict: ApprovalVerdict
    justification: str = Field(..., min_length=4, max_length=1024)
    signature_hex: str = Field(default="", max_length=256)


class IngressProposalRequest(BaseModel):
    provider: str
    trace_id: str
    intent: str
    confidence: float = 1.0
    raw_payload: dict[str, Any]


class GovernanceReceipt(BaseModel):
    ledger_seq: int
    proposal_id: str
    trace_id: str
    provider: ProviderType
    model: str
    decision: GateDecision
    violated_rules: list[str] = []
    canonical_hash: str
    prev_hash: str
    entry_hash: str
    recorded_at_utc: str
