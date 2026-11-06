# No-synthetic runtime policy and current scope

The agent no longer supplies hard-coded search expansions or string-length
critic scores. It requires caller-supplied generator and critic callbacks
and HRM/decoder checkpoint files. Strict state-dict loading is mandatory;
there is no random-weight fallback. Checkpoints must be trusted local
state dictionaries compatible with the supplied architecture dimensions.
Checkpoint existence and successful loading do not prove training quality,
calibration, provenance, or correctness. Callback quality needs evaluation.

Non-commit metacognitive decisions cannot invoke the decoder. Generated
hypotheses are not automatically consolidated into factual memory. Outputs
are explicitly generated_unverified, never claimed to be verified answers.

The root and api entry points use the same FastAPI application. POST /run
and POST /reason accept JSON {"goal": "..."}. RHNS_API_KEY is required
and clients supply Authorization: Bearer <key>. The default app returns
503 for execution until a deployment bootstrap calls create_app with a
real agent factory. This patch does not supply that backend or checkpoints.
/health checks the API process only. /ready does not load or certify models.
No credentials, external actions, merge, or deployment are included.

This patch removes the inspected synthetic agent defaults, not every
possible placeholder across the repository. Other modules and historical
documentation still require a full audit. In particular, encoder embedding
norm is not calibrated confidence. Durable memory/auditing, real provider
integration, grounded search evaluation, quotas, job orchestration, and
full API/model/deployment tests remain outstanding. No production-readiness
or end-to-end completion claim is made.
