import unittest

from symbolic.plan_verifier import verify_plan


class PlanVerifierTests(unittest.TestCase):
    def test_approves_allowlisted_read_only_plan(self):
        result = verify_plan({
            "goal": "Review a lead record",
            "actions": [{"action_id": "a1", "operation": "read", "target": "lead:123"}],
        })
        self.assertTrue(result.approved)
        self.assertEqual(result.status, "approved")
        self.assertEqual(result.violations, ())

    def test_rejects_external_side_effect(self):
        result = verify_plan({
            "goal": "Contact prospect",
            "actions": [{"action_id": "a1", "operation": "send_email", "target": "prospect"}],
        })
        self.assertFalse(result.approved)
        self.assertIn("POLICY-002", {v.rule_id for v in result.violations})

    def test_rejects_unknown_operation(self):
        result = verify_plan({
            "goal": "Do something",
            "actions": [{"action_id": "a1", "operation": "magic", "target": "x"}],
        })
        self.assertIn("POLICY-003", {v.rule_id for v in result.violations})

    def test_rejects_duplicate_ids(self):
        action = {"action_id": "same", "operation": "read", "target": "x"}
        result = verify_plan({"goal": "Read", "actions": [action, action]})
        self.assertIn("ACTION-003", {v.rule_id for v in result.violations})

    def test_rejects_missing_goal_and_actions(self):
        result = verify_plan({"goal": "", "actions": []})
        rule_ids = {v.rule_id for v in result.violations}
        self.assertTrue({"PLAN-002", "PLAN-003"}.issubset(rule_ids))

    def test_rejects_human_approval_and_external_effect_flags(self):
        result = verify_plan({
            "goal": "Publish content",
            "actions": [{
                "action_id": "a1", "operation": "draft", "target": "content",
                "external_effect": True, "requires_human_approval": True,
            }],
        })
        rule_ids = {v.rule_id for v in result.violations}
        self.assertTrue({"POLICY-004", "POLICY-005"}.issubset(rule_ids))

    def test_rejects_non_object(self):
        result = verify_plan("not a plan")
        self.assertFalse(result.approved)
        self.assertEqual(result.violations[0].rule_id, "PLAN-001")

    def test_enforces_action_limit(self):
        actions = [
            {"action_id": str(i), "operation": "read", "target": "x"}
            for i in range(26)
        ]
        result = verify_plan({"goal": "Read records", "actions": actions})
        self.assertIn("PLAN-004", {v.rule_id for v in result.violations})


if __name__ == "__main__":
    unittest.main()
