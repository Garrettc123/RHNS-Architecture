# reasoning/h_module.py
import torch
import torch.nn as nn
from typing import Tuple
from reasoning.l_module import LModule

class HModule(nn.Module):
    """
    High-level slow-cycle strategic planner.
    Updates every T L-module steps.
    """
    def __init__(self, hidden_dim: int = 512):
        super().__init__()
        self.rnn = nn.GRUCell(input_size=hidden_dim, hidden_size=hidden_dim)
        self.plan_head = nn.Linear(hidden_dim, hidden_dim)
        self.confidence_head = nn.Linear(hidden_dim, 1)

    def forward(
        self,
        h_l_summary: torch.Tensor,
        z_h: torch.Tensor
    ) -> Tuple[torch.Tensor, float]:
        z_h_new = self.rnn(h_l_summary, z_h)
        plan = self.plan_head(z_h_new)
        confidence = torch.sigmoid(self.confidence_head(z_h_new)).item()
        return plan, confidence

class HRMReasoner(nn.Module):
    """Full HRM: T L-cycles per H-cycle, with convergence gate."""
    def __init__(self, hidden_dim: int = 512, input_dim: int = 384, T: int = 4):
        super().__init__()
        self.l = LModule(hidden_dim=hidden_dim, input_dim=input_dim)
        self.h = HModule(hidden_dim=hidden_dim)
        self.T = T
        self.hidden_dim = hidden_dim

    def forward(self, x: torch.Tensor, steps: int = 1):
        batch = x.size(0)
        h_l = torch.zeros(batch, self.hidden_dim)
        z_h = torch.zeros(batch, self.hidden_dim)
        outputs = []
        for _ in range(steps):
            for _ in range(self.T):
                out, h_l = self.l(x, h_l, z_h)
                outputs.append(out)
            z_h, confidence = self.h(h_l, z_h)
        return outputs[-1], z_h, confidence
