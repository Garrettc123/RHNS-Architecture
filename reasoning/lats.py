# reasoning/lats.py
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
        return (self.value / self.visits) + c * math.sqrt(math.log(parent_visits) / self.visits)

    def is_leaf(self) -> bool:
        return len(self.children) == 0

class LATS:
    """
    Language Agent Tree Search.
    Generator proposes expansions; critic scores them;
    MCTS governs search budget allocation.
    """
    def __init__(
        self,
        generator: Callable[[str], List[str]],
        critic: Callable[[str], float],
        max_depth: int = 6,
        n_expansions: int = 3,
        budget: int = 20
    ):
        self.generator = generator
        self.critic = critic
        self.max_depth = max_depth
        self.n_expansions = n_expansions
        self.budget = budget

    def _select(self, node: TreeNode) -> TreeNode:
        while not node.is_leaf():
            node = max(node.children, key=lambda c: c.ucb())
        return node

    def _expand(self, node: TreeNode) -> List[TreeNode]:
        if node.depth >= self.max_depth:
            return []
        candidates = self.generator(node.state)[:self.n_expansions]
        for cand in candidates:
            child = TreeNode(state=cand, parent=node, depth=node.depth + 1)
            node.children.append(child)
        return node.children

    def _evaluate(self, node: TreeNode) -> float:
        score = self.critic(node.state)
        node.value += score
        node.visits += 1
        return score

    def _backpropagate(self, node: TreeNode, score: float):
        current = node.parent
        while current:
            current.visits += 1
            current.value += score * 0.95
            current = current.parent

    def search(self, root_state: str) -> TreeNode:
        root = TreeNode(state=root_state, visits=1)
        for _ in range(self.budget):
            leaf = self._select(root)
            children = self._expand(leaf)
            if not children:
                score = self._evaluate(leaf)
                self._backpropagate(leaf, score)
            else:
                best_child = max(children, key=lambda c: self.critic(c.state))
                score = self._evaluate(best_child)
                self._backpropagate(best_child, score)

        def best_leaf(node):
            if node.is_leaf():
                return node
            return max(
                (best_leaf(c) for c in node.children),
                key=lambda n: n.value / max(n.visits, 1)
            )
        return best_leaf(root)
