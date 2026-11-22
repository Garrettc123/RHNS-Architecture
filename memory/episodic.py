"""In-memory episode history (not persistent storage)."""

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Episode:
    episode_id: str
    timestamp: float
    action: str
    observation: str
    outcome: str
    metadata: Dict = field(default_factory=dict)


class EpisodicMemory:
    def __init__(self):
        self.log: List[Episode] = []

    def record(self, action: str, observation: str, outcome: str, metadata: Dict = None) -> Episode:
        ep = Episode(
            episode_id=f"ep_{uuid.uuid4().hex}",
            timestamp=time.time(),
            action=action,
            observation=observation,
            outcome=outcome,
            metadata=metadata or {},
        )
        self.log.append(ep)
        return ep

    def recall_recent(self, n: int = 10) -> List[Episode]:
        if type(n) is not int or n < 0:
            raise ValueError("n must be a non-negative integer")
        return self.log[-n:] if n else []

    def recall_by_outcome(self, outcome_keyword: str) -> List[Episode]:
        return [e for e in self.log if outcome_keyword.lower() in e.outcome.lower()]

    def export(self) -> str:
        return json.dumps([e.__dict__ for e in self.log], indent=2)
