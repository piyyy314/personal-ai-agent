#!/usr/bin/env python3
"""
FastAPI service for the personal AI agent with observability and basic auth.
Run: uvicorn server:app --host 0.0.0.0 --port 8000
"""
import os
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from aircraft_visualization import (
    AircraftSnapshot,
    build_aircraft_analysis,
    render_aircraft_visualization,
)
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
    yield
    set_session_status(False)
    audit_event("shutdown", {"mode": "api"})


app = FastAPI(title="Personal AI Agent", version="1.0.0", lifespan=lifespan)


class ChatRequest(BaseModel):
    prompt: str = Field(..., description="User prompt for the AI agent.")


class ChatResponse(BaseModel):
    response: str
    latency_ms: float
    suspicious: Optional[str] = None


class AircraftAnalysisRequest(BaseModel):
    altitude_ft: float = Field(..., ge=0, description="Aircraft altitude in feet.")
    speed_kts: float = Field(..., ge=0, description="Aircraft speed in knots.")
    heading_deg: float = Field(..., description="Aircraft heading in degrees.")
    stealth_enabled: bool = Field(
        False, description="Whether stealth mode or low-observable posture is active."
    )


@lru_cache(maxsize=1)
def get_agent():
    return create_agent()


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
        reply = get_agent().invoke({"input": request.prompt})["output"]
        duration = timer() - start_time
        record_request_outcome("success", duration, source="api")
        audit_event(
            "response",
            {
                "latency_ms": round(duration * 1000, 2),
                "status": "success",
                "source": "api",
            },
        )
        return JSONResponse(
            content={
                "response": reply,
                "latency_ms": round(duration * 1000, 2),
                "suspicious": suspicious,
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


@app.post("/v1/aircraft/analyze")
async def analyze_aircraft(
    request: AircraftAnalysisRequest, _: None = Depends(require_api_key)
) -> JSONResponse:
    snapshot = AircraftSnapshot(
        altitude_ft=request.altitude_ft,
        speed_kts=request.speed_kts,
        heading_deg=request.heading_deg,
        stealth_enabled=request.stealth_enabled,
    )
    return JSONResponse(content=build_aircraft_analysis(snapshot))


@app.get("/aircraft/visualization", response_class=HTMLResponse)
async def aircraft_visualization(
    altitude: float = Query(32000, ge=0),
    speed: float = Query(480, ge=0),
    heading: float = 75,
    stealth: bool = False,
    _: None = Depends(require_api_key),
) -> HTMLResponse:
    snapshot = AircraftSnapshot(
        altitude_ft=altitude,
        speed_kts=speed,
        heading_deg=heading,
        stealth_enabled=stealth,
    )
    return HTMLResponse(content=render_aircraft_visualization(snapshot))
