"""RHNS experimental neural/symbolic single-sweep agent.

Constructs without network access. The neural encoder requires approved local
model artifacts, and the HRM/decoder heads require trained weights before
any output can be interpreted as a validated operational decision.
"""

from typing import Any

import torch

from audit.ledger import AuditLedger
from generation.decoder import GenerationDecoder
from memory.controller import MemoryController
from metacognition.executive import MetacognitiveExecutive
from perception.encoder import PerceptionEncoder
from reasoning.h_module import HRMReasoner
from reasoning.lats import LATS
from symbolic.knowledge_graph import KnowledgeGraph
from symbolic.parser import NeuralSymbolicParser
from symbolic.verifier import SymbolicVerifier


class RHNSAgent:
    def __init__(
        self,
        hrm_hidden: int = 512,
        hrm_input: int = 384,
        hrm_T: int = 4,
        lats_budget: int = 20,
        vocab_size: int = 32000,
    ):
        self.encoder = PerceptionEncoder()
        self.parser = NeuralSymbolicParser()
        self.verifier = SymbolicVerifier()
        self.kg = KnowledgeGraph()
        self.memory = MemoryController()
        self.hrm = HRMReasoner(hidden_dim=hrm_hidden, input_dim=hrm_input, T=hrm_T)
        self.decoder = GenerationDecoder(hidden_dim=hrm_hidden, vocab_size=vocab_size)
        self.meta = MetacognitiveExecutive(self.verifier)
        self.ledger = AuditLedger()
        self.lats = LATS(
            generator=lambda s: [s + " [expand A]", s + " [expand B]", s + " [expand C]"],
            critic=lambda s: 0.5 + len(s) % 3 * 0.1,
            budget=lats_budget,
        )

    @torch.no_grad()
    def run(self, text: str) -> dict[str, Any]:
        """Experimental local forward pass; no external authorization or execution."""
        token = self.encoder.encode(text)
        self.ledger.record("perception", "encode", {"signal_magnitude": token.confidence})

        predicates = self.parser.parse(text)
        self.ledger.record("parser", "parse", {"n_predicates": len(predicates)})

        self.verifier.load(predicates)
        derived = self.verifier.forward_chain()
        all_predicates = predicates + derived
        self.ledger.record("verifier", "forward_chain", {"derived": len(derived)})

        for pred in all_predicates:
            self.kg.ingest_predicate(pred)
        self.ledger.record("knowledge_graph", "ingest", {"nodes": len(self.kg.nodes)})

        self.memory.observe(token, relevance=token.confidence)
        self.memory.consolidate(all_predicates)
        self.ledger.record("memory", "consolidate", {"predicates": len(all_predicates)})

        vector = token.embedding.unsqueeze(0)
        if vector.shape[-1] != self.hrm.input_dim:
            raise ValueError(
                f"encoder dimension {vector.shape[-1]} does not match HRM input "
                f"dimension {self.hrm.input_dim}"
            )
        output, z_h, hrm_confidence = self.hrm(vector, steps=1)
        self.ledger.record("hrm", "forward", {"diagnostic_signal": hrm_confidence})

        best_node = self.lats.search(root_state=text)
        self.ledger.record("lats", "search", {"best_state": best_node.state[:60]})

        meta_state = self.meta.evaluate(all_predicates, hrm_confidence)
        self.ledger.record("meta", "evaluate", {"decision": meta_state.decision})

        logits = self.decoder(z_h)
        count = min(5, logits.shape[-1])
        top_tokens = torch.topk(logits, count, dim=-1).indices.squeeze(0).tolist()
        self.ledger.record("decoder", "generate", {"top_tokens": top_tokens})

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
            "audit_log": self.ledger.export_json(),
            "execution_mode": "experimental_no_external_actions",
            "trained_model_verified": False,
        }
