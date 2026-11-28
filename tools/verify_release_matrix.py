"""Offline verification of the RHNS/MARS 11-repository release manifest.

This checks only documented release-gate consistency. It does not query
provider infrastructure or certify code, deployments, or production readiness.
"""
from __future__ import annotations
import json
from pathlib import Path

def validate() -> None:
    path = Path(__file__).resolve().parents[1] / "release" / "rhns_mars_release_matrix.json"
    obj = json.loads(path.read_text(encoding="utf-8"))
    components = obj["components"]
    required = {
        "RHNS-Architecture", "rhns-agent-core", "garcar-rhns",
        "garcar-rhns-core", "garcar-rhns-edge", "gitops-rhns",
        "mars-api", "mars-production", "mars-ai-debugger",
        "udcb-mars-implementation", "mars-benchmark-research",
    }
    names = [item["repo"].removeprefix("Garrettc123/") for item in components]
    if len(names) != len(required) or set(names) != required:
        raise SystemExit("Release manifest must cover exactly eleven distinct repositories")
    if obj["default_branch"] != "main":
        raise SystemExit("Unexpected release target branch")
    if obj["scope"] != "source_changes_only_no_deployment":
        raise SystemExit("Release requires independent deployment approval")
    inv = obj["invariants"]
    for attr in ("production_deployments_enabled", "automatic_vercel_builds_enabled",
                 "paid_inference_enabled", "outbound_customer_communications_enabled",
                 "trading_enabled", "cloud_resources_created"):
        if inv.get(attr) is not False:
            raise SystemExit("Unsafe release state: " + attr)
    for item in components:
        workflows = item.get("required_workflows")
        if (not isinstance(workflows, list) or not workflows or
                len(workflows) != len(set(map(str, workflows))) or
                any(not isinstance(name, str) or not name for name in workflows)):
            raise SystemExit("Missing unique required CI workflow names")
        if item["pr_url"] != "https://github.com/" + item["repo"] + "/pull/" + str(item["pr"]):
            raise SystemExit("Invalid pull request reference")
        if item.get("verified_runtime") is not False or item.get("verified_deployment") is not False:
            raise SystemExit("Do not claim execution proof without provider verification")
        if item["target"] in ("distributed-ray-worker", "argocd-gitops", "research-placeholder"):
            if item["gate"] != "no_vercel_deployment":
                raise SystemExit("Non-web repository must not deploy to Vercel")
        if item["target"] == "dedicated-worker" and item["gate"] != "blocked_pending_durable_state":
            raise SystemExit("Edge workload requires external durability")
    print("Release matrix consistency PASS (source metadata only; no provider proof).")

if __name__ == "__main__":
    validate()
