#!/usr/bin/env python3
"""
FastAPI service for the personal AI agent with observability and basic auth.
Run: uvicorn server:app --host 0.0.0.0 --port 8000
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dotenv import load_dotenv
from agent import create_agent
from health_server import start_health_server
from monitoring import (
    audit_event,
    configure_logging,
    detect_suspicious_query,
    metrics_response,
    record_request_outcome,
    record_security_event,
    set_session_status,
    timer,
)
from prometheus_client import CONTENT_TYPE_LATEST
from radar_api import router as radar_router, radar_startup_async, radar_shutdown


load_dotenv()

API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")
AUTH_DISABLED = os.getenv("AUTH_DISABLED", "").lower() in ("1", "true", "yes")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    health_port = int(os.getenv("HEALTH_PORT", "8080"))
    start_health_server(port=health_port)
    set_session_status(True)
    audit_event("startup", {"mode": "api"})
    await radar_startup_async()
    yield
    set_session_status(False)
    audit_event("shutdown", {"mode": "api"})
    await radar_shutdown()


app = FastAPI(title="Personal AI Agent", version="1.0.0", lifespan=lifespan)
agent = create_agent()

# ── Static files & radar dashboard ────────────────────────────────
_static_dir = Path(__file__).parent / "static"
_static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# ── Radar API router ───────────────────────────────────────────────
app.include_router(radar_router)


class ChatRequest(BaseModel):
    prompt: str = Field(..., description="User prompt for the AI agent.")
    stealth: bool = Field(
        default=False,
        description="When true, uses a stateless agent path that does not persist session history.",
    )
    use_cache: bool = Field(
        default=True,
        description="When true, allows privacy-aware response cache reuse.",
    )


class ChatResponse(BaseModel):
    response: str
    latency_ms: float
    suspicious: Optional[str] = None
    cache_hit: bool = False
    stealth: bool = False


def require_api_key(request: Request) -> None:
    if AUTH_DISABLED:
        return
    if not API_AUTH_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Server misconfiguration: API_AUTH_TOKEN is not configured. Set AUTH_DISABLED=true to explicitly disable authentication.",
        )
    provided = request.headers.get("x-api-key")
    if provided != API_AUTH_TOKEN:
        record_security_event("unauthorized_request")
        audit_event(
            "unauthorized_request",
            {
                "client": request.client.host if request.client else "unknown",
                "path": request.url.path,
            },
        )
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/healthz")
async def healthcheck() -> dict:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    payload = metrics_response()
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest, _: None = Depends(require_api_key)
) -> JSONResponse:
    suspicious = detect_suspicious_query(request.prompt)
    if suspicious:
        record_security_event(suspicious)
        audit_event("suspicious_query", {"pattern": suspicious, "source": "api"})

    start_time = timer()
    try:
        result = agent.invoke(
            {
                "input": request.prompt,
                "stealth": request.stealth,
                "use_cache": request.use_cache,
            }
        )
        reply = result["output"]
        cache_hit = result.get("cache_hit", False)
        stealth_mode = result.get("stealth", False)
        duration = timer() - start_time
        record_request_outcome("success", duration, source="api")
        audit_event(
            "response",
            {
                "latency_ms": round(duration * 1000, 2),
                "status": "success",
                "source": "api",
                "stealth": request.stealth,
                "cache_hit": cache_hit,
            },
        )
        return JSONResponse(
            content={
                "response": reply,
                "latency_ms": round(duration * 1000, 2),
                "suspicious": suspicious,
                "cache_hit": cache_hit,
                "stealth": stealth_mode,
            }
        )
    except Exception as run_error:
        duration = timer() - start_time
        record_request_outcome("error", duration, source="api")
        record_security_event("agent_error")
        audit_event(
            "response",
            {
                "latency_ms": round(duration * 1000, 2),
                "status": "error",
                "source": "api",
                "error": str(run_error),
            },
        )
        raise HTTPException(status_code=500, detail="Agent failed to respond") from run_error
