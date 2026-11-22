"""Executable API contract tests: no network/model/secret prerequisites."""

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_health_is_diagnostic_not_production_claim():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["mode"] == "analysis_only"


def test_run_uses_local_bounded_search():
    r = client.post("/run", json={"goal": "fire causes smoke"})
    assert r.status_code == 200
    body = r.json()
    assert body["execution_mode"] == "analysis_only"
    assert body["verifier_status"] == "parsed_unverified"
    assert body["subgoal_stack"] == ["causes(fire, smoke)"]
    assert body["reward"] == 0.0
    assert body["tree_size"] == 2


def test_run_with_no_known_pattern_is_unverified():
    r = client.post("/run", json={"goal": "inspect current sales"})
    assert r.status_code == 200
    assert r.json()["verifier_status"] == "no_predicates"
    assert r.json()["tree_size"] == 1


def test_no_unsupported_schema():
    r = client.post("/run", json={"goal": "fire causes smoke", "schema": "autonomous_execution"})
    assert r.status_code == 422


def test_empty_and_long_goals_rejected():
    assert client.post("/run", json={"goal": ""}).status_code == 422
    assert client.post("/run", json={"goal": "a" * 2001}).status_code == 422


def test_batch_hard_limit():
    assert client.post("/run/batch", json=[]).status_code == 422
    assert client.post("/run/batch", json=["a"] * 21).status_code == 422
    result = client.post("/run/batch", json=["fire causes smoke", "cat is a animal"])
    assert result.status_code == 200
    assert result.json()["count"] == 2


def test_legacy_reason_does_not_pretend_to_execute():
    result = client.post("/reason", params={"goal": "fire causes smoke", "context": "notes"})
    assert result.status_code == 200
    assert result.json()["context_used"] is False
    assert result.json()["status"] == "completed"


def test_cors_is_not_wildcard_by_default():
    result = client.options(
        "/run",
        headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST"},
    )
    assert result.headers.get("access-control-allow-origin") != "*"
