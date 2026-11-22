import unittest
from reasoning.lats import LATS

class SearchRegressionTests(unittest.TestCase):
    def test_negative_scores(self):
        scores = {"A": -0.1, "B": -0.5, "C": -0.9}
        result = LATS(lambda _: list(scores), scores.__getitem__, budget=1).search("root")
        self.assertEqual(result.state, "A")
        self.assertGreater(result.visits, 0)

    def test_each_candidate_scored_once(self):
        calls = []
        def critic(state):
            calls.append(state)
            return 1.0
        LATS(lambda _: ["A", "B", "C"], critic, budget=1).search("root")
        self.assertEqual(calls, ["A", "B", "C"])

    def test_nonfinite_scores_rejected(self):
        for score in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(score=score), self.assertRaises(ValueError):
                LATS(lambda _: [], lambda _: score).search("root")

    def test_invalid_settings_rejected(self):
        for settings in ({"budget": 0}, {"budget": -1}, {"budget": True},
                         {"max_depth": -1}, {"n_expansions": 0}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                LATS(lambda _: [], lambda _: 1.0, **settings)

    def test_empty_expansion_evaluates_root(self):
        result = LATS(lambda _: [], lambda _: -1.0, budget=1).search("root")
        self.assertEqual((result.state, result.visits, result.value), ("root", 1, -1.0))

    def test_zero_depth_does_not_generate(self):
        def forbidden(_):
            raise AssertionError("generator must not be called")
        self.assertEqual(LATS(forbidden, lambda _: 1.0, max_depth=0).search("root").depth, 0)

    def test_callback_failure_propagates(self):
        def broken(_):
            raise RuntimeError("provider unavailable")
        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            LATS(lambda _: ["A"], broken).search("root")

    def test_ties_are_deterministic(self):
        result = LATS(lambda _: ["A", "B"], lambda _: 0.0, budget=1).search("root")
        self.assertEqual(result.state, "A")
