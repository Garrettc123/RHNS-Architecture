# RHNS Architecture

## Current implementation boundary (2026-11-21)

This repository contains an architecture publication and a **prototype**, not a verified autonomous production operating system. The public API performs local, bounded predicate extraction and LATS ranking; it **does not** validate factual truth, train a neural model, invoke tools, send messages, change production data, or observe business rewards. The `reward` field is `0.0` because no external reward is observed.

The experimental neural agent uses a pretrained encoder when **pre-provisioned locally**, plus untrained HRM and decoding heads. Its scores must not authorize business actions or be advertised as calibrated confidence. Its audit chain and memory are in-process and not durable.

### Local API (CPU only, no model download)

```bash
python -m pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8090
# POST /run with JSON: {"goal":"fire causes smoke"}
```

### Tests and optional modules

```bash
python -m pip install -r requirements-neural.txt pytest pytest-cov
python -m pytest tests/ -q
# Optional, separate provider packages: requirements-integrations.txt
```

For containerized diagnostics: `docker compose -f infra/docker-compose.yml up --build`. It binds `127.0.0.1:8090`, runs as a non-root user, and requires no external API keys. Use an authenticated, rate-limited gateway before exposing endpoints publicly.

### Release gates

- Require successful GitHub Actions lint, API smoke, full Python 3.11/3.12 tests, and a reviewed PR.
- Provision neural weights and run measured evaluations before treating neural results as valid decisions.
- Implement tenant isolation, approval binding, persistent tamper-evident receipts, external integrations, and service monitoring separately.
- Deploy only with explicit approval after provider credentials and deployment provenance are verified. The repository's release workflow is a **preflight only**, not an actual deployment.
- Fleet-wide automatic credential propagation has been retired; manage provider secrets in individually authorized GitHub environments.

See [implementation and gap status](docs/IMPLEMENTATION_STATUS.md).

---

RHNS (Recursive Hierarchical Network System) is a neuro-symbolic architecture for recursive, governed, multi-agent reasoning.

Created by **Garrett Carrol** at **Garcar Enterprise**, RHNS is designed as a cognitive substrate for agentic operating systems that need to plan, remember, adapt, and execute across multiple business and scientific domains. The architecture combines recursive goal trees, graph-grounded memory, skill synthesis, metacognitive control, and runtime policy enforcement.

**Prior art established: April 27, 2026**  
**Public IP metadata finalized: October 12, 2026** (`CITATION.cff` + `.zenodo.json` on main)

[![Zenodo](https://img.shields.io/badge/Zenodo-Prior%20Art%20Deposit-blue)](docs/zenodo-description.txt)
[![arXiv](https://img.shields.io/badge/arXiv-Preprint-red)](docs/arxiv-abstract.txt)
[![Defensive Publication](https://img.shields.io/badge/IP%20Commons-Defensive%20Publication-green)](docs/defensive-publication.txt)

---

## Core Claims

- Recursive decomposition of high-level goals into executable sub-goals via a hierarchical goal tree
- Federated memory and knowledge graph integration across deployments
- Symbolic governance layer for auditability and constraint enforcement at every reasoning step
- Skill synthesis loop (NSP) for converting execution traces into reusable procedural schemas
- Metacognitive controller (CMC) for oversight, retry, audit, and policy validation
- Designed for multi-domain agent orchestration — not single-task prompting

---

## Architecture Components

| Component | Role |
|-----------|------|
| Recursive Goal Tree (RGT) | Decomposes high-level objectives into hierarchical sub-goals |
| Federated Knowledge Graph | Persistent, cross-deployment graph memory |
| Skill Synthesis Protocol (NSP) | Converts execution traces into reusable schemas |
| Metacognitive Controller (CMC) | Oversight, retry, audit, and governance |
| Symbolic Constraint Engine | Enforces policies before, during, and after execution |
| Perceptual Fusion Layer | Integrates multi-modal inputs into structured representations |
| Recursive Self-Improvement Loop (RSI) | Compounds learning across deployments |

---

## Why Publish This Now

This repository exists to establish public technical prior art and document the original RHNS architecture in an open, timestamped form. Once published, this record prevents any later exclusive patent claims over the disclosed architecture components.

All documents in `/docs` were authored by Garrett Carrol and first published April 27, 2026.

---

## Repository Structure

```
RHNS-Architecture/
├── README.md                          # This file
├── CITATION.cff                       # GitHub citation metadata (CFF)
├── .zenodo.json                       # Zenodo archival metadata (takes precedence)
├── docs/
│   ├── rhns-whitepaper.txt            # Full technical whitepaper
│   ├── arxiv-abstract.txt             # arXiv submission abstract
│   ├── zenodo-description.txt         # Zenodo deposit description
│   ├── defensive-publication.txt      # IP Commons technical disclosure
│   └── researcher-endorsement-ask.txt # arXiv endorsement email templates
└── LICENSE                            # CC BY 4.0
```

---

## Author & Contact

**Garrett Carrol**  
Founder, Garcar Enterprise  
Grandview, Texas  
GitHub: [Garrettc123](https://github.com/Garrettc123)  

---

## License

This architecture documentation is published under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/). You may share and adapt with attribution.
