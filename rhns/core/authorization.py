"""Trusted-host authorization boundary. Never expose approve() to agents.

Host must authenticate the human approver and derive tenant/mission identity.
Protect the SQLite file from agents. This is not a connector or identity service.
Consumption precedes dispatch: failures require reconciliation, not token reuse.
"""
import hashlib
import json
import secrets
import sqlite3
from dataclasses import dataclass
from typing import Callable

@dataclass(frozen=True)
class Action:
    tenant: str
    mission: str
    tool: str
    target: str
    payload_json: str

    def canonical(self):
        if not all(isinstance(x, str) and x.strip() for x in
                   (self.tenant, self.mission, self.tool, self.target)):
            raise ValueError("Nonempty resolved action identifiers required")
        def reject(value):
            raise ValueError("Nonfinite JSON forbidden")
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate JSON key")
                result[key] = value
            return result
        payload = json.loads(self.payload_json, parse_constant=reject, object_pairs_hook=unique)
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a JSON object")
        return json.dumps([self.tenant, self.mission, self.tool, self.target, payload],
                          sort_keys=True, separators=(",", ":"), allow_nan=False)

class AuthorizationGate:
    def __init__(self, path: str, clock: Callable[[], int]):
        self.path, self.clock = path, clock
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS approvals (token TEXT PRIMARY KEY, action TEXT NOT NULL, approver TEXT NOT NULL, expires INTEGER NOT NULL, state TEXT NOT NULL)")

    def _db(self):
        return sqlite3.connect(self.path, timeout=10)

    def approve(self, action: Action, *, authenticated_approver: str, ttl_seconds: int = 300):
        """Trusted host only, after the human reviews the exact canonical action."""
        canonical = action.canonical()
        if not authenticated_approver.strip() or type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900:
            raise ValueError("Authenticated approver and TTL of 1..900 required")
        token = secrets.token_urlsafe(32)
        with self._db() as db:
            db.execute("INSERT INTO approvals VALUES (?, ?, ?, ?, 'approved')",
                       (hashlib.sha256(token.encode()).hexdigest(), canonical,
                        authenticated_approver, self.clock() + ttl_seconds))
        return token

    def revoke(self, token: str):
        with self._db() as db:
            db.execute("UPDATE approvals SET state='revoked' WHERE token=? AND state='approved'",
                       (hashlib.sha256(token.encode()).hexdigest(),))

    def consume(self, token: str, action: Action):
        canonical = action.canonical()
        with self._db() as db:
            cursor = db.execute("UPDATE approvals SET state='consumed' WHERE token=? AND action=? AND expires>? AND state='approved'",
                                (hashlib.sha256(token.encode()).hexdigest(), canonical, self.clock()))
            if cursor.rowcount != 1:
                raise PermissionError("No matching unexpired unused approval")

    def dispatch(self, token: str, action: Action, *, adapter: Callable):
        """Host selects adapter; it must execute only the supplied canonical action.

        Does not guarantee exactly-once external effects. Never auto-retry after
        dispatch uncertainty. Agent must have no direct connector credentials.
        """
        self.consume(token, action)
        return adapter(json.loads(action.canonical()))
