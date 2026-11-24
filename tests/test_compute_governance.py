"""Compute-governance security and accounting regression tests."""
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rhns_adapter.compute_governance import (
    ComputeGovernor, ComputePolicy, build_compute_governance_router,
)


def stack(tmp_path, monkeypatch, *, cap="0.25", max_hours="10"):
    policy = ComputePolicy(Decimal(max_hours), {"H100": Decimal("1"), "H200": Decimal("1.5")}, Decimal(cap))
    governor = ComputeGovernor(str(tmp_path / "meter.db"), policy)
    monkeypatch.setenv("RHNS_COMPUTE_API_TOKEN", "test-private-operator-token")
    app = FastAPI()
    app.include_router(build_compute_governance_router(governor))
    return governor, TestClient(app), {"Authorization": "Bearer test-private-operator-token"}


def reservation(job_id="a", category="customer_inference", gpu_hours="1"):
    return {"tenant_id":"org-a", "job_id":job_id,"agent_id":"worker-a",
            "category":category,"gpu_type":"H100","estimated_gpu_hours":gpu_hours,
            "workload_ref":"internal:scheduler/queue/1"}


def settlement(job_id="a", actual="1"):
    return {"tenant_id":"org-a","job_id":job_id,"actual_gpu_hours":actual,
            "cpu_seconds":"14","input_tokens":100,"output_tokens":40,
            "meter_evidence_ref":"internal:meter/event/42"}


def test_auth_is_fail_closed(tmp_path, monkeypatch):
    g,c,h = stack(tmp_path,monkeypatch)
    assert c.post("/v1/governance/compute/reserve",json=reservation()).status_code == 401
    monkeypatch.delenv("RHNS_COMPUTE_API_TOKEN")
    assert c.post("/v1/governance/compute/reserve",json=reservation(),headers=h).status_code == 503


def test_policy_is_fail_closed(tmp_path,monkeypatch):
    g = ComputeGovernor(str(tmp_path / "none.db"),None)
    monkeypatch.setenv("RHNS_COMPUTE_API_TOKEN","key")
    app = FastAPI()
    app.include_router(build_compute_governance_router(g))
    c = TestClient(app)
    r = c.post("/v1/governance/compute/reserve",json=reservation(),headers={"Authorization":"Bearer key"})
    assert r.status_code == 503


def test_reservation_limit_and_idempotence(tmp_path,monkeypatch):
    g,c,h = stack(tmp_path,monkeypatch)
    req = reservation("one","capabilities_rd","2")
    r = c.post("/v1/governance/compute/reserve",json=req,headers=h)
    assert r.status_code == 200 and r.json()["allowed"]
    replay = c.post("/v1/governance/compute/reserve",json=req,headers=h)
    assert replay.json()["idempotent"] is True
    assert replay.json()["allowed"] is False  # never redispatch a duplicate job
    assert replay.json()["receipt"]["entry_hash"] == r.json()["receipt"]["entry_hash"]
    denied = c.post("/v1/governance/compute/reserve",json=reservation("two","capabilities_rd","1"),headers=h)
    assert not denied.json()["allowed"]
    assert denied.json()["reason"] == "capabilities_budget_exceeded"
    conflicting = dict(req,estimated_gpu_hours="1")
    assert c.post("/v1/governance/compute/reserve",json=conflicting,headers=h).status_code == 409
    assert g.verify()["entries_verified"] == 2


def test_total_limit_and_tenant_isolation(tmp_path,monkeypatch):
    g,c,h = stack(tmp_path,monkeypatch,max_hours="2")
    assert c.post("/v1/governance/compute/reserve",json=reservation("one",gpu_hours="2"),headers=h).json()["allowed"]
    assert not c.post("/v1/governance/compute/reserve",json=reservation("two"),headers=h).json()["allowed"]
    other = dict(reservation("one"),tenant_id="org-b")
    assert c.post("/v1/governance/compute/reserve",json=other,headers=h).json()["allowed"]


def test_unknown_gpu_and_unclassified_fail_closed(tmp_path,monkeypatch):
    g,c,h=stack(tmp_path,monkeypatch)
    assert c.post("/v1/governance/compute/reserve",json=dict(reservation(),gpu_type="TPU"),headers=h).status_code == 409
    assert c.post("/v1/governance/compute/reserve",json=dict(reservation(),category="unknown"),headers=h).status_code == 422
    assert c.post("/v1/governance/compute/reserve",json=dict(reservation(),estimated_gpu_hours="NaN"),headers=h).status_code == 422


def test_settlement_overrun_truthful_and_idempotent(tmp_path,monkeypatch):
    g,c,h=stack(tmp_path,monkeypatch,max_hours="2")
    assert c.post("/v1/governance/compute/reserve",json=reservation(),headers=h).json()["allowed"]
    r = c.post("/v1/governance/compute/settle",json=settlement(actual="3"),headers=h)
    assert r.status_code == 200
    assert r.json()["over_reservation"] is True
    assert r.json()["budget_breach"] is True
    replay=c.post("/v1/governance/compute/settle",json=settlement(actual="3"),headers=h)
    assert replay.json()["idempotent"] is True
    assert c.post("/v1/governance/compute/settle",json=settlement(actual="4"),headers=h).status_code == 409
    day=datetime.now(timezone.utc).date().isoformat()
    report=c.get("/v1/governance/compute/report",params={"tenant_id":"org-a","day_utc":day},headers=h).json()
    assert report["gpu_equivalent_hours_reserved_or_settled"] == "3"
    assert report["independently_verified"] is False
    assert report["accounting_completeness"] == "UNVERIFIED"


def test_cancel_release_and_cannot_settle(tmp_path,monkeypatch):
    g,c,h=stack(tmp_path,monkeypatch,max_hours="1")
    c.post("/v1/governance/compute/reserve",json=reservation(),headers=h)
    cancelled=c.post("/v1/governance/compute/cancel",json={"tenant_id":"org-a","job_id":"a","reason":"scheduler canceled"},headers=h)
    assert cancelled.json()["state"] == "CANCELLED"
    assert c.post("/v1/governance/compute/settle",json=settlement(),headers=h).status_code == 409
    assert c.post("/v1/governance/compute/reserve",json=reservation("b"),headers=h).json()["allowed"]


def test_reconciliation_is_claim_not_audit(tmp_path,monkeypatch):
    g,c,h=stack(tmp_path,monkeypatch)
    day=datetime.now(timezone.utc).date().isoformat()
    req={"tenant_id":"org-a","day_utc":day,"source":"cloud-meter","external_metered_gpu_equivalent_hours":"5", "external_evidence_ref":"billing:run/18"}
    first=c.post("/v1/governance/compute/reconcile",json=req,headers=h)
    assert first.status_code == 200 and first.json()["independently_verified"] is False
    assert c.post("/v1/governance/compute/reconcile",json=req,headers=h).json()["idempotent"]
    assert c.post("/v1/governance/compute/reconcile",json=dict(req,external_metered_gpu_equivalent_hours="7"),headers=h).status_code == 409


def test_hash_integrity_recomputes_payload(tmp_path,monkeypatch):
    g,c,h=stack(tmp_path,monkeypatch)
    c.post("/v1/governance/compute/reserve",json=reservation(),headers=h)
    assert c.get("/v1/governance/compute/verify",headers=h).json()["valid"]
    with sqlite3.connect(g.db_path) as conn:
        conn.execute("UPDATE compute_events SET payload_json=? WHERE seq=1",(json.dumps({"malicious":"modification"}),))
    assert g.verify()["valid"] is False
    assert c.get("/v1/governance/compute/verify",headers=h).status_code == 409


def test_missing_reservation_does_not_create_settlement(tmp_path,monkeypatch):
    g,c,h=stack(tmp_path,monkeypatch)
    assert c.post("/v1/governance/compute/settle",json=settlement(),headers=h).status_code == 404
    assert g.verify()["entries_verified"] == 0


def test_h200_conversion_from_server_policy(tmp_path,monkeypatch):
    g,c,h=stack(tmp_path,monkeypatch,max_hours="2")
    req=dict(reservation(),gpu_type="H200")
    assert c.post("/v1/governance/compute/reserve",json=req,headers=h).json()["allowed"]
    req2=dict(reservation("b"),gpu_type="H200")
    assert not c.post("/v1/governance/compute/reserve",json=req2,headers=h).json()["allowed"]
