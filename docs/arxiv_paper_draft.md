# RHNS: A Recursive Hierarchical Neuro-Symbolic Architecture for Persistent Multi-Agent Reasoning

**Garrett Carrol** — Garcar Enterprise, Alvarado TX  
**Preprint draft** — May 2026  

---

## Abstract

We present RHNS (Recursive Hierarchical Neuro-Symbolic), a cognitive architecture for persistent multi-agent AI reasoning that combines symbolic knowledge representation with neural sub-symbolic processing. RHNS introduces the Stateful Reasoning Record (SRR) as a first-class primitive for cross-domain state persistence, causal model learning, and goal inference. The architecture operates across five domains (ARC-AGI-3, NWU, MARS, TITAN, enterprise automation) with a unified Cognitive Work Unit (CWU) budget system that bounds compute expenditure per reasoning cycle. We describe the architecture, known limitations (bug audit), and open implementation at github.com/Garrettc123/RHNS-Architecture.

**Keywords:** neuro-symbolic AI, multi-agent systems, persistent reasoning, causal learning, agentic OS

---

## 1. Introduction

Most agent frameworks treat each LLM call as stateless. RHNS is built on the opposite premise: reasoning state should persist, compound, and be symbolically inspectable at every layer. The architecture addresses three core limitations of contemporary agent systems:

1. **Stateless inference** — each call starts cold, discarding accumulated causal knowledge  
2. **Opaque goal representation** — goals are embedded in prompts, not symbolically grounded  
3. **Unbounded compute** — no mechanism to bound or audit reasoning expenditure

RHNS addresses these with the SRR (stateful record), CausalModel (learned action-effect rules), and the CWU budget system.

---

## 2. Related Work

- **LATS** (Liu et al., 2023) — Language Agent Tree Search: tree-based planning over LLM actions. RHNS extends this with persistent causal grounding across episodes.
- **MemGPT** (Packer et al., 2023) — tiered memory for LLM agents. RHNS adds symbolic causal rules on top of episodic memory.
- **GraphRAG** (Edge et al., 2024) — graph-based retrieval augmented generation. RHNS uses knowledge graph structures for causal rule indexing.
- **ReAct** (Yao et al., 2022) — reasoning + acting. RHNS adds persistent state across ReAct cycles.

---

## 3. Architecture

### 3.1 Stateful Reasoning Record (SRR)

The SRR is the central data structure. Each agent instance owns one SRR that persists across all reasoning cycles within a session.

```
SRR:
  domain: str                  # ARC_AGI_3 | NWU | MARS | TITAN | ENTERPRISE
  cwu_consumed: float          # running compute budget spend
  causal_model: Dict[str, CausalRule]   # learned action-effect rules
  active_causal_rules: List[CausalRule] # high-confidence rules (conf >= 0.8)
  symbolic_goal: Dict          # inferred current goal
  episode_history: List[Dict]  # (state, action, reward, turn) tuples
```

### 3.2 CausalModel Update

On each (state, action, state', reward) observation, RHNS updates its causal model using a Bayesian confidence increment:

- Matching observation: `confidence += 0.1` (capped at 1.0)  
- Contradicting observation: `confidence -= 0.2` (floored at 0.0)  
- Rules promoted to `active_causal_rules` at `confidence >= 0.8`

### 3.3 Goal Inference

Goal inference extracts structural patterns from reward-generating states in episode history. With < 2 reward samples, status is `EXPLORING`. With >= 2, the system identifies the best action pattern and computes consistency across reward samples.

### 3.4 Hierarchical Layers

| Layer | Name | Function |
|-------|------|----------|
| L0 | Perception | Raw input normalization |
| L1 | Pattern Recognition | Neural sub-symbolic features |
| L2 | Symbolic Grounding | KG-based entity resolution |
| L3 | Causal Reasoning | CausalModel + GoalInference |
| L4 | Meta-Optimization | EloMetaOptimizer (partial — see §5) |
| L5 | Domain Orchestration | Multi-domain SRR routing |

---

## 4. Implementation

RHNS v2.0 is implemented in Python 3.11+. The public repository includes:

- `rhns/core/causal.py` — CausalModel + GoalInference
- `rhns/srr.py` — SRR dataclass and domain definitions
- `tests/` — unit tests for all core modules
- `docs/bug-audit.md` — transparent known-issues log

Deployment targets: AWS Lambda (stateless inference), Railway (persistent service), local Termux (mobile development).

---

## 5. Limitations & Bug Audit

We document known issues transparently per Garcar Enterprise's no-fabrication policy:

1. **KG lookup latency** — knowledge graph queries add 80-200ms per L2 call; caching partially mitigates
2. **Race conditions** — concurrent SRR writes under high load can corrupt causal model state; mutex lock pending
3. **Confidence oscillation** — rules near the 0.8 threshold oscillate on noisy reward signals
4. **EloMetaOptimizer (L4)** — implemented but not connected to the main reasoning loop (dead code in v2.0)
5. **NWU novelty floor** — novelty scoring floors at 0.1 regardless of true entropy; underestimates exploration value

---

## 6. Future Work

- Connect EloMetaOptimizer to main loop for meta-level strategy adaptation
- Distributed SRR sharing across agent instances (multi-agent causal consensus)
- ARC-AGI-3 benchmark evaluation with real numbers (placeholder removed before submission)
- RHNS-as-a-Service API for enterprise customers via Garcar Enterprise

---

## References

- Liu, A. et al. (2023). LATS: Language Agent Tree Search. arXiv:2310.04406
- Packer, C. et al. (2023). MemGPT: Towards LLMs as Operating Systems. arXiv:2310.08560
- Edge, D. et al. (2024). From Local to Global: A Graph RAG Approach. arXiv:2404.16130
- Yao, S. et al. (2022). ReAct: Synergizing Reasoning and Acting in Language Models. arXiv:2210.03629
