"""In-memory hash-chained audit ledger.

Tamper-evident for this process lifetime; not immutable, durable, or a
substitute for external receipt anchoring and independent reconciliation.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, List


def _digest(index: int, timestamp: float, module: str, event: str,
            payload: Any, prev_hash: str) -> str:
    content = json.dumps(
        {
            "index": index,
            "timestamp": timestamp,
            "module": module,
            "event": event,
            "payload": payload,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


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
        self.hash = _digest(
            self.index, self.timestamp, self.module, self.event, self.payload, self.prev_hash
        )


class AuditLedger:
    GENESIS_HASH = "0" * 64

    def __init__(self):
        self.entries: List[AuditEntry] = []

    def record(self, module: str, event: str, payload: Any) -> AuditEntry:
        # Validate payload is deterministically JSON-serializable before append.
        json.dumps(payload, sort_keys=True, allow_nan=False)
        prev_hash = self.entries[-1].hash if self.entries else self.GENESIS_HASH
        entry = AuditEntry(
            index=len(self.entries),
            timestamp=time.time(),
            module=module,
            event=event,
            payload=payload,
            prev_hash=prev_hash,
        )
        self.entries.append(entry)
        return entry

    def verify_chain(self) -> bool:
        for index, entry in enumerate(self.entries):
            expected_prev = self.entries[index - 1].hash if index else self.GENESIS_HASH
            if entry.index != index or entry.prev_hash != expected_prev:
                return False
            try:
                if _digest(
                    entry.index, entry.timestamp, entry.module, entry.event,
                    entry.payload, entry.prev_hash
                ) != entry.hash:
                    return False
            except (ValueError, TypeError):
                return False
        return True

    def export_json(self) -> str:
        return json.dumps(
            [
                {
                    "index": entry.index,
                    "timestamp": entry.timestamp,
                    "module": entry.module,
                    "event": entry.event,
                    "payload": entry.payload,
                    "prev_hash": entry.prev_hash,
                    "hash": entry.hash,
                }
                for entry in self.entries
            ],
            indent=2,
            sort_keys=True,
        )
