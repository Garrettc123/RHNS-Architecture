# memory/controller.py
from memory.working import WorkingMemory
from memory.episodic import EpisodicMemory
from symbolic.knowledge_graph import KnowledgeGraph
from symbolic.parser import MRLPredicate
from typing import Any, List

class MemoryController:
    """
    MemGPT-style tiered memory controller.
    Governs promotion, eviction, and consolidation across all memory tiers.
    """
    def __init__(self):
        self.working = WorkingMemory(capacity=16)
        self.episodic = EpisodicMemory()
        self.semantic = KnowledgeGraph()

    def observe(self, content: Any, relevance: float = 1.0, source: str = "input"):
        self.working.push(content, relevance=relevance, source=source)
        evicted = self.working.flush_cold(threshold=0.25)
        for slot in evicted:
            self.episodic.record(
                action="evict_from_working",
                observation=str(slot.content),
                outcome="archived",
                metadata={"source": slot.source, "relevance": slot.relevance}
            )

    def consolidate(self, predicates: List[MRLPredicate]):
        for pred in predicates:
            self.semantic.ingest_predicate(pred)

    def working_context(self) -> str:
        slots = self.working.peek(8)
        return "\n".join([str(s.content) for s in slots])

    def retrieve_relevant(self, entities: List[str]) -> str:
        nodes = self.semantic.graph_rag_retrieve(entities, depth=2)
        return "\n".join([f"{n.id}: {n.properties}" for n in nodes])
