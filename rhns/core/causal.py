import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

# Minimal standalone SRR/CausalRule dataclasses (no external deps)
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CausalRule:
    rule_id: str
    action: str
    context_hash: str
    effect_delta: dict
    reward_signal: float
    confidence: float
    observations: int
    domain: str
    created_at: int
    last_updated: int


@dataclass
class SRR:
    domain: str = "default"
    cwu_consumed: float = 0.0
    causal_model: dict = field(default_factory=dict)
    active_causal_rules: list = field(default_factory=list)
    symbolic_goal: dict = field(default_factory=dict)
    episode_history: list = field(default_factory=list)


CWU_WEIGHTS = {"causal_update": 0.1, "goal_inference": 0.2}


def update_causal_model(
    srr: SRR, prev_frame: Any, action: Any, curr_frame: Any, reward: float
) -> SRR:
    srr.cwu_consumed += CWU_WEIGHTS["causal_update"]
    delta = _compute_delta(prev_frame, curr_frame)
    if not delta:
        return srr
    action_str = str(action)
    context_hash = hashlib.md5(str(prev_frame).encode()).hexdigest()[:8]
    rule_key = f"{action_str}:{context_hash}"
    now = time.time_ns()
    existing = srr.causal_model.get(rule_key)
    if existing:
        existing.observations += 1
        if existing.effect_delta == delta:
            existing.confidence = min(1.0, existing.confidence + 0.1)
        else:
            existing.confidence = max(0.0, existing.confidence - 0.2)
        existing.last_updated = now
        if reward > 0:
            existing.reward_signal = (
                (existing.reward_signal * (existing.observations - 1) + reward)
                / existing.observations
            )
    else:
        srr.causal_model[rule_key] = CausalRule(
            rule_id=str(uuid.uuid4())[:8],
            action=action_str,
            context_hash=context_hash,
            effect_delta=delta,
            reward_signal=reward,
            confidence=0.4,
            observations=1,
            domain=srr.domain,
            created_at=now,
            last_updated=now,
        )
    srr.active_causal_rules = [
        r for r in srr.causal_model.values() if r.confidence >= 0.8
    ]
    return srr


def infer_goal(srr: SRR) -> SRR:
    srr.cwu_consumed += CWU_WEIGHTS["goal_inference"]
    reward_states = [h for h in srr.episode_history if h.get("reward", 0) > 0.5]
    if len(reward_states) < 2:
        srr.symbolic_goal = {
            "status": "EXPLORING",
            "confidence": 0.0,
            "samples": len(reward_states),
        }
        return srr
    action_rewards = {}
    for h in reward_states:
        a = str(h["action"])
        action_rewards[a] = action_rewards.get(a, []) + [h["reward"]]
    best_action = max(action_rewards, key=lambda a: sum(action_rewards[a]))
    consistency = len(action_rewards[best_action]) / len(reward_states)
    confidence = min(1.0, len(reward_states) * 0.15 * consistency)
    srr.symbolic_goal = {
        "status": "INFERRED",
        "confidence": confidence,
        "best_action_pattern": best_action,
        "reward_samples": len(reward_states),
        "supporting_causal_rules": len(srr.active_causal_rules),
        "action_consistency": consistency,
    }
    return srr


def _compute_delta(prev: Any, curr: Any) -> dict:
    if isinstance(prev, dict) and isinstance(curr, dict):
        return {k: curr[k] for k in curr if curr.get(k) != prev.get(k)}
    if isinstance(prev, list) and isinstance(curr, list):
        if len(prev) == len(curr):
            return {
                str(i): curr[i]
                for i, (p, c) in enumerate(zip(prev, curr))
                if p != c
            }
        return {"length_changed": {"from": len(prev), "to": len(curr)}}
    return {
        "changed": str(prev) != str(curr),
        "curr_hash": hashlib.md5(str(curr).encode()).hexdigest()[:8],
    }
