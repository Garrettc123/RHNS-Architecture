"""Invariants for module initialization and tamper evidence."""

import pytest
import torch

from audit.ledger import AuditLedger
from core.agent import RHNSAgent
from memory.episodic import EpisodicMemory
from perception.encoder import PerceptionEncoder
from reasoning.h_module import HRMReasoner


def test_encoder_constructs_without_downloading():
    encoder = PerceptionEncoder(model_name="missing-model", local_files_only=True)
    assert encoder.model is None
    assert encoder.tokenizer is None


def test_agent_constructs_without_downloading():
    agent = RHNSAgent(hrm_hidden=32, hrm_input=32, hrm_T=1, vocab_size=16)
    assert agent.encoder.model is None


def test_hrm_rejects_invalid_bounds_and_shapes():
    with pytest.raises(ValueError):
        HRMReasoner(T=0)
    hrm = HRMReasoner(hidden_dim=16, input_dim=8)
    with pytest.raises(ValueError):
        hrm(torch.ones(1, 8), steps=0)
    with pytest.raises(ValueError):
        hrm(torch.ones(1, 7))


def test_hrm_supports_batched_forward():
    hrm = HRMReasoner(hidden_dim=16, input_dim=8, T=2)
    out, strategic, confidence = hrm(torch.ones(2, 8))
    assert out.shape == (2, 8)
    assert strategic.shape == (2, 16)
    assert 0 <= confidence <= 1


def test_episodic_ids_unique_and_zero_recall_empty():
    episodes = EpisodicMemory()
    left = episodes.record("a", "obs", "ok")
    right = episodes.record("a", "obs", "ok")
    assert left.episode_id != right.episode_id
    assert episodes.recall_recent(0) == []


def test_ledger_detects_index_and_payload_tampering():
    ledger = AuditLedger()
    ledger.record("agent", "read", {"items": [1]})
    assert ledger.verify_chain()
    ledger.entries[0].payload["items"].append(2)
    assert not ledger.verify_chain()
    ledger.entries[0].payload["items"].pop()
    ledger.entries[0].index = 4
    assert not ledger.verify_chain()


def test_ledger_export_has_verifiable_full_hashes():
    ledger = AuditLedger()
    entry = ledger.record("agent", "read", {"ok": True})
    exported = ledger.export_json()
    assert entry.hash in exported
    assert entry.prev_hash in exported
