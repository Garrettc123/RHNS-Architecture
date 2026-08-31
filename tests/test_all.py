# tests/test_all.py
import pytest
import torch

# ── Symbolic ──────────────────────────────────────────────────────────────────
from symbolic.parser import NeuralSymbolicParser, MRLPredicate
from symbolic.verifier import SymbolicVerifier
from symbolic.knowledge_graph import KnowledgeGraph, KGNode, KGEdge

def test_parser_extracts_predicates():
    parser = NeuralSymbolicParser()
    preds = parser.parse("A is a B")
    assert any(p.functor == "is_a" for p in preds)

def test_parser_no_match():
    parser = NeuralSymbolicParser()
    assert parser.parse("hello world") == []

def test_verifier_ok():
    v = SymbolicVerifier()
    p = MRLPredicate(functor="is_a", arguments=["dog", "animal"], confidence=0.9, source="test")
    ok, _ = v.verify(p)
    assert ok

def test_verifier_contradiction():
    v = SymbolicVerifier()
    contra = MRLPredicate(functor="contradicts", arguments=["x", "y"], confidence=1.0, source="test")
    v.load([contra])
    target = MRLPredicate(functor="implies", arguments=["x", "y"], confidence=0.8, source="test")
    ok, _ = v.verify(target)
    assert not ok

def test_kg_neighbors():
    kg = KnowledgeGraph()
    kg.add_node(KGNode(id="A", label="A"))
    kg.add_node(KGNode(id="B", label="B"))
    kg.add_edge(KGEdge(source="A", target="B", relation="is_a"))
    neighbors = kg.neighbors("A", depth=1)
    assert any(n.id == "B" for n in neighbors)

def test_kg_graph_rag():
    kg = KnowledgeGraph()
    p = MRLPredicate(functor="causes", arguments=["fire", "smoke"], confidence=0.9, source="test")
    kg.ingest_predicate(p)
    results = kg.graph_rag_retrieve(["fire"], depth=1)
    assert any(n.id == "smoke" for n in results)

# ── Memory ────────────────────────────────────────────────────────────────────
from memory.working import WorkingMemory
from memory.episodic import EpisodicMemory
from memory.controller import MemoryController

def test_working_memory_capacity():
    wm = WorkingMemory(capacity=4)
    for i in range(6):
        wm.push(f"item_{i}")
    assert len(wm.slots) <= 4

def test_working_memory_flush_cold():
    wm = WorkingMemory(capacity=8)
    wm.push("hot", relevance=0.9)
    wm.push("cold", relevance=0.1)
    evicted = wm.flush_cold(threshold=0.25)
    assert any("cold" in str(s.content) for s in evicted)

def test_episodic_record_and_recall():
    em = EpisodicMemory()
    em.record("test_action", "observation", "success")
    recent = em.recall_recent(1)
    assert recent[0].action == "test_action"

def test_episodic_recall_by_outcome():
    em = EpisodicMemory()
    em.record("a", "b", "success")
    em.record("c", "d", "failure")
    successes = em.recall_by_outcome("success")
    assert len(successes) == 1

def test_memory_controller_consolidate():
    mc = MemoryController()
    p = MRLPredicate(functor="is_a", arguments=["cat", "animal"], confidence=0.9, source="test")
    mc.consolidate([p])
    assert "cat" in mc.semantic.nodes

# ── Reasoning ─────────────────────────────────────────────────────────────────
from reasoning.l_module import LModule
from reasoning.h_module import HModule, HRMReasoner
from reasoning.lats import LATS, TreeNode

def test_l_module_output_shape():
    l = LModule(hidden_dim=64, input_dim=32)
    x = torch.randn(1, 32)
    h_l = torch.zeros(1, 64)
    z_h = torch.zeros(1, 64)
    out, h_new = l(x, h_l, z_h)
    assert out.shape == (1, 32)
    assert h_new.shape == (1, 64)

def test_hrm_forward():
    hrm = HRMReasoner(hidden_dim=64, input_dim=32, T=2)
    x = torch.randn(1, 32)
    out, z_h, conf = hrm(x, steps=1)
    assert out.shape == (1, 32)
    assert 0.0 <= conf <= 1.0

def test_lats_search_returns_node():
    lats = LATS(
        generator=lambda s: [s + "_A", s + "_B"],
        critic=lambda s: len(s) * 0.01,
        budget=5
    )
    result = lats.search("root")
    assert isinstance(result, TreeNode)
    assert result.state != ""

def test_lats_ucb_unexplored_infinity():
    node = TreeNode(state="test", visits=0)
    assert node.ucb() == float("inf")

# ── Metacognition ─────────────────────────────────────────────────────────────
from metacognition.executive import MetacognitiveExecutive

def test_meta_commit_on_high_confidence():
    v = SymbolicVerifier()
    meta = MetacognitiveExecutive(v)
    state = meta.evaluate([], hrm_confidence=0.95)
    assert state.decision == "commit"

def test_meta_abort_on_contradictions():
    v = SymbolicVerifier()
    contra = MRLPredicate(functor="contradicts", arguments=["a", "b"], confidence=1.0, source="test")
    v.load([contra])
    meta = MetacognitiveExecutive(v)
    bad_pred = MRLPredicate(functor="implies", arguments=["a", "b"], confidence=0.8, source="test")
    meta.evaluate([bad_pred], 0.5)
    meta.evaluate([bad_pred], 0.5)
    assert meta.state.decision == "abort"

# ── Audit ─────────────────────────────────────────────────────────────────────
from audit.ledger import AuditLedger

def test_ledger_chain_valid():
    ledger = AuditLedger()
    ledger.record("module_A", "event_1", {"x": 1})
    ledger.record("module_B", "event_2", {"y": 2})
    assert ledger.verify_chain()

def test_ledger_chain_tamper_detection():
    ledger = AuditLedger()
    ledger.record("mod", "ev", {})
    ledger.entries[0].hash = "tampered"
    assert not ledger.verify_chain()

def test_ledger_export_json():
    ledger = AuditLedger()
    ledger.record("mod", "ev", "payload")
    out = ledger.export_json()
    assert "mod" in out

# ── Generation ────────────────────────────────────────────────────────────────
from generation.decoder import GenerationDecoder

def test_decoder_output_shape():
    dec = GenerationDecoder(hidden_dim=64, vocab_size=100)
    z_h = torch.randn(1, 64)
    logits = dec(z_h)
    assert logits.shape == (1, 100)

# ── Integration ───────────────────────────────────────────────────────────────
from core.agent import RHNSAgent

def test_agent_single_sweep():
    agent = RHNSAgent(hrm_hidden=64, hrm_input=32, hrm_T=2, lats_budget=5, vocab_size=100)
    import types
    from perception.encoder import PerceptualToken

    def mock_encode(self, text):
        emb = torch.randn(32)
        return PerceptualToken(raw=text, embedding=emb, modality="text", confidence=float(emb.norm()))

    agent.encoder.encode = types.MethodType(mock_encode, agent.encoder)
    result = agent.run("fire causes smoke")
    assert result["chain_valid"] is True
    assert result["predicates"] >= 1
    assert result["meta_decision"] in {"continue", "commit", "escalate", "abort"}
