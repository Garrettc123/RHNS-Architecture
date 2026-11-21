"""Two-timescale recurrent reasoning prototype."""

import torch
import torch.nn as nn

from reasoning.l_module import LModule


class HModule(nn.Module):
    """High-level recurrence: update once per T low-level cycles."""

    def __init__(self, hidden_dim: int = 512):
        super().__init__()
        self.rnn = nn.GRUCell(input_size=hidden_dim, hidden_size=hidden_dim)
        self.plan_head = nn.Linear(hidden_dim, hidden_dim)
        self.confidence_head = nn.Linear(hidden_dim, 1)

    def forward(self, h_l_summary: torch.Tensor, z_h: torch.Tensor):
        z_h_new = self.rnn(h_l_summary, z_h)
        plan = self.plan_head(z_h_new)
        # A pooled diagnostic signal, not a calibrated confidence score.
        confidence = torch.sigmoid(self.confidence_head(z_h_new)).mean().item()
        return plan, confidence


class HRMReasoner(nn.Module):
    """Full HRM prototype with bounded iteration counts."""

    def __init__(self, hidden_dim: int = 512, input_dim: int = 384, T: int = 4):
        super().__init__()
        for name, value in (("hidden_dim", hidden_dim), ("input_dim", input_dim), ("T", T)):
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        self.l = LModule(hidden_dim=hidden_dim, input_dim=input_dim)
        self.h = HModule(hidden_dim=hidden_dim)
        self.T = T
        self.hidden_dim = hidden_dim
        self.input_dim = input_dim

    def forward(self, x: torch.Tensor, steps: int = 1):
        if type(steps) is not int or not 1 <= steps <= 100:
            raise ValueError("steps must be an integer between 1 and 100")
        if x.ndim != 2 or x.shape[1] != self.input_dim or x.shape[0] < 1:
            raise ValueError(f"expected x shape [batch, {self.input_dim}]")
        batch = x.size(0)
        h_l = x.new_zeros(batch, self.hidden_dim)
        z_h = x.new_zeros(batch, self.hidden_dim)
        confidence = 0.0
        output = x
        for _ in range(steps):
            for _ in range(self.T):
                output, h_l = self.l(x, h_l, z_h)
            z_h, confidence = self.h(h_l, z_h)
        return output, z_h, confidence
