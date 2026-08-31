# memory/working.py
from collections import deque
from typing import Any, List
from dataclasses import dataclass
import time

@dataclass
class WorkingMemorySlot:
    content: Any
    timestamp: float
    relevance: float
    source: str

class WorkingMemory:
    def __init__(self, capacity: int = 16):
        self.capacity = capacity
        self.slots: deque = deque(maxlen=capacity)

    def push(self, content: Any, relevance: float = 1.0, source: str = "input"):
        self.slots.append(WorkingMemorySlot(
            content=content,
            timestamp=time.time(),
            relevance=relevance,
            source=source
        ))

    def peek(self, n: int = 8) -> List[WorkingMemorySlot]:
        return list(self.slots)[-n:]

    def flush_cold(self, threshold: float = 0.3) -> List[WorkingMemorySlot]:
        cold = [s for s in self.slots if s.relevance < threshold]
        self.slots = deque(
            [s for s in self.slots if s.relevance >= threshold],
            maxlen=self.capacity
        )
        return cold
