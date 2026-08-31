# generation/decoder.py
import torch
import torch.nn as nn
from typing import List

class GenerationDecoder(nn.Module):
    """
    Lightweight projection decoder: maps HRM strategic state z_h
    back to a token-probability distribution over a small vocab.
    In production, replace the linear head with a language model
    (e.g. GPT-2 / Llama) that conditions on z_h as a prefix embedding.
    """
    def __init__(self, hidden_dim: int = 512, vocab_size: int = 32000):
        super().__init__()
        self.proj = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim * 2),
            nn.GELU(),
            nn.Linear(hidden_dim * 2, vocab_size)
        )

    def forward(self, z_h: torch.Tensor) -> torch.Tensor:
        """Returns logits [batch, vocab_size]."""
        return self.proj(z_h)

    def decode_text(self, z_h: torch.Tensor, id2token: List[str], top_k: int = 5) -> List[List[str]]:
        """Greedy top-k token labels (for debugging / audit)."""
        logits = self.forward(z_h)
        probs = torch.softmax(logits, dim=-1)
        top = torch.topk(probs, top_k, dim=-1)
        results = []
        for row in top.indices:
            results.append([id2token[i] for i in row.tolist() if i < len(id2token)])
        return results
