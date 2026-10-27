from __future__ import annotations

import os
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="RHNS Agentic System",
    description="Recursive Hierarchical Neuro-Symbolic agentic reasoning engine — Garcar Enterprise",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    goal: str
    schema: Optional[str] = "general_reasoning"


class RunResponse(BaseModel):
    frame_id: str
    verifier_status: str
    operator_history: list[str]
    subgoal_stack: list[str]
    reward: float
    depth_reached: int
    tree_size: int


@app.get("/")
def root():
    return {
        "system": "RHNS Agentic System",
        "version": "2.0.0",
        "status": "operational",
        "author": "Garrett Carrol",
        "organization": "Garcar Enterprise",
    }


@app.get("/health")
def health():
    return {"status": "healthy", "system": "RHNS Agentic System"}


@app.post("/run", response_model=RunResponse)
def run_agent(request: RunRequest):
    """Execute the RHNS LATS reasoning pipeline on a goal."""
    try:
        from search.lats_controller import LATSController
        controller = LATSController()
        result = controller.run(goal=request.goal, schema=request.schema or "general_reasoning")
        return RunResponse(**result)
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"LATS controller not available: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/run/batch")
def run_batch(goals: list[str]):
    """Run multiple goals through the RHNS pipeline."""
    from search.lats_controller import LATSController
    controller = LATSController()
    results = []
    for goal in goals:
        result = controller.run(goal=goal)
        results.append(result)
    return {"results": results, "count": len(results)}