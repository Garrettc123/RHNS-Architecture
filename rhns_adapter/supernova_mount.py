from __future__ import annotations

import os

from fastapi import APIRouter, FastAPI, HTTPException, status

from .compute_governance import ComputeGovernor, ComputePolicy, build_compute_governance_router
from .gate import GatePolicy, evaluate_proposal
from .ledger import GovernanceLedger
from .normalizer import normalize_proposal
from .schemas import ApprovalRequest, GovernanceReceipt, IngressProposalRequest

FORBIDDEN_PORT = 8000
DEFAULT_SUPERNOVA_PORT = 8090


def build_governance_router(
    ledger: GovernanceLedger,
    policy: GatePolicy,
) -> APIRouter:
    router = APIRouter(prefix="/v1/governance", tags=["rhns-governance"])

    @router.post(
        "/evaluate",
        response_model=GovernanceReceipt,
        status_code=status.HTTP_200_OK,
    )
    def evaluate_endpoint(req: IngressProposalRequest) -> GovernanceReceipt:
        try:
            canonical = normalize_proposal(req)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Normalization failed: {exc}",
            ) from exc

        decision, violations = evaluate_proposal(canonical, policy)
        try:
            return ledger.append(canonical, decision, violations)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ledger commit failed: {exc}",
            ) from exc

    @router.post(
        "/approve/{proposal_id}",
        response_model=GovernanceReceipt,
        status_code=status.HTTP_200_OK,
    )
    def approve_endpoint(
        proposal_id: str,
        approval: ApprovalRequest,
    ) -> GovernanceReceipt:
        try:
            return ledger.record_approval_override(
                proposal_id=proposal_id,
                reviewer_id=approval.reviewer_id,
                verdict=approval.verdict.value,
                justification=approval.justification,
                signature_hex=approval.signature_hex,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Approval ledger write failed: {exc}",
            ) from exc

    @router.get("/ledger/verify")
    def verify_endpoint() -> dict[str, object]:
        result = ledger.verify_chain()
        if not result["valid"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result,
            )
        return result

    return router


def mount_into_supernova_os(
    supernova_app: FastAPI,
    *,
    db_path: str | None = None,
    policy: GatePolicy | None = None,
    compute_policy: ComputePolicy | None = None,
) -> FastAPI:
    resolved_db = db_path or os.getenv("RHNS_LEDGER_DB", "rhns_governance_ledger.db")
    ledger = GovernanceLedger(resolved_db)
    active_policy = policy or GatePolicy()
    supernova_app.include_router(build_governance_router(ledger, active_policy))
    active_compute_policy = compute_policy if compute_policy is not None else ComputePolicy.from_environment()
    supernova_app.include_router(build_compute_governance_router(ComputeGovernor(resolved_db, active_compute_policy)))
    return supernova_app


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("SUPERNOVA_PORT", str(DEFAULT_SUPERNOVA_PORT)))
    if port == FORBIDDEN_PORT:
        raise RuntimeError("Port 8000 is prohibited in Garcar Sovereign One.")

    # Replace with `from garcar_supernova_os.main import app as supernova_app` in production
    supernova_app = FastAPI(title="Garcar Sovereign One (garcar-supernova-os)")
    mount_into_supernova_os(supernova_app)
    uvicorn.run(supernova_app, host="0.0.0.0", port=port, reload=False)
