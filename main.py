"""RHNS API: reasoning requests are verified before any downstream execution.

The /reason endpoint validates a proposed plan and records the decision.
It does not execute actions.
"""
from __future__ import annotations

import hmac
import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from audit.ledger import AuditLedger, SQLiteAuditLedger
from symbolic.plan_verifier import verify_plan

MAX_REQUEST_BYTES = 64 * 1024
MIN_API_TOKEN_BYTES = 32

app = FastAPI(
    title="RHNS AI",
    description="Recursive Hierarchical Network System — governed plan verification",
    version="1.2.0",
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

audit_database_path = os.getenv("RHNS_AUDIT_DB_PATH", "").strip()
ledger = (
    SQLiteAuditLedger(audit_database_path)
    if audit_database_path
    else AuditLedger()
)


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "system": "RHNS AI",
        "version": app.version,
        "status": "available",
        "capabilities": {
            "plan_verification": True,
            "deterministic_policy_gate": True,
            "hash_chained_audit": True,
            "audit_storage": "sqlite" if isinstance(ledger, SQLiteAuditLedger) else "in_memory",
            "plan_execution": False,
            "persistent_audit_storage": isinstance(ledger, SQLiteAuditLedger) and ledger.persistent,
            "authentication_configured": len(os.getenv("RHNS_API_TOKEN", "").encode("utf-8")) >= MIN_API_TOKEN_BYTES,
        },
    }


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        chain_valid = ledger.verify_chain()
    except Exception:
        chain_valid = False
    persistent_required = os.getenv("RHNS_REQUIRE_PERSISTENT_AUDIT", "true").lower() not in {
        "0", "false", "no"
    }
    storage_ready = isinstance(ledger, SQLiteAuditLedger) and ledger.persistent
    if not chain_valid or (persistent_required and not storage_ready):
        raise HTTPException(status_code=503, detail="RHNS audit subsystem is not ready.")
    return {
        "status": "healthy",
        "system": "RHNS AI",
        "audit_chain_valid": chain_valid,
        "persistent_audit": storage_ready,
    }


@app.get("/architecture")
def architecture() -> dict[str, Any]:
    return {
        "system": "RHNS AI",
        "implemented": [
            "typed plan validation",
            "deterministic allowlist and side-effect policy checks",
            "structured violation reports",
            "hash-chained audit ledger",
            "SQLite persistent audit storage" if isinstance(ledger, SQLiteAuditLedger) and ledger.persistent
            else "in-memory audit storage",
        ],
        "not_implemented": [
            "LLM planning or generation",
            "persistent memory or graph retrieval",
            "plan execution",
            *([] if isinstance(ledger, SQLiteAuditLedger) and ledger.persistent else ["persistent audit storage"]),
            "production rate limiting",
        ],
    }


def _authorize(request: Request) -> None:
    expected = os.getenv("RHNS_API_TOKEN", "")
    if len(expected.encode("utf-8")) < MIN_API_TOKEN_BYTES:
        raise HTTPException(
            status_code=503,
            detail="Reasoning endpoint is disabled: RHNS_API_TOKEN must contain at least 32 UTF-8 bytes.",
        )
    supplied = request.headers.get("authorization", "")
    if not hmac.compare_digest(
        supplied.encode("utf-8"), f"Bearer {expected}".encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token.")


async def _read_bounded_json(request: Request) -> Any:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(status_code=415, detail="Content-Type must be application/json.")

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BYTES:
                raise HTTPException(status_code=413, detail="Request body exceeds the 64 KiB limit.")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header.")

    chunks = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_REQUEST_BYTES:
            raise HTTPException(status_code=413, detail="Request body exceeds the 64 KiB limit.")
        chunks.append(chunk)

    try:
        return json.loads(b"".join(chunks))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Request body must be valid JSON.")


@app.post("/reason")
async def reason(request: Request) -> dict[str, Any]:
    _authorize(request)
    persistent_required = os.getenv("RHNS_REQUIRE_PERSISTENT_AUDIT", "true").lower() not in {
        "0", "false", "no"
    }
    storage_ready = isinstance(ledger, SQLiteAuditLedger) and ledger.persistent
    if persistent_required and not storage_ready:
        raise HTTPException(
            status_code=503,
            detail="Reasoning endpoint disabled: persistent audit storage is required.",
        )
    payload = await _read_bounded_json(request)
    result = verify_plan(payload)

    # Do not issue a decision if the existing audit history is already invalid.
    try:
        if not ledger.verify_chain():
            raise HTTPException(status_code=503, detail="Audit integrity check failed; request denied.")
        audit_entry = ledger.record(
            "symbolic.plan_verifier",
            "plan_verification",
            {
                "status": result.status,
                "approved": result.approved,
                "violation_rule_ids": [item.rule_id for item in result.violations],
                "checked_actions": result.checked_actions,
            },
        )
        chain_valid = ledger.verify_chain()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Audit storage unavailable; request denied.")

    if not chain_valid:
        raise HTTPException(status_code=503, detail="Audit integrity check failed; request denied.")

    return {
        "system": "RHNS AI",
        "verification": result.to_dict(),
        "approval_scope": "policy_validation_only_not_execution_authorization",
        "plan_summary": {
            "received": True,
            "action_count": result.checked_actions,
        },
        "execution": {
            "performed": False,
            "reason": "Verification endpoint never executes actions.",
        },
        "audit": {
            "index": audit_entry.index,
            "hash": audit_entry.hash,
            "chain_valid": chain_valid,
            "storage": "sqlite" if isinstance(ledger, SQLiteAuditLedger) else "in_memory",
        },
    }
