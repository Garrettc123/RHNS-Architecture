# core/agent.py
"""
RHNS Agent — single-sweep orchestrator.
The LATS search accepts only structured plans that pass the symbolic plan gate.
"""
import json
import torch
from perception.encoder import PerceptionEncoder
from symbolic.parser import NeuralSymbolicParser
from symbolic.verifier import SymbolicVerifier
from symbolic.plan_verifier import verify_plan
from symbolic.knowledge_graph import KnowledgeGraph
from memory.controller import MemoryController
from reasoning.h_module import HRMReasoner
from reasoning.lats import LATS
from metacognition.executive import MetacognitiveExecutive
from generation.decoder import GenerationDecoder
from audit.ledger import AuditLedger
from typing import Dict, Any


def _validate_lats_candidate(candidate: str) -> bool:
    """Accept only JSON plan candidates approved by the deterministic policy gate."""
    try:
        plan = json.loads(candidate)
    except (TypeError, ValueError):
        return False
    return verify_plan(plan).approved


class RHNSAgent:
    def __init__(
        self,
        hrm_hidden: int = 512,
        hrm_input: int = 384,
        hrm_T: int = 4,
        lats_budget: int = 20,
        vocab_size: int = 32000
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
            generator=lambda state: [
                json.dumps({
                    "goal": state,
                    "actions": [{
                        "action_id": f"candidate-{index}",
                        "operation": "propose",
                        "target": f"{state} [candidate {index}]",
                    }],
                })
                for index in ("A", "B", "C")
            ],
            critic=lambda state: 0.5 + len(state) % 3 * 0.1,
            budget=lats_budget,
            validator=_validate_lats_candidate,
        )

    def run(self, text: str) -> Dict[str, Any]:
        """Full single-sweep forward pass through the RHNS layers."""
        token = self.encoder.encode(text)
        self.ledger.record("perception", "encode", {"confidence": token.confidence})

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

        x = token.embedding.unsqueeze(0)
        _, z_h, hrm_confidence = self.hrm(x, steps=1)
        self.ledger.record("hrm", "forward", {"confidence": hrm_confidence})

        best_node = self.lats.search(root_state=text)
        self.ledger.record(
            "lats", "search",
            {
                "best_state": best_node.state[:160],
                "rejected_candidates": self.lats.rejected_candidates,
                "candidate_gate": "symbolic_plan_verifier",
            },
        )

        meta_state = self.meta.evaluate(all_predicates, hrm_confidence)
        self.ledger.record("meta", "evaluate", {"decision": meta_state.decision})

        logits = self.decoder(z_h)
        top_tokens = torch.topk(logits, 5, dim=-1).indices.squeeze().tolist()
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
            "lats_rejected_candidates": self.lats.rejected_candidates,
            "meta_decision": meta_state.decision,
            "top_token_ids": top_tokens,
            "chain_valid": chain_valid,
            "audit_log": self.ledger.export_json(),
        }
