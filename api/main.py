"""Public RHNS API: bounded and explicit about unverified reasoning results."""

import logging
import os
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from search.lats_controller import LATSController

logger = logging.getLogger(__name__)

app = FastAPI(
    title="RHNS Symbolic Diagnostic API",
    description="Local, read-only symbolic extraction and bounded LATS ranking. Not an autonomous executor.",
    version="2.1.0",
)

allowed_origins = [
    origin.strip()
    for origin in os.environ.get("RHNS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

_controller = LATSController()


class RunRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    schema: Literal["general_reasoning"] = "general_reasoning"


class RunResponse(BaseModel):
    frame_id: str
    verifier_status: str
    operator_history: list[str]
    subgoal_stack: list[str]
    reward: float
    depth_reached: int
    tree_size: int
    execution_mode: Literal["analysis_only"]
    best_state: str


@app.get("/")
def root():
    return {
        "system": "RHNS",
        "version": "2.1.0",
        "mode": "analysis_only",
        "capabilities": ["predicate_extraction", "bounded_lats_ranking"],
        "external_execution": False,
    }


@app.get("/health")
def health():
    return {"status": "healthy", "mode": "analysis_only"}


def _diagnose(goal: str, schema: str = "general_reasoning") -> RunResponse:
    try:
        return RunResponse(**_controller.run(goal=goal, schema=schema))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        logger.exception("RHNS diagnostic failed")
        raise HTTPException(status_code=500, detail="Internal diagnostic error") from error


@app.post("/run", response_model=RunResponse)
def run_agent(request: RunRequest):
    return _diagnose(request.goal, request.schema)


@app.post("/run/batch")
def run_batch(goals: list[str]):
    if not 1 <= len(goals) <= 20:
        raise HTTPException(status_code=422, detail="batch must contain 1 to 20 goals")
    return {
        "results": [_diagnose(goal).model_dump() for goal in goals],
        "count": len(goals),
    }


@app.post("/reason")
def reason(goal: str = Query(min_length=1, max_length=2000), context: str | None = None):
    """Legacy query interface. Context is returned, not silently interpreted."""
    return {
        "goal_received": goal,
        "context": context,
        "context_used": False,
        "status": "completed",
        "result": _diagnose(goal).model_dump(),
    }
