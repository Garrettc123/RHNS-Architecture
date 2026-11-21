"""Additional invariants for deterministic, bounded tree search."""
import unittest
from reasoning.lats import LATS


class SearchInvariantTests(unittest.TestCase):
    def test_best_intermediate_candidate_remains_eligible(self):
        scores = {"A": 0.9, "B": 0.1, "A1": -0.1, "B1": -0.2}
        def gen(state):
            return {"root": ["A", "B"], "A": ["A1"], "B": ["B1"]}.get(state, [])
        result = LATS(gen, scores.__getitem__, budget=4).search("root")
        self.assertEqual(result.state, "A")
        self.assertEqual(result.depth, 1)

    def test_expansion_count_is_bounded(self):
        calls = []
        def gen(state):
            calls.append(state)
            return [state + "a", state + "b"]
        LATS(gen, lambda _: 0.0, budget=2).search("r")
        self.assertLessEqual(len(calls), 2)

    def test_max_depth_is_respected(self):
        calls = []
        def gen(state):
            calls.append(state)
            return [state + "x"]
        node = LATS(gen, lambda s: len(s), max_depth=1, budget=20).search("r")
        self.assertEqual(calls, ["r"])
        self.assertEqual(node.depth, 1)

    def test_critic_score_is_cached_within_search(self):
        calls = []
        def critic(state):
            calls.append(state)
            return -0.1
        LATS(lambda s: [s + "x"] if len(s) < 3 else [], critic,
             budget=20, max_depth=4).search("r")
        self.assertEqual(calls, ["rx", "rxx"])

    def test_root_is_scored_once_at_zero_depth(self):
        calls = []
        lats = LATS(lambda _: self.fail("generator called"),
                    lambda s: calls.append(s) or 0.0, max_depth=0)
        node = lats.search("r")
        self.assertEqual(calls, ["r"])
        self.assertEqual((node.visits, node.depth), (1, 0))

    def test_generator_failure_propagates(self):
        def gen(_):
            raise RuntimeError("generator unavailable")
        with self.assertRaisesRegex(RuntimeError, "generator unavailable"):
            LATS(gen, lambda _: 1.0).search("r")

    def test_unscored_nodes_not_selected_over_negative(self):
        node = LATS(lambda _: ["A", "B", "C"],
                    {"A": -3.0, "B": -1.0, "C": -2.0}.__getitem__, budget=1).search("r")
        self.assertEqual(node.state, "B")
        self.assertEqual(node.evaluation_score, -1.0)

    def test_repeat_search_no_residual_state(self):
        lats = LATS(lambda _: ["A"], lambda _: 0.5, budget=1)
        a, b = lats.search("root"), lats.search("root")
        self.assertIsNot(a, b)
        self.assertEqual((a.state, a.value, a.visits), (b.state, b.value, b.visits))

    def test_noninteger_configuration_rejected(self):
        for key, invalid in (("budget", 1.2), ("n_expansions", True),
                             ("max_depth", False), ("max_depth", None)):
            with self.subTest(key=key, invalid=invalid), self.assertRaises(ValueError):
                LATS(lambda _: [], lambda _: 0.0, **{key: invalid})


if __name__ == "__main__":
    unittest.main()
