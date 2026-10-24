import unittest
import tempfile
from dataclasses import replace
from rhns.core.authorization import Action, AuthorizationGate

class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 100
        self.path = self.temp.name + "/auth.db"
        self.gate = AuthorizationGate(self.path, lambda: self.now)
        self.action = Action("tenant", "mission", "crm.update", "record-1", '{"stage":"qualified"}')
        self.token = self.gate.approve(self.action, authenticated_approver="human-1")

    def test_exact_dispatch(self):
        result = self.gate.dispatch(self.token, self.action, adapter=lambda value: value)
        self.assertEqual(result[3], "record-1")

    def test_changes_denied(self):
        for field, value in [("tenant", "other"), ("mission", "other"), ("tool", "other"), ("target", "other"), ("payload_json", '{"stage":"closed"}')]:
            with self.subTest(field=field), self.assertRaises(PermissionError):
                self.gate.consume(self.token, replace(self.action, **{field: value}))
        self.gate.consume(self.token, self.action)

    def test_restart_replay_denied(self):
        self.gate.consume(self.token, self.action)
        restarted = AuthorizationGate(self.path, lambda: self.now)
        with self.assertRaises(PermissionError):
            restarted.consume(self.token, self.action)

    def test_expiry(self):
        self.now = 400
        with self.assertRaises(PermissionError):
            self.gate.consume(self.token, self.action)

    def test_revoke(self):
        self.gate.revoke(self.token)
        with self.assertRaises(PermissionError):
            self.gate.consume(self.token, self.action)

    def test_unknown_token(self):
        with self.assertRaises(PermissionError):
            self.gate.consume("unknown", self.action)

    def test_adapter_error_burns_token(self):
        def broken(value):
            raise TimeoutError()
        with self.assertRaises(TimeoutError):
            self.gate.dispatch(self.token, self.action, adapter=broken)
        with self.assertRaises(PermissionError):
            self.gate.consume(self.token, self.action)

    def test_invalid_payload(self):
        for payload in ['{"a":1,"a":2}', '{"a":NaN}', '[]']:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                replace(self.action, payload_json=payload).canonical()

    def test_no_dispatch_without_approval(self):
        calls = []
        with self.assertRaises(PermissionError):
            self.gate.dispatch("unknown", self.action, adapter=calls.append)
        self.assertEqual(calls, [])
