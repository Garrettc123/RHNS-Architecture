# symbolic/knowledge_graph.py
from typing import List, Dict
from dataclasses import dataclass, field
import json

@dataclass
class KGNode:
    id: str
    label: str
    properties: Dict = field(default_factory=dict)

@dataclass
class KGEdge:
    source: str
    target: str
    relation: str
    weight: float = 1.0

class KnowledgeGraph:
    def __init__(self):
        self.nodes: Dict[str, KGNode] = {}
        self.edges: List[KGEdge] = []
        self.index: Dict[str, List[KGEdge]] = {}

    def add_node(self, node: KGNode):
        self.nodes[node.id] = node

    def add_edge(self, edge: KGEdge):
        self.edges.append(edge)
        self.index.setdefault(edge.source, []).append(edge)

    def neighbors(self, node_id: str, depth: int = 2) -> List[KGNode]:
        visited, frontier = set(), [node_id]
        result = []
        for _ in range(depth):
            next_frontier = []
            for nid in frontier:
                for edge in self.index.get(nid, []):
                    if edge.target not in visited:
                        visited.add(edge.target)
                        next_frontier.append(edge.target)
                        if edge.target in self.nodes:
                            result.append(self.nodes[edge.target])
            frontier = next_frontier
        return result

    def graph_rag_retrieve(self, query_entities: List[str], depth: int = 2) -> List[KGNode]:
        results, seen = [], set()
        for entity in query_entities:
            for node in self.neighbors(entity, depth):
                if node.id not in seen:
                    seen.add(node.id)
                    results.append(node)
        return results

    def ingest_predicate(self, pred):
        for arg in pred.arguments:
            if arg not in self.nodes:
                self.add_node(KGNode(id=arg, label=arg))
        if len(pred.arguments) >= 2:
            self.add_edge(KGEdge(
                source=pred.arguments[0],
                target=pred.arguments[1],
                relation=pred.functor,
                weight=pred.confidence
            ))

    def export_json(self) -> str:
        return json.dumps({
            "nodes": [{"id": n.id, "label": n.label} for n in self.nodes.values()],
            "edges": [{"src": e.source, "tgt": e.target, "rel": e.relation} for e in self.edges]
        }, indent=2)
