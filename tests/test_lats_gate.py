import json

from reasoning.lats import LATS


def test_lats_rejects_candidates_before_critic():
    critic_calls = []
    candidates = [
        json.dumps({
            "goal": "Review a record",
            "actions": [{"action_id": "safe", "operation": "read", "target": "record:1"}],
        }),
        json.dumps({
            "goal": "Send a message",
            "actions": [{"action_id": "unsafe", "operation": "send_email", "target": "customer"}],
        }),
        "not-json",
    ]

    def critic(state):
        critic_calls.append(state)
        return 0.7

    def validator(candidate):
        from symbolic.plan_verifier import verify_plan
        try:
            return verify_plan(json.loads(candidate)).approved
        except (TypeError, ValueError):
            return False

    search = LATS(
        generator=lambda _state: candidates,
        critic=critic,
        budget=1,
        validator=validator,
    )
    result = search.search("root")

    assert result.state == candidates[0]
    assert search.rejected_candidates == 2
    assert critic_calls == [candidates[0]]


def test_lats_fails_closed_when_every_candidate_is_rejected():
    critic_calls = []
    search = LATS(
        generator=lambda _state: ["bad candidate"],
        critic=lambda state: critic_calls.append(state) or 1.0,
        budget=2,
        validator=lambda _candidate: False,
    )

    result = search.search("root")

    assert result.state == "root"
    assert search.rejected_candidates == 2
    assert critic_calls == []


def test_lats_preserves_legacy_behavior_without_validator():
    search = LATS(
        generator=lambda state: [state + "_child"],
        critic=lambda _state: 0.5,
        budget=1,
    )

    result = search.search("root")

    assert result.state == "root_child"
    assert search.rejected_candidates == 0
