"""Fail-closed mission completion gate; no external actions or trust issuance."""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, FrozenSet, Tuple

@dataclass(frozen=True)
class MissionContract:
    mission_id: str
    required: FrozenSet[str]
    allowed_sources: FrozenSet[str]
    max_cost: Decimal
    deadline: datetime

    def __post_init__(self):
        if not self.mission_id or not self.required or not self.allowed_sources:
            raise ValueError("Mission, requirements, and sources must be nonempty")
        if not isinstance(self.max_cost, Decimal) or not self.max_cost.is_finite() or self.max_cost < 0:
            raise ValueError("Cost must be a finite nonnegative Decimal")
        if self.deadline.tzinfo is None or self.deadline.utcoffset() is None:
            raise ValueError("Deadline must be timezone-aware")

@dataclass(frozen=True)
class Evidence:
    mission_id: str
    criterion: str
    source: str
    reference: str
    observed_at: datetime

@dataclass(frozen=True)
class Decision:
    complete: bool
    reasons: Tuple[str, ...]

def evaluate(contract: MissionContract, evidence: Tuple[Evidence, ...], *,
             spent: Decimal, now: datetime,
             verify: Callable[[Evidence], bool]) -> Decision:
    """verify must be supplied by a trusted adapter, not the proposing model.

    This gate checks submitted observations. It does not authenticate adapters,
    authorize writes, prevent duplicate actions, or enforce runtime budgets.
    """
    reasons = []
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Current time must be timezone-aware")
    if not isinstance(spent, Decimal) or not spent.is_finite() or spent < 0:
        raise ValueError("Spent must be a finite nonnegative Decimal")
    if spent > contract.max_cost:
        reasons.append("budget_exceeded")
    if now > contract.deadline:
        reasons.append("deadline_exceeded")
    satisfied = set()
    for item in evidence:
        if item.mission_id != contract.mission_id or item.criterion not in contract.required:
            continue
        if item.source not in contract.allowed_sources or not item.reference.strip():
            continue
        if item.observed_at.tzinfo is None or item.observed_at.utcoffset() is None:
            continue
        if item.observed_at > now:
            continue
        try:
            valid = verify(item) is True
        except Exception:
            valid = False
        if valid:
            satisfied.add(item.criterion)
    reasons.extend("missing:" + criterion for criterion in sorted(contract.required - satisfied))
    return Decision(not reasons, tuple(reasons))
