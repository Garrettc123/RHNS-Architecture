"""Read-only RHNS cross-service health contract probe.

Requires explicitly provided RHNS_*_URL environment variables. Does not
discover internal endpoints or call any agent, payment, or mutation routes.
Passing health contracts does not prove a deployed integrated workflow.
"""

import json
import os
import socket
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ServiceContract:
    name: str
    env: str
    path: str


CONTRACTS = (
    ServiceContract("architecture", "RHNS_ARCHITECTURE_URL", "/health"),
    ServiceContract("cognitive", "RHNS_COGNITIVE_URL", "/cognitive/health"),
    ServiceContract("governed_agent", "RHNS_AGENT_RUNTIME_URL", "/ready"),
    ServiceContract("edge", "RHNS_EDGE_URL", "/health"),
)


def _safe_base(value: str) -> str:
    """Allow HTTPS or explicit local HTTP; reject credentials and query data."""
    parsed = urlsplit(value.strip())
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or parsed.scheme not in ("https", "http")
        or (
            parsed.scheme == "http"
            and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        )
    ):
        raise ValueError("expected an HTTPS origin or an explicit localhost origin")
    return value.rstrip("/")


def _meets_contract(service: str, payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    if service == "architecture":
        return payload.get("status") == "healthy" and payload.get("mode") == "analysis_only"
    if service == "cognitive":
        return payload.get("status") == "PROCESS_ALIVE" and payload.get("cognition_verified") is False
    if service == "governed_agent":
        return payload.get("ready") is True and payload.get("external_actions_enabled") is False
    if service == "edge":
        return payload.get("status") == "ok" and payload.get("broken_at") is None
    return False


def probe(contract: ServiceContract, environment: dict[str, str]) -> dict[str, object]:
    value = environment.get(contract.env, "").strip()
    if not value:
        return {"service": contract.name, "status": "missing", "reason": "origin_not_provided"}

    try:
        target = _safe_base(value) + contract.path
    except ValueError:
        return {"service": contract.name, "status": "blocked", "reason": "invalid_origin"}
    # Explicitly send no provider credentials. Only GET health/ready contracts.
    request = Request(target, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=4) as response:
            if response.status != 200:
                return {"service": contract.name, "status": "unavailable", "reason": "non_200"}
            raw = response.read(8193)
            if len(raw) > 8192:
                return {"service": contract.name, "status": "incompatible", "reason": "response_too_large"}
            payload = json.loads(raw.decode("utf-8"))
        return {
            "service": contract.name,
            "status": "compatible_health" if _meets_contract(contract.name, payload) else "incompatible",
        }
    except (HTTPError, URLError, TimeoutError, socket.timeout, UnicodeError, ValueError, json.JSONDecodeError):
        return {"service": contract.name, "status": "unavailable", "reason": "request_or_contract_failure"}


def run(environment: dict[str, str] | None = None) -> dict[str, object]:
    current = environment if environment is not None else dict(os.environ)
    results = [probe(contract, current) for contract in CONTRACTS]
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only_health_contracts",
        "services": results,
        "health_contracts_all_compatible": all(
            item["status"] == "compatible_health" for item in results
        ),
        "end_to_end_integration_verified": False,
        "reason": "health contracts do not establish authenticated dispatch, receipt reconciliation or provider execution",
    }


if __name__ == "__main__":
    outcome = run()
    print(json.dumps(outcome, sort_keys=True, indent=2))
    if not outcome["health_contracts_all_compatible"]:
        sys.exit(2)
