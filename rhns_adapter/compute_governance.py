"""RHNS bounded compute reservations and auditable metering (not a VCAD audit).

The API must be restricted to a trusted scheduler and metering worker. Recorded usage
is *operator supplied*; independently reconciled infrastructure evidence is separate.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

GENESIS = "0" * 64


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _dec(value: Any) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Invalid decimal quantity") from exc
    if not number.is_finite() or number < 0:
        raise ValueError("Quantity must be finite and nonnegative")
    return number


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkloadCategory(str, Enum):
    CAPABILITIES_RD = "capabilities_rd"
    CUSTOMER_INFERENCE_TRAINED_ON = "customer_inference_trained_on"
    CUSTOMER_INFERENCE = "customer_inference"
    SAFEGUARD_CLASSIFIERS = "safeguard_classifiers"
    NON_CAPABILITIES_RD = "non_capabilities_rd"


CAPABILITIES = {WorkloadCategory.CAPABILITIES_RD.value, WorkloadCategory.CUSTOMER_INFERENCE_TRAINED_ON.value}


class Reservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=128)
    job_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    category: WorkloadCategory
    gpu_type: str = Field(min_length=1, max_length=128)
    estimated_gpu_hours: Decimal = Field(gt=0)
    workload_ref: str = Field(min_length=1, max_length=512)


class Settlement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=128)
    job_id: str = Field(min_length=1, max_length=128)
    actual_gpu_hours: Decimal = Field(ge=0)
    cpu_seconds: Decimal = Field(default=Decimal(0), ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    meter_evidence_ref: str = Field(min_length=1, max_length=512)


class CancelReservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=128)
    job_id: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=512)


class MeterReconciliation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=128)
    day_utc: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    source: str = Field(min_length=1, max_length=128)
    external_metered_gpu_equivalent_hours: Decimal = Field(ge=0)
    external_evidence_ref: str = Field(min_length=1, max_length=512)


@dataclass(frozen=True)
class ComputePolicy:
    daily_gpu_equivalent_hour_budget: Decimal
    gpu_equivalence: dict[str, Decimal]
    capabilities_share_cap: Decimal | None = None

    def __post_init__(self) -> None:
        if _dec(self.daily_gpu_equivalent_hour_budget) <= 0:
            raise ValueError("A positive daily compute budget is required")
        if not self.gpu_equivalence or any(_dec(x) <= 0 for x in self.gpu_equivalence.values()):
            raise ValueError("Explicit positive GPU equivalence factors are required")
        if self.capabilities_share_cap is not None and not 0 <= _dec(self.capabilities_share_cap) <= 1:
            raise ValueError("Capabilities share must be in [0,1]")

    @classmethod
    def from_environment(cls) -> ComputePolicy | None:
        raw = os.environ.get("RHNS_COMPUTE_POLICY_JSON")
        if not raw:
            return None
        payload = json.loads(raw)
        return cls(
            daily_gpu_equivalent_hour_budget=_dec(payload["daily_gpu_equivalent_hour_budget"]),
            capabilities_share_cap=(_dec(payload["capabilities_share_cap"]) if "capabilities_share_cap" in payload else None),
            gpu_equivalence={k: _dec(v) for k, v in payload["gpu_equivalence"].items()},
        )


class ComputeConflict(ValueError):
    pass


class ComputeGovernor:
    def __init__(self, db_path: str, policy: ComputePolicy | None):
        self.db_path, self.policy = db_path, policy
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA busy_timeout=10000")
        return c

    def _init_db(self) -> None:
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS compute_jobs (
                    tenant_id TEXT NOT NULL, job_id TEXT NOT NULL, day_utc TEXT NOT NULL,
                    request_json TEXT NOT NULL, estimated_gpu_equiv TEXT NOT NULL,
                    actual_gpu_equiv TEXT, settlement_json TEXT, state TEXT NOT NULL,
                    reserve_seq INTEGER NOT NULL, final_seq INTEGER,
                    PRIMARY KEY(tenant_id, job_id)
                );
                CREATE TABLE IF NOT EXISTS compute_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL, payload_json TEXT NOT NULL,
                    recorded_at_utc TEXT NOT NULL, prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS compute_reconciliations (
                    tenant_id TEXT NOT NULL, day_utc TEXT NOT NULL, source TEXT NOT NULL,
                    claim_json TEXT NOT NULL, receipt_seq INTEGER NOT NULL,
                    PRIMARY KEY(tenant_id,day_utc,source)
                );
            """)

    @staticmethod
    def _append(c: sqlite3.Connection, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = c.execute("SELECT seq, entry_hash FROM compute_events ORDER BY seq DESC LIMIT 1").fetchone()
        seq = int(row["seq"]) + 1 if row else 1
        prev = str(row["entry_hash"]) if row else GENESIS
        recorded = _now()
        entry = {"seq": seq, "kind": kind, "payload": payload, "recorded_at_utc": recorded, "prev_hash": prev}
        digest = _sha(entry)
        c.execute("INSERT INTO compute_events (seq,kind,payload_json,recorded_at_utc,prev_hash,entry_hash) VALUES (?,?,?,?,?,?)",
                  (seq,kind,_json(payload),recorded,prev,digest))
        return {"seq":seq, "kind":kind, "prev_hash":prev, "entry_hash":digest, "recorded_at_utc":recorded}

    @staticmethod
    def _receipt(c: sqlite3.Connection, seq: int) -> dict[str, Any]:
        row = c.execute("SELECT * FROM compute_events WHERE seq=?", (seq,)).fetchone()
        return {"seq":row["seq"],"kind":row["kind"],"prev_hash":row["prev_hash"],
                "entry_hash":row["entry_hash"],"recorded_at_utc":row["recorded_at_utc"]}

    @staticmethod
    def _totals(c: sqlite3.Connection, tenant: str, day: str) -> tuple[Decimal, Decimal, dict[str, Decimal]]:
        rows = c.execute("SELECT request_json, estimated_gpu_equiv, actual_gpu_equiv FROM compute_jobs WHERE tenant_id=? AND day_utc=? AND state != 'CANCELLED'", (tenant,day)).fetchall()
        total, caps = Decimal(0), Decimal(0)
        categories: dict[str, Decimal] = {}
        for row in rows:
            category = json.loads(row["request_json"])["category"]
            amount = _dec(row["actual_gpu_equiv"] if row["actual_gpu_equiv"] is not None else row["estimated_gpu_equiv"])
            total += amount
            categories[category] = categories.get(category, Decimal(0)) + amount
            if category in CAPABILITIES:
                caps += amount
        return total, caps, categories

    def reserve(self, request: Reservation) -> dict[str, Any]:
        if self.policy is None:
            raise RuntimeError("Compute policy not configured; refusing reservations")
        if request.gpu_type not in self.policy.gpu_equivalence:
            raise ValueError("Unknown GPU equivalence; refusing unaccountable work")
        day = datetime.now(timezone.utc).date().isoformat()
        req = request.model_dump(mode="json")
        equivalent = request.estimated_gpu_hours * self.policy.gpu_equivalence[request.gpu_type]
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            self._assert_integrity(c)
            prior = c.execute("SELECT * FROM compute_jobs WHERE tenant_id=? AND job_id=?",(request.tenant_id,request.job_id)).fetchone()
            if prior:
                if prior["request_json"] != _json(req):
                    raise ComputeConflict("Reused job_id with different reservation")
                # A replay must never grant another dispatch authorization.
                return {"allowed":False, "state":prior["state"], "reason":"duplicate_job_id",
                        "receipt":self._receipt(c,prior["reserve_seq"]),"idempotent":True}
            total, caps, _ = self._totals(c, request.tenant_id, day)
            next_total = total + equivalent
            next_caps = caps + (equivalent if request.category.value in CAPABILITIES else Decimal(0))
            violation = None
            if next_total > self.policy.daily_gpu_equivalent_hour_budget:
                violation = "daily_gpu_equivalent_hour_budget_exceeded"
            elif request.category.value in CAPABILITIES and self.policy.capabilities_share_cap is None:
                violation = "capabilities_cap_not_configured"
            elif self.policy.capabilities_share_cap is not None and next_caps > self.policy.daily_gpu_equivalent_hour_budget * self.policy.capabilities_share_cap:
                violation = "capabilities_budget_exceeded"
            payload = {"tenant_id":request.tenant_id,"job_id":request.job_id,"day_utc":day,
                       "reservation":req,"estimated_gpu_equiv":str(equivalent),"violation":violation}
            receipt = self._append(c,"RESERVE_DENIED" if violation else "RESERVE_ALLOWED",payload)
            if violation:
                return {"allowed":False,"state":"DENIED","reason":violation,"receipt":receipt}
            c.execute("INSERT INTO compute_jobs VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (request.tenant_id,request.job_id,day,_json(req),str(equivalent),None,None,"RESERVED",receipt["seq"],None))
            return {"allowed":True,"state":"RESERVED","receipt":receipt}

    def settle(self, request: Settlement) -> dict[str, Any]:
        if self.policy is None:
            raise RuntimeError("Compute policy not configured")
        req = request.model_dump(mode="json")
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            self._assert_integrity(c)
            job = c.execute("SELECT * FROM compute_jobs WHERE tenant_id=? AND job_id=?",(request.tenant_id,request.job_id)).fetchone()
            if not job:
                raise KeyError("Unknown reservation")
            if job["state"] == "SETTLED":
                if job["settlement_json"] != _json(req):
                    raise ComputeConflict("Conflicting second settlement")
                return {"state":"SETTLED","receipt":self._receipt(c,job["final_seq"]),"idempotent":True}
            if job["state"] != "RESERVED":
                raise ComputeConflict("Reservation is not active")
            reserved_request = json.loads(job["request_json"])
            # Keep the hardware conversion factor from authorization, even after policy rotation.
            frozen_factor = _dec(job["estimated_gpu_equiv"]) / _dec(reserved_request["estimated_gpu_hours"])
            actual = request.actual_gpu_hours * frozen_factor
            over_reservation = actual > _dec(job["estimated_gpu_equiv"])
            c.execute("UPDATE compute_jobs SET actual_gpu_equiv=?,settlement_json=?,state='SETTLED' WHERE tenant_id=? AND job_id=?",
                      (str(actual),_json(req),request.tenant_id,request.job_id))
            total, caps, _ = self._totals(c,request.tenant_id,job["day_utc"])
            cap_breach = (self.policy.capabilities_share_cap is not None and caps > self.policy.daily_gpu_equivalent_hour_budget * self.policy.capabilities_share_cap)
            budget_breach = total > self.policy.daily_gpu_equivalent_hour_budget
            receipt = self._append(c,"SETTLED",{"tenant_id":request.tenant_id,"job_id":request.job_id,
                "settlement":req,"actual_gpu_equiv":str(actual),"day_utc":job["day_utc"],
                "over_reservation":over_reservation,"budget_breach":budget_breach,"capabilities_breach":cap_breach})
            c.execute("UPDATE compute_jobs SET final_seq=? WHERE tenant_id=? AND job_id=?",(receipt["seq"],request.tenant_id,request.job_id))
            return {"state":"SETTLED","over_reservation":over_reservation,"budget_breach":budget_breach,
                    "capabilities_breach":cap_breach,"receipt":receipt}

    def cancel(self, request: CancelReservation) -> dict[str, Any]:
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            self._assert_integrity(c)
            job = c.execute("SELECT * FROM compute_jobs WHERE tenant_id=? AND job_id=?",(request.tenant_id,request.job_id)).fetchone()
            if not job:
                raise KeyError("Unknown reservation")
            if job["state"] != "RESERVED":
                raise ComputeConflict("Only active reservations can be cancelled")
            receipt = self._append(c,"CANCELLED",request.model_dump(mode="json"))
            c.execute("UPDATE compute_jobs SET state='CANCELLED',final_seq=? WHERE tenant_id=? AND job_id=?",(receipt["seq"],request.tenant_id,request.job_id))
            return {"state":"CANCELLED","receipt":receipt}

    def reconcile(self, request: MeterReconciliation) -> dict[str, Any]:
        # This is an attributed external claim, not independent verification.
        day = datetime.fromisoformat(request.day_utc).date().isoformat()
        if day != request.day_utc:
            raise ValueError("day_utc must be a real ISO calendar day")
        payload = request.model_dump(mode="json")
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            self._assert_integrity(c)
            prior = c.execute("SELECT * FROM compute_reconciliations WHERE tenant_id=? AND day_utc=? AND source=?",(request.tenant_id,day,request.source)).fetchone()
            if prior:
                if prior["claim_json"] != _json(payload):
                    raise ComputeConflict("Conflicting reconciliation for source/day")
                return {"receipt":self._receipt(c,prior["receipt_seq"]),"idempotent":True}
            receipt = self._append(c,"METER_RECONCILIATION_CLAIM",payload)
            c.execute("INSERT INTO compute_reconciliations VALUES (?,?,?,?,?)",(request.tenant_id,day,request.source,_json(payload),receipt["seq"]))
            return {"receipt":receipt,"independently_verified":False}

    def report(self, tenant_id: str, day_utc: str) -> dict[str, Any]:
        day = datetime.fromisoformat(day_utc).date().isoformat()
        if day != day_utc:
            raise ValueError("Invalid UTC date")
        with self._conn() as c:
            c.execute("BEGIN")
            self._assert_integrity(c)
            total, caps, categories = self._totals(c,tenant_id,day)
            jobs = c.execute("SELECT state,settlement_json FROM compute_jobs WHERE tenant_id=? AND day_utc=?",(tenant_id,day)).fetchall()
            reconciliations = [json.loads(r["claim_json"]) for r in c.execute("SELECT claim_json FROM compute_reconciliations WHERE tenant_id=? AND day_utc=?",(tenant_id,day))]
            return {"tenant_id":tenant_id,"day_utc":day,"gpu_equivalent_hours_reserved_or_settled":str(total),
                    "capabilities_gpu_equivalent_hours":str(caps),"category_gpu_equivalent_hours":{k:str(v) for k,v in categories.items()},
                    "jobs_reserved":sum(j["state"]=="RESERVED" for j in jobs),
                    "jobs_settled":sum(j["state"]=="SETTLED" for j in jobs),
                    "jobs_cancelled":sum(j["state"]=="CANCELLED" for j in jobs),
                    "external_meter_claims":reconciliations,"independently_verified":False,
                    "accounting_completeness":"UNVERIFIED", "policy_configured":self.policy is not None}

    def _verify_connection(self, c: sqlite3.Connection) -> dict[str, Any]:
        rows = c.execute("SELECT * FROM compute_events ORDER BY seq ASC").fetchall()
        previous = GENESIS
        for expected_seq, row in enumerate(rows,1):
            try:
                payload = json.loads(row["payload_json"])
                expected = _sha({"seq":row["seq"],"kind":row["kind"],"payload":payload,
                                 "recorded_at_utc":row["recorded_at_utc"],"prev_hash":row["prev_hash"]})
                valid = (row["seq"]==expected_seq and row["prev_hash"]==previous and
                         row["payload_json"]==_json(payload) and row["entry_hash"]==expected)
            except (ValueError, TypeError):
                valid = False
            if not valid:
                return {"valid":False,"entries_verified":expected_seq-1,"failed_seq":expected_seq}
            previous = row["entry_hash"]
        # Verify the mutable SQL projection matches the event ledger. Otherwise a
        # modified jobs table could yield false reports while event hashes still pass.
        expected_jobs: dict[tuple[str, str], dict[str, Any]] = {}
        expected_claims: dict[tuple[str, str, str], tuple[str, int]] = {}
        try:
            for row in rows:
                event = json.loads(row["payload_json"])
                kind = row["kind"]
                if kind == "RESERVE_ALLOWED":
                    key = (event["tenant_id"], event["job_id"])
                    if key in expected_jobs:
                        raise ValueError("Duplicate authorization in ledger")
                    expected_jobs[key] = {
                        "day_utc": event["day_utc"],
                        "request_json": _json(event["reservation"]),
                        "estimated_gpu_equiv": event["estimated_gpu_equiv"],
                        "actual_gpu_equiv": None, "settlement_json": None,
                        "state": "RESERVED", "reserve_seq": row["seq"], "final_seq": None,
                    }
                elif kind == "SETTLED":
                    key = (event["tenant_id"], event["job_id"])
                    if key not in expected_jobs or expected_jobs[key]["state"] != "RESERVED":
                        raise ValueError("Settlement without active reservation")
                    expected_jobs[key].update({
                        "actual_gpu_equiv": event["actual_gpu_equiv"],
                        "settlement_json": _json(event["settlement"]),
                        "state": "SETTLED", "final_seq": row["seq"],
                    })
                elif kind == "CANCELLED":
                    key = (event["tenant_id"], event["job_id"])
                    if key not in expected_jobs or expected_jobs[key]["state"] != "RESERVED":
                        raise ValueError("Cancellation without active reservation")
                    expected_jobs[key].update({"state": "CANCELLED", "final_seq": row["seq"]})
                elif kind == "METER_RECONCILIATION_CLAIM":
                    key = (event["tenant_id"], event["day_utc"], event["source"])
                    if key in expected_claims:
                        raise ValueError("Duplicate reconciliation claim")
                    expected_claims[key] = (_json(event), row["seq"])
                elif kind != "RESERVE_DENIED":
                    raise ValueError("Unknown compute event type")
            jobs = c.execute("SELECT * FROM compute_jobs").fetchall()
            claims = c.execute("SELECT * FROM compute_reconciliations").fetchall()
            if len(jobs) != len(expected_jobs) or len(claims) != len(expected_claims):
                raise ValueError("Projection row count mismatch")
            for job in jobs:
                key = (job["tenant_id"], job["job_id"])
                expected = expected_jobs.get(key)
                if expected is None or any(job[field] != value for field, value in expected.items()):
                    raise ValueError("Job projection mismatch")
            for claim in claims:
                key = (claim["tenant_id"], claim["day_utc"], claim["source"])
                if expected_claims.get(key) != (claim["claim_json"], claim["receipt_seq"]):
                    raise ValueError("Meter claim projection mismatch")
        except (ValueError, TypeError, KeyError):
            return {"valid":False,"entries_verified":len(rows),"reason":"materialized_view_mismatch"}
        return {"valid":True,"entries_verified":len(rows),"tip_hash":previous,"externally_anchored":False}

    def verify(self) -> dict[str, Any]:
        """Verify chain and materialized usage together in one consistent SQLite snapshot."""
        with self._conn() as c:
            c.execute("BEGIN")
            return self._verify_connection(c)

    def _assert_integrity(self, c: sqlite3.Connection) -> None:
        """Refuse budget decisions or ledger mutations on inconsistent state.

        Called inside BEGIN IMMEDIATE before changes, preventing concurrent
        writers from invalidating the verification prior to authorization.
        """
        result = self._verify_connection(c)
        if not result["valid"]:
            raise RuntimeError("Compute accounting integrity failed; refusing operation")

    def pending(self, tenant_id: str, older_than_seconds: int = 86400, limit: int = 100) -> dict[str, Any]:
        """Read-only list of unmetered reservations; never silently reclaim them."""
        if not tenant_id or not tenant_id.strip():
            raise ValueError("tenant_id must not be empty")
        if older_than_seconds < 0 or limit < 1 or limit > 500:
            raise ValueError("Invalid pending inspection bounds")
        with self._conn() as c:
            c.execute("BEGIN")
            self._assert_integrity(c)
            rows = c.execute(
                """SELECT j.job_id, j.day_utc, j.request_json, e.recorded_at_utc,
                          e.entry_hash, j.estimated_gpu_equiv
                   FROM compute_jobs AS j
                   JOIN compute_events AS e ON e.seq=j.reserve_seq
                   WHERE j.tenant_id=? AND j.state='RESERVED'
                   ORDER BY e.recorded_at_utc ASC""",
                (tenant_id,),
            ).fetchall()
        current = datetime.now(timezone.utc)
        overdue = []
        for row in rows:
            age = max(0, int((current - datetime.fromisoformat(row["recorded_at_utc"])).total_seconds()))
            if age >= older_than_seconds:
                req = json.loads(row["request_json"])
                overdue.append({
                    "job_id": row["job_id"], "agent_id": req["agent_id"],
                    "category": req["category"], "day_utc": row["day_utc"],
                    "reserved_gpu_equivalent_hours": row["estimated_gpu_equiv"],
                    "reserved_at_utc": row["recorded_at_utc"],
                    "age_seconds": age, "reservation_entry_hash": row["entry_hash"],
                })
        return {
            "tenant_id": tenant_id, "threshold_seconds": older_than_seconds,
            "unsettled_count": len(rows), "stale_count": len(overdue),
            "stale_reservations": overdue[:limit], "truncated": len(overdue) > limit,
            "automatically_released": False,
            "accounting_completeness": "UNVERIFIED",
        }


def build_compute_governance_router(governor: ComputeGovernor) -> APIRouter:
    router = APIRouter(prefix="/v1/governance/compute", tags=["rhns-compute-governance"])

    def require_operator(authorization: str | None = Header(default=None)) -> None:
        token = os.environ.get("RHNS_COMPUTE_API_TOKEN")
        if not token:
            raise HTTPException(503,"Compute API token not configured")
        if not authorization or not hmac.compare_digest(authorization, "Bearer " + token):
            raise HTTPException(401,"Unauthorized")

    # Dependency executes prior to request handling for all endpoints, including reports.
    from fastapi import Depends
    auth = [Depends(require_operator)]

    def guard(fn, *args):
        try:
            return fn(*args)
        except KeyError as exc:
            raise HTTPException(404,str(exc)) from exc
        except (ValueError, ComputeConflict) as exc:
            raise HTTPException(409,str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503,str(exc)) from exc

    @router.post("/reserve", dependencies=auth)
    def reserve(req: Reservation):
        return guard(governor.reserve,req)

    @router.post("/settle", dependencies=auth)
    def settle(req: Settlement):
        return guard(governor.settle,req)

    @router.post("/cancel", dependencies=auth)
    def cancel(req: CancelReservation):
        return guard(governor.cancel,req)

    @router.post("/reconcile", dependencies=auth)
    def reconcile(req: MeterReconciliation):
        return guard(governor.reconcile,req)

    @router.get("/report", dependencies=auth)
    def report(tenant_id: str, day_utc: str):
        return guard(governor.report,tenant_id,day_utc)

    @router.get("/pending", dependencies=auth)
    def pending(tenant_id: str, older_than_seconds: int = 86400, limit: int = 100):
        return guard(governor.pending,tenant_id,older_than_seconds,limit)

    @router.get("/verify", dependencies=auth)
    def verify():
        result = governor.verify()
        if not result["valid"]:
            raise HTTPException(409,result)
        return result

    return router
