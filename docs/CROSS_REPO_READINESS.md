# RHNS / MARS cross-repository release verifier

The manifest at `release/rhns_mars_release_matrix.json` pins the eleven
repositories, exact draft PR references and expected workflow names. Run
`python tools/release_readiness.py --output release-review.json`
to read real GitHub workflow results. This is **read-only**.

Provide `GITHUB_TOKEN` via your approved local secret manager or managed
CI environment. The fine-grained identity must have read-only metadata,
pull-request and Actions permissions for *each* relevant repository.
Never commit or paste credentials in chat, PRs, logs or artifacts. The
public CI test intentionally does **not** use your private-repository token.

The verifier rejects missing tokens, unexpected PR bases or branches,
absent pinned workflows, pending/failed checks, incomplete metadata,
and any unsupported claims of production runtime verification.
Workflow failures with no executable steps are described as
`failed_before_executable_steps`, **not** automatically diagnosed as billing.

Two separate statuses are returned:
- `ci_ready`: all pinned workflows for all eleven PR head SHAs succeeded;
- `release_ready`: always false until independent review, runtime
  attestation and deployment evidence are added through a reviewed
  follow-up process.

Exit code 2 means the release remains blocked. The script cannot merge,
change repositories, dispatch workflows, invoke providers, move money,
send messages, or create infrastructure.

For repositories with instant failed jobs and no steps, an authorized
GitHub account owner should inspect the Actions run's UI banner and
repository/organization Actions billing/policy settings. The symptom
alone cannot identify the underlying permission, quota or runner cause.

No production deployment was performed.
