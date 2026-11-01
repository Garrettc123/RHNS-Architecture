import asyncio

import pytest
from fastapi import HTTPException, Request

import main
from audit.ledger import AuditLedger


def make_request(headers=None, body=b""):
    sent = False
    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    encoded_headers = [
        (key.lower().encode(), value.encode())
        for key, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/reason",
        "raw_path": b"/reason",
        "query_string": b"",
        "headers": encoded_headers,
        "server": ("testserver", 80),
        "client": ("testclient", 12345),
    }
    return Request(scope, receive)


def test_reason_endpoint_disabled_without_token(monkeypatch):
    monkeypatch.delenv("RHNS_API_TOKEN", raising=False)
    with pytest.raises(HTTPException) as error:
        main._authorize(make_request())
    assert error.value.status_code == 503


def test_reason_endpoint_uses_bearer_authentication(monkeypatch):
    monkeypatch.setenv("RHNS_API_TOKEN", "a-long-test-token")
    main._authorize(make_request({"authorization": "Bearer a-long-test-token"}))
    with pytest.raises(HTTPException) as error:
        main._authorize(make_request({"authorization": "Bearer wrong"}))
    assert error.value.status_code == 401


def test_reason_rejects_wrong_content_type():
    request = make_request({"content-type": "text/plain"}, b"{}")
    with pytest.raises(HTTPException) as error:
        asyncio.run(main._read_bounded_json(request))
    assert error.value.status_code == 415


def test_reason_rejects_oversized_declared_body():
    request = make_request({
        "content-type": "application/json",
        "content-length": str(main.MAX_REQUEST_BYTES + 1),
    })
    with pytest.raises(HTTPException) as error:
        asyncio.run(main._read_bounded_json(request))
    assert error.value.status_code == 413


def test_reason_rejects_oversized_streamed_body():
    request = make_request(
        {"content-type": "application/json"},
        b" " * (main.MAX_REQUEST_BYTES + 1),
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(main._read_bounded_json(request))
    assert error.value.status_code == 413


def test_reason_does_not_echo_plan_and_records_audit(monkeypatch):
    monkeypatch.setenv("RHNS_API_TOKEN", "a-long-test-token")
    monkeypatch.setattr(main, "ledger", AuditLedger())
    plan = {
        "goal": "Review confidential customer record",
        "actions": [{
            "action_id": "a1",
            "operation": "read",
            "target": "customer-record-123",
        }],
    }
    request = make_request(
        {
            "authorization": "Bearer a-long-test-token",
            "content-type": "application/json",
        },
        __import__("json").dumps(plan).encode(),
    )

    response = asyncio.run(main.reason(request))

    assert response["verification"]["approved"] is True
    assert "plan" not in response
    assert response["plan_summary"]["action_count"] == 1
    assert response["audit"]["chain_valid"] is True
    assert response["execution"]["performed"] is False


def test_reason_fails_closed_when_audit_chain_is_invalid(monkeypatch):
    monkeypatch.setenv("RHNS_API_TOKEN", "a-long-test-token")

    class BrokenLedger:
        def verify_chain(self):
            return False

        def record(self, *_args, **_kwargs):
            raise AssertionError("must not append to an invalid audit chain")

    monkeypatch.setattr(main, "ledger", BrokenLedger())
    request = make_request(
        {
            "authorization": "Bearer a-long-test-token",
            "content-type": "application/json",
        },
        b'{"goal":"safe","actions":[{"action_id":"a1","operation":"read","target":"x"}]}',
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(main.reason(request))
    assert error.value.status_code == 503
