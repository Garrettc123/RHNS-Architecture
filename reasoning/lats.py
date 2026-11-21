"""Bounded, deterministic Language Agent Tree Search (LATS).

``budget`` counts node-expansion rounds, not critic invocations.  A single
round scores up to ``n_expansions`` new candidates exactly once.  Results
are ranked by their own finite critic scores (not ancestor backup values).
"""

import math
from dataclasses import dataclass, field
from itertools import islice
from typing import Callable, List, Optional


@dataclass
class TreeNode:
    state: str
    parent: Optional["TreeNode"] = None
    children: List["TreeNode"] = field(default_factory=list)
    visits: int = 0
    value: float = 0.0
    depth: int = 0
    # Appended to retain compatibility with existing positional construction.
    evaluation_score: Optional[float] = None
    expanded: bool = False

    def ucb(self, c: float = 1.414) -> float:
        if self.visits == 0:
            return float("inf")
        parent_visits = max(1, self.parent.visits if self.parent else 1)
        return (self.value / self.visits) + c * math.sqrt(
            math.log(parent_visits) / self.visits
        )

    def is_leaf(self) -> bool:
        return len(self.children) == 0


class LATS:
    """Search candidate states with finite scoring and bounded expansions.

    A generated state is scored once per search.  ``budget`` limits rounds
    of expansion, while ``n_expansions`` limits candidates scored per round.
    A fresh tree is built per ``search`` call.  No callbacks are swallowed.
    """

    def __init__(
        self,
        generator: Callable[[str], List[str]],
        critic: Callable[[str], float],
        max_depth: int = 6,
        n_expansions: int = 3,
        budget: int = 20,
    ):
        for name, value, minimum in (
            ("max_depth", max_depth, 0),
            ("n_expansions", n_expansions, 1),
            ("budget", budget, 1),
        ):
            if type(value) is not int or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        self.generator = generator
        self.critic = critic
        self.max_depth = max_depth
        self.n_expansions = n_expansions
        self.budget = budget

    def _select(self, node: TreeNode) -> Optional[TreeNode]:
        """Select an expandable node; prune exhausted/depth-bound branches."""
        if node.depth >= self.max_depth:
            return None
        if not node.expanded:
            return node

        # Preserve insertion order on UCB ties.
        available = []
        for child in node.children:
            descendant = self._select(child)
            if descendant is not None:
                available.append((child, descendant))
        if not available:
            return None
        return max(available, key=lambda pair: pair[0].ucb())[1]

    def _expand(self, node: TreeNode) -> List[TreeNode]:
        if node.depth >= self.max_depth or node.expanded:
            return []
        # islice also supports iterator generators and avoids materializing
        # more than the configured number of child states.
        candidates = list(islice(self.generator(node.state), self.n_expansions))
        node.expanded = True
        for state in candidates:
            node.children.append(
                TreeNode(state=state, parent=node, depth=node.depth + 1)
            )
        return node.children

    def _evaluate(self, node: TreeNode) -> float:
        if node.evaluation_score is not None:
            return node.evaluation_score
        score = float(self.critic(node.state))
        if not math.isfinite(score):
            raise ValueError(f"critic returned non-finite score for {node.state!r}")
        node.evaluation_score = score
        node.value += score
        node.visits += 1
        return score

    def _backpropagate(self, node: TreeNode, score: float) -> None:
        current = node.parent
        while current is not None:
            current.visits += 1
            current.value += score * 0.95
            current = current.parent

    def search(self, root_state: str) -> TreeNode:
        root = TreeNode(state=root_state)
        best: Optional[TreeNode] = None

        def record(node: TreeNode) -> None:
            nonlocal best
            if node.evaluation_score is None:
                score = self._evaluate(node)
                self._backpropagate(node, score)
            if best is None or node.evaluation_score > best.evaluation_score:
                best = node

        for _ in range(self.budget):
            selected = self._select(root)
            if selected is None:
                break  # every expandable branch is exhausted
            children = self._expand(selected)
            if not children:
                record(selected)
            else:
                for child in children:
                    record(child)

        if best is None:  # zero-depth or an otherwise unexpanded root
            record(root)
        return best
