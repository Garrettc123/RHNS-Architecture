"""Offline regression suite for read-only cross-repository release review."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.release_readiness import (
    EvidenceUnavailable, GitHubReader, evaluate_release, inspect_component, main
)

HEAD = "a" * 40
BRANCH = "fix/rhns-mars-release-gate-20261128"

def component():
    return {"repo": "Garrettc123/mars-api", "pr": 7,
            "required_workflows": ["MARS API Validation (deployment gated)"],
            "verified_runtime": False, "verified_deployment": False}

def good_run(status="completed", conclusion="success", name="MARS API Validation (deployment gated)"):
    return {"id": 42, "workflow_id": 11, "name": name, "head_sha": HEAD,
            "event": "pull_request", "status": status, "conclusion": conclusion,
            "created_at": "2026-11-28T04:00:00Z", "run_attempt": 1}

class FakeReader:
    def __init__(self, runs=None, pr=None, jobs=None):
        self.runs = [good_run()] if runs is None else runs
        self.pr = pr or {"state": "open", "draft": True,
                         "base": {"ref": "main"}, "head": {"ref": BRANCH, "sha": HEAD, "repo": {"full_name": "Garrettc123/mars-api"}}}
        self.jobs = [{"id": 5, "steps": None}] if jobs is None else jobs
    def get(self, path, params=None):
        if path.endswith("/pulls/7"):
            return self.pr
        if path.endswith("/actions/runs"):
            return {"total_count": len(self.runs), "workflow_runs": self.runs}
        if path.endswith("/jobs"):
            return {"jobs": self.jobs}
        raise AssertionError(path)

class ReadinessTests(unittest.TestCase):
    def test_verified_workflow_is_only_ci_ready(self):
        x = inspect_component(component(), FakeReader())
        self.assertTrue(x["ci_pass"])
        self.assertFalse(x["review_pass"])
        self.assertFalse(x["runtime_pass"])
        self.assertFalse(x["deployment_pass"])

    def test_incomplete_run_blocks_ci(self):
        x = inspect_component(component(), FakeReader(runs=[good_run("in_progress", None)]))
        self.assertFalse(x["ci_pass"])
        self.assertIn("workflow_not_successful", x["reasons"])

    def test_failed_before_steps_is_diagnostic_not_approval(self):
        x = inspect_component(component(), FakeReader(runs=[good_run(conclusion="failure")]))
        self.assertFalse(x["ci_pass"])
        self.assertEqual(x["checks"][0]["diagnostic"], "failed_before_executable_steps")

    def test_missing_pinned_check_blocks(self):
        x = inspect_component(component(), FakeReader(runs=[good_run(name="Unrelated success")]))
        self.assertFalse(x["ci_pass"])
        self.assertIn("required_workflows_not_observed", x["reasons"])
        self.assertEqual(x["missing_workflows"], component()["required_workflows"])

    def test_wrong_branch_blocks(self):
        pr = {"state": "open", "draft": True, "base": {"ref": "main"},
              "head": {"ref": "other", "sha": HEAD, "repo": {"full_name": "Garrettc123/mars-api"}}}
        x = inspect_component(component(), FakeReader(pr=pr))
        self.assertFalse(x["ci_pass"])
        self.assertIn("unexpected_head_branch", x["reasons"])

    def test_fork_head_does_not_pass_source_provenance(self):
        pr = {"state": "open", "draft": True, "base": {"ref": "main"},
              "head": {"ref": BRANCH, "sha": HEAD,
                       "repo": {"full_name": "thirdparty/mars-api"}}}
        x = inspect_component(component(), FakeReader(pr=pr))
        self.assertFalse(x["ci_pass"])
        self.assertIn("unexpected_head_repository", x["reasons"])

    def test_invalid_repository_prevents_api_request(self):
        item = dict(component(), repo="../evil")
        x = inspect_component(item, FakeReader())
        self.assertEqual(x["reasons"], ["invalid_repo"])

    def test_github_reader_missing_token_fails_closed(self):
        with self.assertRaises(EvidenceUnavailable):
            GitHubReader("")

    def test_all_green_ci_does_not_mean_release_ready(self):
        obj = {"release": "test", "components": [component()] * 11}
        report = evaluate_release(obj, FakeReader())
        self.assertEqual(report["counts"]["ci_pass"], 11)
        self.assertTrue(report["ci_ready"])
        self.assertFalse(report["release_ready"])

    def test_missing_auth_blocks_all_components(self):
        obj = {"release": "test", "components": [component()] * 11}
        report = evaluate_release(obj, None)
        self.assertEqual(report["counts"]["ci_blocked"], 11)
        self.assertFalse(report["release_ready"])

    def test_cli_missing_auth_never_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps({"release": "test",
                                        "components": [component()] * 11}))
            out = io.StringIO()
            with patch.dict("os.environ", {"GITHUB_TOKEN": ""}):
                with contextlib.redirect_stdout(out):
                    exit_code = main(["--manifest", str(path)])
        result = json.loads(out.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertFalse(result["release_ready"])
        self.assertEqual(result["counts"]["ci_blocked"], 11)

if __name__ == "__main__":
    unittest.main()
