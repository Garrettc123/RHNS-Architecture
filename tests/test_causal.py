"""Tests for RHNS CausalModel + GoalInference (GAR-411)"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rhns.core.causal import update_causal_model, infer_goal, SRR


def test_causal_model_builds():
    srr = SRR(domain="ARC_AGI_3")
    srr = update_causal_model(srr, {"pos": [0, 0]}, "RIGHT", {"pos": [1, 0]}, 0.0)
    srr = update_causal_model(srr, {"pos": [1, 0]}, "RIGHT", {"pos": [2, 0]}, 1.0)
    for _ in range(6):
        srr = update_causal_model(srr, {"pos": [0, 0]}, "RIGHT", {"pos": [1, 0]}, 0.8)
    assert len(srr.causal_model) > 0, "Causal model should have rules"
    assert len(srr.active_causal_rules) > 0, "Should have active rules at confidence >= 0.8"
    print(f"  Causal model size: {len(srr.causal_model)}")
    print(f"  Active rules: {len(srr.active_causal_rules)}")


def test_goal_inference():
    srr = SRR(domain="ARC_AGI_3")
    srr.episode_history = [{"action": "RIGHT", "reward": 0.9, "turn": i} for i in range(5)]
    srr = infer_goal(srr)
    assert srr.symbolic_goal["status"] == "INFERRED", f"Expected INFERRED, got {srr.symbolic_goal['status']}"
    assert srr.symbolic_goal["confidence"] > 0
    print(f"  Goal: {srr.symbolic_goal}")


def test_exploring_with_few_samples():
    srr = SRR(domain="test")
    srr.episode_history = [{"action": "LEFT", "reward": 0.8, "turn": 0}]
    srr = infer_goal(srr)
    assert srr.symbolic_goal["status"] == "EXPLORING"


if __name__ == "__main__":
    test_causal_model_builds()
    test_goal_inference()
    test_exploring_with_few_samples()
    print("ALL TESTS PASSED")
