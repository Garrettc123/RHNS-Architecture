# memory/episodic.py
import json
import time
from typing import List, Dict
from dataclasses import dataclass, field

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
            episode_id=f"ep_{int(time.time()*1000)}",
            timestamp=time.time(),
            action=action,
            observation=observation,
            outcome=outcome,
            metadata=metadata or {}
        )
        self.log.append(ep)
        return ep

    def recall_recent(self, n: int = 10) -> List[Episode]:
        return self.log[-n:]

    def recall_by_outcome(self, outcome_keyword: str) -> List[Episode]:
        return [e for e in self.log if outcome_keyword.lower() in e.outcome.lower()]

    def export(self) -> str:
        return json.dumps([e.__dict__ for e in self.log], indent=2)
