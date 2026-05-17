#!/usr/bin/env python3
"""
FastAPI service for the personal AI agent with observability and basic auth.
Run: uvicorn server:app --host 0.0.0.0 --port 8000
"""
import os
import math
import random
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, TypedDict

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
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
agent = create_agent()

_DASHBOARD_HTML_PATH = Path(__file__).with_name("dashboard.html")
_AIRCRAFT_LOCK = threading.Lock()
_AIRCRAFT_STATE: list["AircraftStatePayload"] = []
_LAST_AIRCRAFT_UPDATE = time.time()
_MIN_UPDATE_INTERVAL_SEC = 0.1
_MAX_UPDATE_INTERVAL_SEC = 3.0
_MAX_HEADING_CHANGE_DEGREES = 4.0
_MIN_ALTITUDE_FT = 500.0
_MAX_ALTITUDE_FT = 45000.0
_ALTITUDE_VARIATION_FT = 220.0
_BOUNDARY_RADIUS_NM = 100
_SECONDS_PER_HOUR = 3600.0
_HOURS_PER_SECOND = 1.0 / _SECONDS_PER_HOUR
_STEALTH_PROBABILITY = 0.18


class ChatRequest(BaseModel):
    prompt: str = Field(..., description="User prompt for the AI agent.")


class ChatResponse(BaseModel):
    response: str
    latency_ms: float
    suspicious: Optional[str] = None


class AircraftState(BaseModel):
    id: str
    call_sign: str
    type: str
    stealth: bool
    x: float
    y: float
    heading: float
    speed_kts: float
    altitude_ft: float


class LiveAircraftResponse(BaseModel):
    aircraft: list[AircraftState]
    updated_at: int
    range_nm: int


class AircraftStatePayload(TypedDict):
    id: str
    call_sign: str
    type: str
    stealth: bool
    x: float
    y: float
    heading: float
    speed_kts: float
    altitude_ft: float


def _build_aircraft_state(count: int = 24) -> list[AircraftStatePayload]:
    """Create initial synthetic aircraft data for the radar dashboard feed."""
    aircraft_types = ["commercial", "cargo", "military", "private", "drone"]
    state: list[AircraftStatePayload] = []
    for idx in range(count):
        angle = random.uniform(0, 360)
        radius = random.uniform(12, 95)
        heading = random.uniform(0, 360)
        speed = random.uniform(120, 620)
        altitude = random.uniform(1500, 43000)
        state.append(
            {
                "id": f"AC{idx + 1:03d}",
                "call_sign": f"PX{random.randint(100, 999)}",
                "type": random.choice(aircraft_types),
                "stealth": random.random() < _STEALTH_PROBABILITY,
                "x": math.sin(math.radians(angle)) * radius,
                "y": math.cos(math.radians(angle)) * radius,
                "heading": heading,
                "speed_kts": speed,
                "altitude_ft": altitude,
            }
        )
    return state


def _update_aircraft_state() -> list[AircraftStatePayload]:
    """Advance the synthetic aircraft simulation and return response-safe snapshots."""
    global _AIRCRAFT_STATE, _LAST_AIRCRAFT_UPDATE
    now = time.time()
    dt = min(
        max(now - _LAST_AIRCRAFT_UPDATE, _MIN_UPDATE_INTERVAL_SEC),
        _MAX_UPDATE_INTERVAL_SEC,
    )
    _LAST_AIRCRAFT_UPDATE = now
    if not _AIRCRAFT_STATE:
        _AIRCRAFT_STATE = _build_aircraft_state()

    for aircraft in _AIRCRAFT_STATE:
        speed_nm_per_sec = aircraft["speed_kts"] * _HOURS_PER_SECOND
        distance = speed_nm_per_sec * dt
        angle_radians = math.radians(aircraft["heading"])
        aircraft["x"] += math.sin(angle_radians) * distance
        aircraft["y"] += math.cos(angle_radians) * distance
        aircraft["heading"] = (
            aircraft["heading"]
            + random.uniform(
                -_MAX_HEADING_CHANGE_DEGREES,
                _MAX_HEADING_CHANGE_DEGREES,
            )
        ) % 360
        aircraft["altitude_ft"] = min(
            _MAX_ALTITUDE_FT,
            max(
                _MIN_ALTITUDE_FT,
                aircraft["altitude_ft"]
                + random.uniform(-_ALTITUDE_VARIATION_FT, _ALTITUDE_VARIATION_FT),
            ),
        )
        if math.hypot(aircraft["x"], aircraft["y"]) > _BOUNDARY_RADIUS_NM:
            aircraft["heading"] = (aircraft["heading"] + 180) % 360

    return [
        {
            "id": aircraft["id"],
            "call_sign": aircraft["call_sign"],
            "type": aircraft["type"],
            "stealth": aircraft["stealth"],
            "x": round(aircraft["x"], 3),
            "y": round(aircraft["y"], 3),
            "heading": round(aircraft["heading"], 1),
            "speed_kts": round(aircraft["speed_kts"], 1),
            "altitude_ft": round(aircraft["altitude_ft"], 1),
        }
        for aircraft in _AIRCRAFT_STATE
    ]


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
        reply = agent.invoke({"input": request.prompt})["output"]
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


@app.get("/v1/aircraft/live", response_model=LiveAircraftResponse)
async def live_aircraft(_: None = Depends(require_api_key)) -> LiveAircraftResponse:
    with _AIRCRAFT_LOCK:
        aircraft = _update_aircraft_state()
    return LiveAircraftResponse(
        aircraft=aircraft,
        updated_at=round(time.time() * 1000),
        range_nm=_BOUNDARY_RADIUS_NM,
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    return HTMLResponse(_DASHBOARD_HTML_PATH.read_text(encoding="utf-8"))
