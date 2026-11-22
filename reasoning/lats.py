# reasoning/lats.py
"""Language Agent Tree Search with an optional fail-closed candidate gate."""
import math
from dataclasses import dataclass, field
from typing import List, Optional, Callable


@dataclass
class TreeNode:
    state: str
    parent: Optional["TreeNode"] = None
    children: List["TreeNode"] = field(default_factory=list)
    visits: int = 0
    value: float = 0.0
    depth: int = 0

    def ucb(self, c: float = 1.414) -> float:
        if self.visits == 0:
            return float("inf")
        parent_visits = self.parent.visits if self.parent else 1
        return (self.value / self.visits) + c * math.sqrt(
            math.log(max(parent_visits, 1)) / self.visits
        )

    def is_leaf(self) -> bool:
        return len(self.children) == 0


class LATS:
    """Generator proposes candidates; optional validator gates them before insertion.

    The validator must be deterministic and side-effect-free. Rejected candidates
    never enter the tree and therefore cannot be selected or evaluated by the critic.
    """

    def __init__(
        self,
        generator: Callable[[str], List[str]],
        critic: Callable[[str], float],
        max_depth: int = 6,
        n_expansions: int = 3,
        budget: int = 20,
        validator: Optional[Callable[[str], bool]] = None,
    ):
        if any(type(value) is not int for value in (max_depth, n_expansions, budget)) or max_depth < 0 or n_expansions < 1 or budget < 1:
            raise ValueError("max_depth must be a non-negative integer; n_expansions and budget must be positive integers")
        self.generator = generator
        self.critic = critic
        self.max_depth = max_depth
        self.n_expansions = n_expansions
        self.budget = budget
        self.validator = validator
        self.rejected_candidates = 0

    def _select(self, node: TreeNode) -> TreeNode:
        while not node.is_leaf():
            node = max(node.children, key=lambda child: child.ucb())
        return node

    def _expand(self, node: TreeNode) -> List[TreeNode]:
        if node.depth >= self.max_depth:
            return []
        candidates = self.generator(node.state)[:self.n_expansions]
        accepted: List[TreeNode] = []
        for candidate in candidates:
            if not isinstance(candidate, str) or not candidate.strip():
                self.rejected_candidates += 1
                continue
            if self.validator is not None:
                try:
                    valid = self.validator(candidate)
                except Exception:
                    valid = False
                if valid is not True:
                    self.rejected_candidates += 1
                    continue
            child = TreeNode(state=candidate, parent=node, depth=node.depth + 1)
            node.children.append(child)
            accepted.append(child)
        return accepted

    def _evaluate(self, node: TreeNode, score: Optional[float] = None) -> float:
        if score is None:
            score = float(self.critic(node.state))
        if not math.isfinite(score):
            raise ValueError("critic must return a finite numeric score")
        node.value += score
        node.visits += 1
        return score

    def _backpropagate(self, node: TreeNode, score: float):
        current = node.parent
        discount = 0.95
        while current:
            current.visits += 1
            current.value += score * discount
            discount *= 0.95
            current = current.parent

    def search(self, root_state: str) -> TreeNode:
        root = TreeNode(state=root_state)
        for _ in range(self.budget):
            leaf = self._select(root)
            children = self._expand(leaf)
            if not children:
                # Without a policy gate, a genuinely empty expansion is a terminal
                # state and is evaluated once. When a validator rejects every
                # proposal, do NOT evaluate it or imply a validated candidate.
                if self.validator is None and leaf.visits == 0:
                    self._evaluate(leaf)
                continue
            # Score every admitted candidate exactly once. This prevents
            # unevaluated siblings (which default to zero) from outranking
            # negative but valid critic scores.
            scored_children = [
                (child, float(self.critic(child.state))) for child in children
            ]
            if any(not math.isfinite(score) for _, score in scored_children):
                raise ValueError("critic must return finite numeric scores")
            for child, score in scored_children:
                self._evaluate(child, score)
            best_child, best_score = max(scored_children, key=lambda item: item[1])
            self._backpropagate(best_child, best_score)

        def best_leaf(node: TreeNode) -> TreeNode:
            if node.is_leaf():
                return node
            return max(
                (best_leaf(child) for child in node.children),
                key=lambda item: item.value / max(item.visits, 1),
            )
        return best_leaf(root)
