"""Unified API with no simulated runtime or success responses."""
import logging
import os
import secrets
from typing import Optional
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class RunRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=8000)

def authorize(authorization: Optional[str] = Header(default=None)):
    key = os.environ.get("RHNS_API_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="API authentication is not configured")
    if not secrets.compare_digest((authorization or "").encode(), ("Bearer " + key).encode()):
        raise HTTPException(status_code=401, detail="Unauthorized")

def create_app(agent_factory=None):
    app = FastAPI(title="RHNS Runtime", version="2.1.0")

    @app.get("/")
    def root():
        return {"system": "RHNS", "production_ready": False}

    @app.get("/health")
    def health():
        return {"status": "alive", "scope": "api_process_only"}

    @app.get("/ready", dependencies=[Depends(authorize)])
    def ready():
        if agent_factory is None:
            raise HTTPException(status_code=503, detail="Runtime dependencies are not configured")
        return {"factory_configured": True, "runtime_verified": False}

    @app.post("/run", dependencies=[Depends(authorize)])
    @app.post("/reason", dependencies=[Depends(authorize)])
    def run(request: RunRequest):
        if not request.goal.strip():
            raise HTTPException(status_code=422, detail="A nonempty goal is required")
        if agent_factory is None:
            raise HTTPException(status_code=503, detail="Runtime dependencies are not configured")
        try:
            return agent_factory().run(request.goal)
        except Exception:
            logger.exception("RHNS runtime failed")
            raise HTTPException(status_code=503, detail="Runtime unavailable") from None

    return app

app = create_app()
