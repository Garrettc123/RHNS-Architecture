"""Read-only symbolic reasoning diagnostic using the tested LATS implementation.

This controller parses literal predicates and ranks them by parser confidence.
It is NOT a language-model planner, factual verifier, observed-reward estimator
or executor. It does not access credentials, production systems or networks.
"""

import uuid

from reasoning.lats import LATS
from symbolic.parser import NeuralSymbolicParser


class LATSController:
    MAX_PREDICATES = 8

    def __init__(self):
        self.parser = NeuralSymbolicParser()

    def run(self, goal: str, schema: str = "general_reasoning") -> dict:
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("goal must be a non-empty string")
        goal = goal.strip()
        if len(goal) > 2000:
            raise ValueError("goal exceeds the 2000-character limit")
        if schema != "general_reasoning":
            raise ValueError("only the general_reasoning schema is implemented")

        predicates = self.parser.parse(goal)[:self.MAX_PREDICATES]
        states = [
            f"{p.functor}({', '.join(p.arguments)})"
            for p in predicates
        ]
        scores = dict(zip(states, (p.confidence for p in predicates)))
        # The critic is a syntactic ranking only. No truth claims are made.
        search = LATS(
            generator=lambda s: states if s == goal else [],
            critic=lambda s: scores.get(s, 0.0),
            max_depth=1,
            n_expansions=self.MAX_PREDICATES,
            budget=1,
        )
        best = search.search(goal)
        return {
            "frame_id": str(uuid.uuid4()),
            "verifier_status": "parsed_unverified" if states else "no_predicates",
            "operator_history": [
                f"parser: {len(states)} predicate(s) extracted",
                f"lats: selected {best.state!r}",
                "execution: skipped (read-only diagnostic)",
            ],
            "subgoal_stack": states,
            "reward": 0.0,  # No environment or business reward was observed.
            "depth_reached": best.depth,
            "tree_size": 1 + len(states),
            "execution_mode": "analysis_only",
            "best_state": best.state,
        }
