# perception/encoder.py
import torch
from transformers import AutoTokenizer, AutoModel
from dataclasses import dataclass

@dataclass
class PerceptualToken:
    raw: str
    embedding: torch.Tensor
    modality: str
    confidence: float

class PerceptionEncoder:
    def __init__(self, model_name="sentence-transformers/all-MiniLM-L6-v2"):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.model.eval()

    @torch.no_grad()
    def encode(self, text: str) -> PerceptualToken:
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        out = self.model(**inputs)
        emb = out.last_hidden_state.mean(dim=1).squeeze()
        return PerceptualToken(
            raw=text,
            embedding=emb,
            modality="text",
            confidence=float(emb.norm().item())
        )
