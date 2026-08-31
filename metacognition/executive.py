# metacognition/executive.py
from dataclasses import dataclass
from typing import List
from symbolic.verifier import SymbolicVerifier
from symbolic.parser import MRLPredicate

@dataclass
class MetaState:
    confidence: float = 1.0
    contradiction_count: int = 0
    stall_count: int = 0
    cycle: int = 0
    decision: str = "continue"  # 'continue' | 'escalate' | 'commit' | 'abort'

class MetacognitiveExecutive:
    """
    Monitors reasoning quality, detects stalls and contradictions,
    gates convergence, escalates to H-module when needed.
    """
    CONFIDENCE_THRESHOLD = 0.72
    STALL_LIMIT = 3
    CONTRADICTION_LIMIT = 2

    def __init__(self, verifier: SymbolicVerifier):
        self.verifier = verifier
        self.state = MetaState()
        self.history: List[float] = []

    def evaluate(
        self,
        new_predicates: List[MRLPredicate],
        hrm_confidence: float
    ) -> MetaState:
        self.state.cycle += 1
        self.state.confidence = hrm_confidence
        self.history.append(hrm_confidence)

        if len(self.history) >= 3:
            delta = self.history[-1] - self.history[-3]
            if abs(delta) < 0.01:
                self.state.stall_count += 1
            else:
                self.state.stall_count = 0

        for pred in new_predicates:
            valid, _ = self.verifier.verify(pred)
            if not valid:
                self.state.contradiction_count += 1

        if self.state.contradiction_count >= self.CONTRADICTION_LIMIT:
            self.state.decision = "abort"
        elif self.state.stall_count >= self.STALL_LIMIT:
            self.state.decision = "escalate"
        elif hrm_confidence >= self.CONFIDENCE_THRESHOLD:
            self.state.decision = "commit"
        else:
            self.state.decision = "continue"

        return self.state

    def reset(self):
        self.state = MetaState()
        self.history.clear()
