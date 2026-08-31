# symbolic/parser.py
import re
from dataclasses import dataclass, field
from typing import List

@dataclass
class MRLPredicate:
    functor: str
    arguments: List[str]
    confidence: float
    source: str  # 'perception' | 'memory' | 'inference'

class NeuralSymbolicParser:
    PATTERNS = [
        (r"(\w+) is a (\w+)",           "is_a"),
        (r"(\w+) causes (\w+)",         "causes"),
        (r"(\w+) has property (\w+)",   "has_property"),
        (r"if (\w+) then (\w+)",        "implies"),
        (r"(\w+) depends on (\w+)",     "depends_on"),
        (r"(\w+) contradicts (\w+)",    "contradicts"),
    ]

    def parse(self, text: str, source: str = "perception") -> List[MRLPredicate]:
        predicates = []
        for pattern, functor in self.PATTERNS:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                predicates.append(MRLPredicate(
                    functor=functor,
                    arguments=list(m.groups()),
                    confidence=0.85,
                    source=source
                ))
        return predicates
