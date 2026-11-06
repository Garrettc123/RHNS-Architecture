"""Dependency-explicit RHNS runtime. No fabricated search fallback."""
from pathlib import Path
from typing import Any, Dict
from metacognition.gate import GenerationBlocked, guarded_generate

class RuntimeUnavailable(RuntimeError):
    pass

class RHNSAgent:
    def __init__(self, *, generator=None, critic=None, hrm_checkpoint=None,
                 decoder_checkpoint=None, hrm_hidden=512, hrm_input=384,
                 hrm_T=4, lats_budget=20, vocab_size=32000):
        if not callable(generator) or not callable(critic):
            raise RuntimeUnavailable("Real search generator and critic are required")
        for checkpoint in (hrm_checkpoint, decoder_checkpoint):
            if not checkpoint or not Path(checkpoint).is_file():
                raise RuntimeUnavailable("HRM and decoder checkpoint files are required")
        import torch
        from perception.encoder import PerceptionEncoder
        from symbolic.parser import NeuralSymbolicParser
        from symbolic.verifier import SymbolicVerifier
        from symbolic.knowledge_graph import KnowledgeGraph
        from memory.controller import MemoryController
        from reasoning.h_module import HRMReasoner
        from reasoning.lats import LATS
        from metacognition.executive import MetacognitiveExecutive
        from generation.decoder import GenerationDecoder
        from audit.ledger import AuditLedger
        self.torch = torch
        self.ledger_type = AuditLedger
        self.encoder = PerceptionEncoder()
        self.parser = NeuralSymbolicParser()
        self.verifier = SymbolicVerifier()
        self.kg = KnowledgeGraph()
        self.memory = MemoryController()
        self.hrm = HRMReasoner(hidden_dim=hrm_hidden, input_dim=hrm_input, T=hrm_T)
        self.decoder = GenerationDecoder(hidden_dim=hrm_hidden, vocab_size=vocab_size)
        self.hrm.load_state_dict(torch.load(hrm_checkpoint, map_location="cpu", weights_only=True), strict=True)
        self.decoder.load_state_dict(torch.load(decoder_checkpoint, map_location="cpu", weights_only=True), strict=True)
        self.hrm.eval()
        self.decoder.eval()
        self.meta = MetacognitiveExecutive(self.verifier)
        self.lats = LATS(generator=generator, critic=critic, budget=lats_budget)

    def run(self, text: str) -> Dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("A nonempty goal is required")
        self.meta.reset()
        ledger = self.ledger_type()
        token = self.encoder.encode(text)
        predicates = self.parser.parse(text)
        self.verifier.load(predicates)
        predicates += self.verifier.forward_chain()
        with self.torch.no_grad():
            _, z_h, confidence = self.hrm(token.embedding.unsqueeze(0), steps=1)
        best = self.lats.search(root_state=text)
        state = self.meta.evaluate(predicates, confidence)
        ledger.record("meta", "evaluate", {"decision": state.decision})
        tokens = []
        try:
            with self.torch.no_grad():
                logits = guarded_generate(state.decision, lambda: self.decoder(z_h))
                tokens = self.torch.topk(logits, 5, dim=-1).indices.squeeze().tolist()
        except GenerationBlocked:
            status = "blocked"
            ledger.record("decoder", "blocked", {"decision": state.decision})
        else:
            status = "generated_unverified"
            ledger.record("decoder", "generated", {"top_token_ids": tokens})
        ledger.record("audit", "finalize", {"status": status})
        valid = ledger.verify_chain()
        if not valid:
            status, tokens = "audit_failed", []
        # Generated hypotheses are not automatically promoted to factual memory.
        return {"input": text, "status": status, "meta_decision": state.decision,
                "hrm_confidence": confidence, "lats_best": best.state,
                "top_token_ids": tokens, "chain_valid": valid,
                "audit_log": ledger.export_json(), "production_ready": False}
