"""End-to-end approval + mount verification."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rhns_adapter.supernova_mount import mount_into_supernova_os


def test_approval_override_chain() -> None:
    supernova_test_app = FastAPI()
    mount_into_supernova_os(supernova_test_app, db_path=":memory:")
    client = TestClient(supernova_test_app)

    # 1. Submit financial action -> ESCALATE_HUMAN
    eval_resp = client.post(
        "/v1/governance/evaluate",
        json={
            "provider": "anthropic",
            "trace_id": "trace_override_001",
            "intent": "Approve payout batch",
            "confidence": 0.95,
            "raw_payload": {
                "id": "msg_override_001",
                "model": "claude-sonnet-4-6",
                "content": [
                    {"type": "tool_use", "name": "stripe_create_payout", "input": {"amount": 2500}}
                ],
            },
        },
    )
    assert eval_resp.status_code == 200
    assert eval_resp.json()["decision"] == "ESCALATE_HUMAN"

    # 2. Operator approves -> appends linked ALLOW override & keeps chain valid
    app_resp = client.post(
        "/v1/governance/approve/msg_override_001",
        json={
            "reviewer_id": "garrett_carrol",
            "verdict": "APPROVE",
            "justification": "Verified batch against ledger and policy limits.",
        },
    )
    assert app_resp.status_code == 200
    assert app_resp.json()["decision"] == "ALLOW"
    assert app_resp.json()["prev_hash"] == eval_resp.json()["entry_hash"]

    ver_resp = client.get("/v1/governance/ledger/verify")
    assert ver_resp.status_code == 200
    assert ver_resp.json()["valid"] is True
    assert ver_resp.json()["entries_verified"] == 2
