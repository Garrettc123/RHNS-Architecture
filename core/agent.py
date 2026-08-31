# core/agent.py
"""
RHNS Agent — single-sweep orchestrator.
Wires all 10 layers in sequence:
  Perception -> Parser -> Verifier -> KG -> MemoryController
  -> HRMReasoner -> LATS -> MetacognitiveExecutive -> Decoder -> AuditLedger
"""
import torch
from perception.encoder import PerceptionEncoder
from symbolic.parser import NeuralSymbolicParser
from symbolic.verifier import SymbolicVerifier
from symbolic.knowledge_graph import KnowledgeGraph
from memory.controller import MemoryController
from reasoning.h_module import HRMReasoner
from reasoning.lats import LATS, TreeNode
from metacognition.executive import MetacognitiveExecutive
from generation.decoder import GenerationDecoder
from audit.ledger import AuditLedger
from typing import Dict, Any

class RHNSAgent:
    def __init__(
        self,
        hrm_hidden: int = 512,
        hrm_input: int = 384,
        hrm_T: int = 4,
        lats_budget: int = 20,
        vocab_size: int = 32000
    ):
        self.encoder  = PerceptionEncoder()
        self.parser   = NeuralSymbolicParser()
        self.verifier = SymbolicVerifier()
        self.kg       = KnowledgeGraph()
        self.memory   = MemoryController()
        self.hrm      = HRMReasoner(hidden_dim=hrm_hidden, input_dim=hrm_input, T=hrm_T)
        self.decoder  = GenerationDecoder(hidden_dim=hrm_hidden, vocab_size=vocab_size)
        self.meta     = MetacognitiveExecutive(self.verifier)
        self.ledger   = AuditLedger()
        self.lats = LATS(
            generator=lambda s: [s + " [expand A]", s + " [expand B]", s + " [expand C]"],
            critic=lambda s: 0.5 + len(s) % 3 * 0.1,
            budget=lats_budget
        )

    def run(self, text: str) -> Dict[str, Any]:
        """Full single-sweep forward pass through all 10 layers."""

        # Layer 1: Perception
        token = self.encoder.encode(text)
        self.ledger.record("perception", "encode", {"confidence": token.confidence})

        # Layer 2: Symbolic Parsing
        predicates = self.parser.parse(text)
        self.ledger.record("parser", "parse", {"n_predicates": len(predicates)})

        # Layer 3: Symbolic Verification + Forward Chaining
        self.verifier.load(predicates)
        derived = self.verifier.forward_chain()
        all_predicates = predicates + derived
        self.ledger.record("verifier", "forward_chain", {"derived": len(derived)})

        # Layer 4: Knowledge Graph Ingestion
        for pred in all_predicates:
            self.kg.ingest_predicate(pred)
        self.ledger.record("knowledge_graph", "ingest", {"nodes": len(self.kg.nodes)})

        # Layer 5: Memory
        self.memory.observe(token, relevance=token.confidence)
        self.memory.consolidate(all_predicates)
        self.ledger.record("memory", "consolidate", {"predicates": len(all_predicates)})

        # Layer 6: HRM Reasoning
        x = token.embedding.unsqueeze(0)  # [1, input_dim]
        out, z_h, hrm_confidence = self.hrm(x, steps=1)
        self.ledger.record("hrm", "forward", {"confidence": hrm_confidence})

        # Layer 7: LATS Tree Search
        best_node = self.lats.search(root_state=text)
        self.ledger.record("lats", "search", {"best_state": best_node.state[:60]})

        # Layer 8: Metacognitive Gate
        meta_state = self.meta.evaluate(all_predicates, hrm_confidence)
        self.ledger.record("meta", "evaluate", {"decision": meta_state.decision})

        # Layer 9: Generation
        logits = self.decoder(z_h)
        top_tokens = torch.topk(logits, 5, dim=-1).indices.squeeze().tolist()
        self.ledger.record("decoder", "generate", {"top_tokens": top_tokens})

        # Layer 10: Audit Chain Verification
        chain_valid = self.ledger.verify_chain()
        self.ledger.record("audit", "verify_chain", {"valid": chain_valid})

        return {
            "input": text,
            "perceptual_confidence": token.confidence,
            "predicates": len(all_predicates),
            "kg_nodes": len(self.kg.nodes),
            "hrm_confidence": hrm_confidence,
            "lats_best": best_node.state,
            "meta_decision": meta_state.decision,
            "top_token_ids": top_tokens,
            "chain_valid": chain_valid,
            "audit_log": self.ledger.export_json()
        }
