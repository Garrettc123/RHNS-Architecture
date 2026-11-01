"""RHNS API: reasoning requests are verified before any downstream execution.

The /reason endpoint validates a proposed plan and records the decision.
It does not execute actions.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from audit.ledger import AuditLedger
from symbolic.plan_verifier import verify_plan

app = FastAPI(
    title="RHNS AI",
    description="Recursive Hierarchical Network System — governed plan verification",
    version="1.1.0",
)

configured_origins = [
    item.strip() for item in os.getenv("RHNS_ALLOWED_ORIGINS", "").split(",")
    if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

ledger = AuditLedger()


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "system": "RHNS AI",
        "version": app.version,
        "status": "available",
        "capabilities": {
            "plan_verification": True,
            "deterministic_policy_gate": True,
            "hash_chained_in_memory_audit": True,
            "plan_execution": False,
            "persistent_audit_storage": False,
            "authentication_configured": bool(os.getenv("RHNS_API_TOKEN")),
        },
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "system": "RHNS AI"}


@app.get("/architecture")
def architecture() -> dict[str, Any]:
    return {
        "system": "RHNS AI",
        "implemented": [
            "typed plan validation",
            "deterministic allowlist and side-effect policy checks",
            "structured violation reports",
            "hash-chained in-memory decision audit",
        ],
        "not_implemented": [
            "LLM planning or generation",
            "persistent memory or graph retrieval",
            "plan execution",
            "persistent audit storage",
            "production rate limiting",
        ],
    }


def _authorize(request: Request) -> None:
    expected = os.getenv("RHNS_API_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Reasoning endpoint is disabled: RHNS_API_TOKEN is not configured.",
        )
    supplied = request.headers.get("authorization", "")
    if supplied != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token.")


@app.post("/reason")
async def reason(request: Request) -> dict[str, Any]:
    _authorize(request)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON.")

    result = verify_plan(payload)
    audit_entry = ledger.record(
        "symbolic.plan_verifier",
        "plan_verification",
        {
            "goal": payload.get("goal") if isinstance(payload, dict) else None,
            "status": result.status,
            "approved": result.approved,
            "violation_rule_ids": [item.rule_id for item in result.violations],
        },
    )
    return {
        "system": "RHNS AI",
        "verification": result.to_dict(),
        "plan": payload if isinstance(payload, dict) else None,
        "execution": {"performed": False, "reason": "Verification endpoint never executes actions."},
        "audit": {
            "index": audit_entry.index,
            "hash": audit_entry.hash,
            "chain_valid": ledger.verify_chain(),
            "storage": "in_memory",
        },
    }
