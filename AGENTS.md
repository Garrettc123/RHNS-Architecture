# AGENTS.md — RHNS Architecture

## What this is
A FastAPI app (`main.py`) exposing the RHNS (Recursive Hierarchical Network System) cognitive architecture API. Originally targeted at Vercel (`vercel.json`); run locally as a standard uvicorn dev server.

## Running
- `docker compose -f docker-compose.base44.yml up -d` brings up the `web` service on host port 3000 (container 8000).
- Base image: `python:3.12-slim`. Source is bind-mounted at `/app`; `fastapi` + `uvicorn[standard]` are installed at container startup, then `uvicorn main:app --reload` runs with live reload.

## Key quirk: requirements.txt vs. the server
- `requirements.txt` lists heavy ML deps (`torch`, `transformers`, `sentence-transformers`) used by the library modules under `core/`, `perception/`, `reasoning/`, `generation/`. **The FastAPI server (`main.py`) does NOT import any of these** — it only needs `fastapi` + `uvicorn`, which is why the compose installs just those for a fast, lightweight preview.
- If you need to run the ML modules or the test suite (`pytest`), install the full `requirements.txt` (expect a large download).

## Endpoints
- `GET /` — system info
- `GET /health` — health check (used by the compose healthcheck)
- `GET /architecture` — component map
- `POST /reason?goal=...&context=...` — submit a goal to the reasoning pipeline

## No external services
No database, cache, or external API credentials are required to run the server.
