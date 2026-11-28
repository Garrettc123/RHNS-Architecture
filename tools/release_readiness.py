"""Read-only cross-repository RHNS/MARS release evidence verifier.

Runs locally with a restricted GitHub token that can read all eleven repos.
This script cannot approve, merge, dispatch workflows, deploy, trade, or spend.
Missing or incomplete evidence always blocks readiness.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

MANIFEST = Path(__file__).resolve().parents[1] / "release" / "rhns_mars_release_matrix.json"
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA = re.compile(r"^[0-9a-fA-F]{40}$")


class EvidenceUnavailable(Exception):
    """An upstream response cannot certify a release gate."""


class GitHubReader:
    def __init__(self, token: str):
        if not token:
            raise EvidenceUnavailable("missing_readonly_github_token")
        self._token = token

    def get(self, path: str, params: dict[str, str | int] | None = None) -> dict:
        if not path.startswith("/repos/") or ".." in path or "://" in path:
            raise EvidenceUnavailable("invalid_github_resource")
        query = "?" + urlencode(params) if params else ""
        request = Request(
            "https://api.github.com" + path + query,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + self._token,
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Garcar-RHNS-release-readonly/1.0",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=12) as response:
                payload = response.read(1024 * 1024 + 1)
            if len(payload) > 1024 * 1024:
                raise EvidenceUnavailable("github_response_too_large")
            value = json.loads(payload)
            if not isinstance(value, dict):
                raise EvidenceUnavailable("github_response_not_an_object")
            return value
        except HTTPError as exc:
            # Never include provider bodies or headers, which could carry secrets.
            raise EvidenceUnavailable("github_http_" + str(exc.code)) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise EvidenceUnavailable("github_query_unavailable") from None


def inspect_component(component: dict, reader: GitHubReader) -> dict:
    """Return a scoped evidence record. No optimistic assumptions."""
    repo = component.get("repo")
    pr_number = component.get("pr")
    result = {"repo": repo, "pr": pr_number, "ci_pass": False,
              "review_pass": False, "runtime_pass": False,
              "deployment_pass": False, "head_sha": None,
              "reasons": [], "checks": []}
    if not isinstance(repo, str) or not REPO.fullmatch(repo):
        result["reasons"].append("invalid_repo")
        return result
    if type(pr_number) is not int or pr_number < 1:
        result["reasons"].append("invalid_pr")
        return result
    try:
        pr = reader.get(f"/repos/{repo}/pulls/{pr_number}")
    except EvidenceUnavailable as exc:
        result["reasons"].append(str(exc))
        return result

    if pr.get("state") != "open":
        result["reasons"].append("pr_not_open")
    if pr.get("draft") is not True:
        result["reasons"].append("pr_not_draft_under_review_gate")
    if (pr.get("base") or {}).get("ref") != "main":
        result["reasons"].append("unexpected_base_branch")
    if (pr.get("head") or {}).get("ref") != "fix/rhns-mars-release-gate-20261128":
        result["reasons"].append("unexpected_head_branch")
    head_sha = (pr.get("head") or {}).get("sha")
    if not isinstance(head_sha, str) or not SHA.fullmatch(head_sha):
        result["reasons"].append("missing_head_sha")
        return result
    result["head_sha"] = head_sha

    try:
        runs_data = reader.get(
            f"/repos/{repo}/actions/runs",
            {"head_sha": head_sha, "event": "pull_request", "per_page": 100},
        )
    except EvidenceUnavailable as exc:
        result["reasons"].append(str(exc))
        return result

    all_runs = runs_data.get("workflow_runs")
    if not isinstance(all_runs, list):
        result["reasons"].append("workflow_evidence_invalid")
        return result
    if (runs_data.get("total_count", len(all_runs)) > len(all_runs)
            and len(all_runs) >= 100):
        result["reasons"].append("workflow_evidence_truncated")
    runs = [run for run in all_runs if isinstance(run, dict)
            and run.get("head_sha") == head_sha
            and run.get("event") == "pull_request"]
    if not runs:
        result["reasons"].append("no_commit_matched_workflow_runs")
        return result
    # A run may have multiple attempts. Evaluate the latest attempt per
    # workflow ID and do not silently discard incomplete checks.
    latest: dict[int, dict] = {}
    for run in runs:
        workflow_id = run.get("workflow_id")
        if type(workflow_id) is not int:
            result["reasons"].append("workflow_id_missing")
            continue
        previous = latest.get(workflow_id)
        if previous is None or (str(run.get("created_at", "")),
                                int(run.get("run_attempt") or 0)) > (
                                    str(previous.get("created_at", "")),
                                    int(previous.get("run_attempt") or 0)):
            latest[workflow_id] = run
    for run in sorted(latest.values(), key=lambda item: str(item.get("name", ""))):
        state = run.get("status")
        conclusion = run.get("conclusion")
        item = {"name": run.get("name"), "status": state, "conclusion": conclusion,
                "run_id": run.get("id")}
        result["checks"].append(item)
        if state != "completed" or conclusion != "success":
            result["reasons"].append("workflow_not_successful")
            if conclusion == "failure" and type(run.get("id")) is int:
                try:
                    jobs = reader.get(
                        f"/repos/{repo}/actions/runs/{run['id']}/jobs",
                        {"per_page": 100},
                    ).get("jobs")
                    if isinstance(jobs, list) and jobs and all(
                            isinstance(job, dict) and not job.get("steps")
                            for job in jobs):
                        item["diagnostic"] = "failed_before_executable_steps"
                except EvidenceUnavailable:
                    item["diagnostic"] = "job_steps_unavailable"
    if not latest:
        result["reasons"].append("no_valid_workflow_identifiers")
    if not result["reasons"]:
        result["ci_pass"] = True
        # This is a draft; code review or release authorization is not granted.
    if component.get("verified_runtime") is True:
        result["reasons"].append("runtime_claim_requires_independent_attestation")
    if component.get("verified_deployment") is True:
        result["reasons"].append("deployment_claim_requires_independent_attestation")
    return result


def evaluate_release(manifest: dict, reader: GitHubReader | None) -> dict:
    components = manifest.get("components")
    if not isinstance(components, list) or len(components) != 11:
        raise EvidenceUnavailable("invalid_release_manifest")
    findings = []
    for component in components:
        if reader is None:
            findings.append({
                "repo": component.get("repo"), "pr": component.get("pr"),
                "ci_pass": False, "review_pass": False,
                "runtime_pass": False, "deployment_pass": False,
                "head_sha": None, "checks": [],
                "reasons": ["missing_readonly_github_token"],
            })
        else:
            findings.append(inspect_component(component, reader))
    ci_ready = all(row["ci_pass"] for row in findings)
    runtime_ready = all(row["runtime_pass"] for row in findings)
    release_ready = ci_ready and runtime_ready and all(
        row["review_pass"] and row["deployment_pass"] for row in findings
    )
    return {
        "release": manifest.get("release"),
        "scope": "read_only_evidence_no_provider_mutations",
        "components_checked": len(findings),
        "ci_ready": ci_ready,
        "release_ready": release_ready,
        "counts": {
            "ci_pass": sum(row["ci_pass"] for row in findings),
            "ci_blocked": sum(not row["ci_pass"] for row in findings),
        },
        "components": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--output", type=Path, default=None,
                        help="Optional JSON report path; never secret-bearing")
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        token = os.environ.get("GITHUB_TOKEN", "")
        reader = GitHubReader(token) if token else None
        report = evaluate_release(manifest, reader)
    except (OSError, ValueError, EvidenceUnavailable) as exc:
        # Sanitize exception classes and never include file paths or API payloads.
        report = {"release_ready": False, "ci_ready": False,
                  "error": str(exc) if isinstance(exc, EvidenceUnavailable)
                  else "release_evaluation_unavailable"}
    output = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0 if report.get("release_ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
