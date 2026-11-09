# audit/ledger.py
"""Hash-chained audit ledgers: in-memory compatibility and SQLite persistence."""
import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Any


def _canonical_payload(payload: Any) -> str:
    """Serialize audit payloads deterministically; reject non-JSON values."""
    try:
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Audit payload must contain finite JSON-compatible values") from exc


def _entry_digest(index: int, timestamp: float, module: str, event: str,
                  payload: Any, prev_hash: str) -> str:
    content = json.dumps({
        "index": index,
        "timestamp": timestamp,
        "module": module,
        "event": event,
        "payload": _canonical_payload(payload),
        "prev_hash": prev_hash,
    }, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(content.encode()).hexdigest()


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
        self.hash = _entry_digest(
            self.index, self.timestamp, self.module, self.event,
            self.payload, self.prev_hash,
        )


class AuditLedger:
    """Process-local append-only hash chain; entries do not survive restart."""
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
            prev_hash=prev_hash,
        )
        self.entries.append(entry)
        return entry

    def verify_chain(self) -> bool:
        previous = self.GENESIS_HASH
        for index, entry in enumerate(self.entries):
            if entry.index != index or entry.prev_hash != previous:
                return False
            if _entry_digest(
                entry.index, entry.timestamp, entry.module, entry.event,
                entry.payload, entry.prev_hash,
            ) != entry.hash:
                return False
            previous = entry.hash
        return True

    def export_json(self) -> str:
        return json.dumps([
            {
                "index": entry.index,
                "module": entry.module,
                "event": entry.event,
                "payload": str(entry.payload),
                "hash": entry.hash[:16] + "...",
            }
            for entry in self.entries
        ], indent=2)


class SQLiteAuditLedger:
    """SQLite-backed hash chain with immutable rows and restart recovery.

    The database is append-only through SQLite triggers for ordinary SQL
    operations. This is not WORM storage: a privileged actor able to replace
    the database file can still alter it. Back up and protect the file and
    its directory using deployment-level controls.
    """
    GENESIS_HASH = "0" * 64

    def __init__(self, database_path: str):
        if not database_path:
            raise ValueError("database_path must be a non-empty path")
        self.database_path = (
            database_path if database_path == ":memory:"
            else str(Path(database_path).expanduser())
        )
        self._lock = threading.RLock()
        if self.database_path != ":memory:":
            Path(self.database_path).resolve().parent.mkdir(
                parents=True, exist_ok=True
            )
        self._connection = sqlite3.connect(
            self.database_path, timeout=10, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute("PRAGMA busy_timeout = 10000")
            if self.database_path != ":memory:":
                self._connection.execute("PRAGMA journal_mode = WAL")
                self._connection.execute("PRAGMA synchronous = FULL")
            self._connection.executescript("""
                CREATE TABLE IF NOT EXISTS audit_entries (
                    entry_index INTEGER PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    module TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    entry_hash TEXT NOT NULL UNIQUE
                );
                CREATE TRIGGER IF NOT EXISTS audit_entries_no_update
                BEFORE UPDATE ON audit_entries
                BEGIN
                    SELECT RAISE(ABORT, 'audit entries are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS audit_entries_no_delete
                BEFORE DELETE ON audit_entries
                BEGIN
                    SELECT RAISE(ABORT, 'audit entries are append-only');
                END;
            """)
            self._connection.commit()

    @property
    def persistent(self) -> bool:
        return self.database_path != ":memory:"

    @property
    def entries(self) -> List[AuditEntry]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM audit_entries ORDER BY entry_index"
            ).fetchall()
        result = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            if _canonical_payload(payload) != row["payload_json"]:
                raise ValueError("Audit payload is not stored in canonical JSON form")
            entry = AuditEntry(
                index=row["entry_index"],
                timestamp=row["timestamp"],
                module=row["module"],
                event=row["event"],
                payload=payload,
                prev_hash=row["prev_hash"],
            )
            entry.hash = row["entry_hash"]
            result.append(entry)
        return result

    def record(self, module: str, event: str, payload: Any) -> AuditEntry:
        payload_json = _canonical_payload(payload)

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT entry_index, entry_hash FROM audit_entries "
                    "ORDER BY entry_index DESC LIMIT 1"
                ).fetchone()
                index = row["entry_index"] + 1 if row else 0
                prev_hash = row["entry_hash"] if row else self.GENESIS_HASH
                entry = AuditEntry(
                    index=index,
                    timestamp=time.time(),
                    module=module,
                    event=event,
                    payload=json.loads(payload_json),
                    prev_hash=prev_hash,
                )
                self._connection.execute(
                    "INSERT INTO audit_entries "
                    "(entry_index, timestamp, module, event, payload_json, prev_hash, entry_hash) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        entry.index, entry.timestamp, entry.module, entry.event,
                        payload_json, entry.prev_hash, entry.hash,
                    ),
                )
                self._connection.commit()
                return entry
            except Exception:
                self._connection.rollback()
                raise

    def verify_chain(self) -> bool:
        previous = self.GENESIS_HASH
        for expected_index, entry in enumerate(self.entries):
            if entry.index != expected_index or entry.prev_hash != previous:
                return False
            expected_hash = _entry_digest(
                entry.index, entry.timestamp, entry.module, entry.event,
                entry.payload, entry.prev_hash,
            )
            if expected_hash != entry.hash:
                return False
            previous = entry.hash
        return True

    def export_json(self) -> str:
        return json.dumps([
            {
                "index": entry.index,
                "module": entry.module,
                "event": entry.event,
                "payload": str(entry.payload),
                "hash": entry.hash[:16] + "...",
            }
            for entry in self.entries
        ], indent=2)

    def close(self) -> None:
        with self._lock:
            self._connection.close()
