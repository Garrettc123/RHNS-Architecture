# audit/ledger.py
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import List, Any

@dataclass
class AuditEntry:
    index: int
    timestamp: float
    module: str
    event: str
    payload: Any
    prev_hash: str
    hash: str = field(init=False)

    def __post_init__(self):
        content = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "module": self.module,
            "event": self.event,
            "payload": str(self.payload),
            "prev_hash": self.prev_hash
        }, sort_keys=True)
        self.hash = hashlib.sha256(content.encode()).hexdigest()

class AuditLedger:
    """
    Append-only cryptographically chained audit log.
    Every module writes here. No entry can be altered without
    breaking the hash chain.
    """
    GENESIS_HASH = "0" * 64

    def __init__(self):
        self.entries: List[AuditEntry] = []

    def record(self, module: str, event: str, payload: Any) -> AuditEntry:
        prev_hash = self.entries[-1].hash if self.entries else self.GENESIS_HASH
        entry = AuditEntry(
            index=len(self.entries),
            timestamp=time.time(),
            module=module,
            event=event,
            payload=payload,
            prev_hash=prev_hash
        )
        self.entries.append(entry)
        return entry

    def verify_chain(self) -> bool:
        for i, entry in enumerate(self.entries):
            expected_prev = self.entries[i - 1].hash if i > 0 else self.GENESIS_HASH
            if entry.prev_hash != expected_prev:
                return False
            content = json.dumps({
                "index": entry.index,
                "timestamp": entry.timestamp,
                "module": entry.module,
                "event": entry.event,
                "payload": str(entry.payload),
                "prev_hash": entry.prev_hash
            }, sort_keys=True)
            if hashlib.sha256(content.encode()).hexdigest() != entry.hash:
                return False
        return True

    def export_json(self) -> str:
        return json.dumps([
            {
                "index": e.index,
                "module": e.module,
                "event": e.event,
                "payload": str(e.payload),
                "hash": e.hash[:16] + "..."
            }
            for e in self.entries
        ], indent=2)
