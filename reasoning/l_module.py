# reasoning/l_module.py
import torch
import torch.nn as nn
from typing import Tuple

class LModule(nn.Module):
    """
    Low-level fast-cycle recurrent reasoner.
    Runs T times per H-module step.
    """
    def __init__(self, hidden_dim: int = 512, input_dim: int = 384):
        super().__init__()
        self.rnn = nn.GRUCell(input_size=input_dim + hidden_dim, hidden_size=hidden_dim)
        self.output_head = nn.Linear(hidden_dim, input_dim)
        self.hidden_dim = hidden_dim

    def forward(
        self,
        x: torch.Tensor,
        h_l: torch.Tensor,
        z_h: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        fused = torch.cat([x, z_h], dim=-1)
        h_l_new = self.rnn(fused, h_l)
        output = self.output_head(h_l_new)
        return output, h_l_new
