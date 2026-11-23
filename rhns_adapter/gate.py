from __future__ import annotations

from typing import Any

from .schemas import GateDecision


class GatePolicy:
    def __init__(self) -> None:
        pass


def evaluate_proposal(canonical: dict[str, Any], policy: GatePolicy) -> tuple[GateDecision, list[str]]:
    # Minimal policy: escalate financial actions, otherwise allow.
    raw = canonical.get("raw_payload") or {}
    content = raw.get("content") or []
    for item in content:
        if isinstance(item, dict) and item.get("name") == "stripe_create_payout":
            return GateDecision.ESCALATE_HUMAN, ["financial_action"]
    return GateDecision.ALLOW, []
