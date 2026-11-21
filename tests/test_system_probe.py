"""Offline tests for the RHNS cross-service probe."""

import io
import json
from unittest.mock import patch

from tools.rhns_probe import CONTRACTS, _safe_base, probe, run


def test_probe_returns_missing_without_urls():
    result = run({})
    assert len(result["services"]) == 4
    assert all(item["status"] == "missing" for item in result["services"])
    assert result["end_to_end_integration_verified"] is False


def test_rejects_untrusted_origin_and_credentials():
    for value in (
        "http://internal.company",
        "https://user:secret@example.com",
        "https://example.com/path",
        "https://example.com?q=1",
        "file:///etc/passwd",
    ):
        try:
            _safe_base(value)
            assert False, value
        except ValueError:
            pass


def test_only_get_with_no_auth_headers():
    class Response(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

    def fake_urlopen(request, timeout):
        assert request.get_method() == "GET"
        assert request.get_header("Authorization") is None
        assert timeout == 4
        return Response(json.dumps({"status": "healthy", "mode": "analysis_only"}).encode())

    with patch("tools.rhns_probe.urlopen", side_effect=fake_urlopen):
        result = probe(CONTRACTS[0], {CONTRACTS[0].env: "https://example.com"})
    assert result["status"] == "compatible_health"


def test_reachable_but_wrong_contract_is_incompatible():
    class Response(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

    with patch("tools.rhns_probe.urlopen", return_value=Response(b'{"status":"operational"}')):
        result = probe(CONTRACTS[0], {CONTRACTS[0].env: "https://example.com"})
    assert result["status"] == "incompatible"


def test_explicit_https_origin_and_loopback_allowed():
    assert _safe_base("https://example.com") == "https://example.com"
    assert _safe_base("http://127.0.0.1:8090") == "http://127.0.0.1:8090"
