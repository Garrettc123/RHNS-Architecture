"""Generation authorization only; not external-action approval."""
from typing import Callable, TypeVar

T = TypeVar("T")

class GenerationBlocked(RuntimeError):
    pass

def guarded_generate(decision: str, generate: Callable[[], T]) -> T:
    """Invoke generation only for an explicit metacognitive commit."""
    if decision != "commit":
        raise GenerationBlocked(f"Generation blocked: {decision!r}")
    return generate()
