from __future__ import annotations

from typing import Any

from .schemas import IngressProposalRequest


def normalize_proposal(req: IngressProposalRequest) -> dict[str, Any]:
    raw = req.raw_payload or {}
    proposal_id = raw.get("id") or req.trace_id
    return {
        "id": proposal_id,
        "proposal_id": proposal_id,
        "trace_id": req.trace_id,
        "provider": req.provider,
        "model": raw.get("model", "unknown"),
        "intent": req.intent,
        "confidence": req.confidence,
        "raw_payload": raw,
    }
