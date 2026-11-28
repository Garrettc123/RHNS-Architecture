"""PostgreSQL-backed, transactionally serialized RHNS hash-chained audit ledger.

Requires independent managed PostgreSQL storage. Ordinary row updates/deletes
are blocked with a database trigger; this is NOT externally anchored WORM storage.
"""
from __future__ import annotations

import json
import time
from typing import Any

import psycopg

from .ledger import AuditEntry, AuditLedger, _canonical_payload, _entry_digest

_TABLE = "rhns_audit_entries"
_LOCK_KEY = 628183022


class PostgresAuditLedger:
    GENESIS_HASH = AuditLedger.GENESIS_HASH
    persistent = True

    def __init__(self, dsn: str):
        if not dsn or not dsn.startswith(("postgresql://", "postgres://")):
            raise ValueError("RHNS PostgreSQL connection string required")
        self._dsn = dsn
        # No schema mutations at import/startup. Apply audited SQL migration first.
        with self._connection() as connection:
            with connection.cursor() as cur:
                cur.execute("SELECT entry_index FROM rhns_audit_entries LIMIT 0")
                cur.execute(
                    "SELECT COUNT(*) FROM pg_trigger WHERE tgrelid = "
                    "'rhns_audit_entries'::regclass AND tgname = "
                    "'rhns_audit_no_mutation' AND NOT tgisinternal"
                )
                if cur.fetchone()[0] != 1:
                    raise RuntimeError("RHNS immutable audit trigger is not installed")

    def _connection(self):
        # One short-lived connection per transaction; never print DSN.
        return psycopg.connect(self._dsn, connect_timeout=5)

    @property
    def entries(self) -> list[AuditEntry]:
        with self._connection() as connection:
            with connection.cursor() as cur:
                cur.execute("SELECT entry_index, timestamp, module, event, payload_json, "
                            "prev_hash, entry_hash FROM rhns_audit_entries ORDER BY entry_index")
                rows = cur.fetchall()
        result: list[AuditEntry] = []
        for index, stamp, module, event, encoded, previous, digest in rows:
            payload = json.loads(encoded)
            if _canonical_payload(payload) != encoded:
                raise ValueError("RHNS audit payload is not canonical")
            entry = AuditEntry(index=index, timestamp=stamp, module=module,
                               event=event, payload=payload, prev_hash=previous)
            entry.hash = digest
            result.append(entry)
        return result

    def record(self, module: str, event: str, payload: Any) -> AuditEntry:
        encoded = _canonical_payload(payload)
        with self._connection() as connection:
            with connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
                cur.execute("SELECT entry_index, entry_hash FROM rhns_audit_entries "
                            "ORDER BY entry_index DESC LIMIT 1")
                previous = cur.fetchone()
                index = previous[0] + 1 if previous else 0
                prev_hash = previous[1] if previous else self.GENESIS_HASH
                entry = AuditEntry(index=index, timestamp=time.time(),
                                   module=module, event=event,
                                   payload=json.loads(encoded), prev_hash=prev_hash)
                cur.execute(
                    "INSERT INTO rhns_audit_entries "
                    "(entry_index,timestamp,module,event,payload_json,prev_hash,entry_hash) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (entry.index, entry.timestamp, entry.module, entry.event,
                     encoded, entry.prev_hash, entry.hash),
                )
        return entry

    def verify_chain(self) -> bool:
        previous = self.GENESIS_HASH
        for index, entry in enumerate(self.entries):
            if entry.index != index or entry.prev_hash != previous:
                return False
            if entry.hash != _entry_digest(entry.index, entry.timestamp, entry.module,
                                           entry.event, entry.payload, entry.prev_hash):
                return False
            previous = entry.hash
        return True

    def export_json(self) -> str:
        return json.dumps([{"index": e.index, "timestamp": e.timestamp,
                            "module": e.module, "event": e.event, "payload": e.payload,
                            "prev_hash": e.prev_hash, "hash": e.hash}
                           for e in self.entries], indent=2)

    def close(self) -> None:
        # Stateless connections are closed on every operation.
        pass
