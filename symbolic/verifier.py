# symbolic/verifier.py
from typing import List, Tuple
from symbolic.parser import MRLPredicate

class SymbolicVerifier:
    """
    Datalog-style forward-chaining verifier.
    Checks predicate consistency and detects contradictions.
    """
    def __init__(self):
        self.fact_base: List[MRLPredicate] = []
        self.contradiction_log: List[Tuple[MRLPredicate, MRLPredicate]] = []

    def load(self, predicates: List[MRLPredicate]):
        self.fact_base.extend(predicates)

    def verify(self, predicate: MRLPredicate) -> Tuple[bool, str]:
        for fact in self.fact_base:
            if (fact.functor == "contradicts" and
                set(fact.arguments) == set(predicate.arguments)):
                self.contradiction_log.append((fact, predicate))
                return False, f"CONTRADICTION: {predicate} conflicts with {fact}"
        self.fact_base.append(predicate)
        return True, "OK"

    def forward_chain(self) -> List[MRLPredicate]:
        """Apply implies rules to derive new facts."""
        derived = []
        implies_rules = [f for f in self.fact_base if f.functor == "implies"]
        for rule in implies_rules:
            antecedent, consequent = rule.arguments
            for fact in self.fact_base:
                if antecedent in fact.arguments and fact.functor == "is_a":
                    new_fact = MRLPredicate(
                        functor="is_a",
                        arguments=[consequent, fact.arguments[-1]],
                        confidence=rule.confidence * 0.9,
                        source="inference"
                    )
                    if new_fact not in self.fact_base:
                        derived.append(new_fact)
        self.fact_base.extend(derived)
        return derived
