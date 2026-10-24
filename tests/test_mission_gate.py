import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from dataclasses import replace
from rhns.core.missions import MissionContract, Evidence, evaluate

class MissionGateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 24, tzinfo=timezone.utc)
        self.contract = MissionContract("m1", frozenset({"confirmed"}), frozenset({"crm"}), Decimal("5"), self.now + timedelta(hours=1))
        self.item = Evidence("m1", "confirmed", "crm", "record-1", self.now)

    def run_gate(self, items=(), **kwargs):
        options = dict(spent=Decimal("1"), now=self.now, verify=lambda item: True)
        options.update(kwargs)
        return evaluate(self.contract, tuple(items), **options)

    def test_verified(self):
        self.assertTrue(self.run_gate([self.item]).complete)

    def test_missing(self):
        self.assertFalse(self.run_gate().complete)

    def test_rejected(self):
        self.assertFalse(self.run_gate([self.item], verify=lambda item: False).complete)

    def test_verifier_error(self):
        def broken(item):
            raise RuntimeError("offline")
        self.assertFalse(self.run_gate([self.item], verify=broken).complete)

    def test_wrong_mission(self):
        self.assertFalse(self.run_gate([replace(self.item, mission_id="m2")]).complete)

    def test_wrong_source(self):
        self.assertFalse(self.run_gate([replace(self.item, source="model")]).complete)

    def test_blank_reference(self):
        self.assertFalse(self.run_gate([replace(self.item, reference=" ")]).complete)

    def test_future_evidence(self):
        self.assertFalse(self.run_gate([replace(self.item, observed_at=self.now + timedelta(days=1))]).complete)

    def test_naive_evidence(self):
        self.assertFalse(self.run_gate([replace(self.item, observed_at=self.now.replace(tzinfo=None))]).complete)

    def test_budget(self):
        self.assertFalse(self.run_gate([self.item], spent=Decimal("6")).complete)

    def test_deadline(self):
        self.assertFalse(self.run_gate([self.item], now=self.now + timedelta(days=1)).complete)

    def test_nan_spend(self):
        with self.assertRaises(ValueError):
            self.run_gate(spent=Decimal("NaN"))

    def test_invalid_contract(self):
        with self.assertRaises(ValueError):
            replace(self.contract, max_cost=Decimal("-1"))

    def test_truthy_is_not_verified(self):
        self.assertFalse(self.run_gate([self.item], verify=lambda item: "yes").complete)
