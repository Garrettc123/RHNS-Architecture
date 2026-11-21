"""Lazy, fail-closed text encoder.

Model files are loaded on the first encode call, rather than at agent
construction. By default the model must already be cached on disk.
"""

from dataclasses import dataclass

import torch


@dataclass
class PerceptualToken:
    raw: str
    embedding: torch.Tensor
    modality: str
    confidence: float


class PerceptionEncoder:
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        local_files_only: bool = True,
    ):
        self.model_name = model_name
        self.local_files_only = local_files_only
        self.tokenizer = None
        self.model = None

    def _load(self):
        if self.model is not None:
            return
        from transformers import AutoModel, AutoTokenizer

        try:
            tokenizer = AutoTokenizer.from_pretrained(
                self.model_name, local_files_only=self.local_files_only
            )
            model = AutoModel.from_pretrained(
                self.model_name, local_files_only=self.local_files_only
            )
        except (OSError, ValueError) as exc:
            raise RuntimeError(
                f"RHNS encoder {self.model_name!r} is not available locally. "
                "Provision the reviewed model artifacts before neural execution."
            ) from exc
        model.eval()
        self.tokenizer = tokenizer
        self.model = model

    @torch.no_grad()
    def encode(self, text: str) -> PerceptualToken:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")
        self._load()
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        output = self.model(**inputs).last_hidden_state
        mask = inputs["attention_mask"].unsqueeze(-1).to(output.dtype)
        pooled = (output * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
        embedding = pooled.squeeze(0)
        # A vector norm is a signal magnitude, not a calibrated probability.
        return PerceptualToken(
            raw=text,
            embedding=embedding,
            modality="text",
            confidence=float(embedding.norm().item()),
        )
