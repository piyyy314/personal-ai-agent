#!/usr/bin/env python3
"""
FastAPI service for the personal AI agent with observability and basic auth.
Run: uvicorn server:app --host 0.0.0.0 --port 8000
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dotenv import load_dotenv
from flight_analysis import analyze_flight_operations
from flight_tracking import FlightHistoryStore, FlightObservation
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
flight_history = FlightHistoryStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    health_port = int(os.getenv("HEALTH_PORT", "8080"))
    health_server = start_health_server(port=health_port)
    set_session_status(True)
    audit_event("startup", {"mode": "api"})
    await radar_startup_async()
    yield
    set_session_status(False)
    audit_event("shutdown", {"mode": "api"})
    await radar_shutdown()
    health_server.shutdown()


app = FastAPI(title="Personal AI Agent", version="1.0.0", lifespan=lifespan)


@lru_cache(maxsize=1)
def get_agent():
    from agent import create_agent

    return create_agent()


_static_dir = Path(__file__).parent / "static"
_static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
app.include_router(radar_router)


@app.get("/dashboard", include_in_schema=False)
async def dashboard_redirect() -> RedirectResponse:
    """Redirect top-level /dashboard to the radar ops-center dashboard."""
    return RedirectResponse(url="/radar/dashboard")


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


class FlightAnalysisRequest(BaseModel):
    flights: List[Dict[str, Any]] = Field(default_factory=list)
    events: List[Dict[str, Any]] = Field(default_factory=list)
    filters: Dict[str, Any] = Field(default_factory=dict)
    search_query: Optional[str] = None
    search_limit: int = Field(default=10, ge=1, le=100)


class FlightObservationRequest(BaseModel):
    aircraft_id: str = Field(..., description="Stable aircraft identifier or callsign.")
    timestamp: datetime = Field(..., description="Observation timestamp in ISO-8601 format.")
    latitude: float
    longitude: float
    altitude_ft: Optional[float] = None
    groundspeed_kts: Optional[float] = None
    heading_deg: Optional[float] = None
    squawk: Optional[str] = None
    event_type: str = Field(default="position", description="position, alert, handoff, etc.")
    source: str = Field(default="manual", description="Data source for the observation.")
    metadata: Dict[str, Any] = Field(default_factory=dict)


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
        result = get_agent().invoke(
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


@app.post("/v1/flight-analysis")
async def flight_analysis(
    request: FlightAnalysisRequest, _: None = Depends(require_api_key)
) -> JSONResponse:
    start_time = timer()
    try:
        result = analyze_flight_operations(
            flights=request.flights,
            events=request.events,
            filters=request.filters,
            search_query=request.search_query,
            search_limit=request.search_limit,
        )
        duration = timer() - start_time
        record_request_outcome("success", duration, source="api")
        audit_event(
            "flight_analysis",
            {
                "flight_count": len(request.flights),
                "event_count": len(request.events),
                "filtered_count": len(result["filtered_flights"]),
                "latency_ms": round(duration * 1000, 2),
                "status": "success",
            },
        )
        return JSONResponse(content=result)
    except Exception as run_error:
        duration = timer() - start_time
        record_request_outcome("error", duration, source="api")
        record_security_event("flight_analysis_error")
        audit_event(
            "flight_analysis",
            {
                "flight_count": len(request.flights),
                "event_count": len(request.events),
                "latency_ms": round(duration * 1000, 2),
                "status": "error",
                "error": str(run_error),
            },
        )
        raise HTTPException(
            status_code=400,
            detail=f"Flight analysis failed: {run_error.__class__.__name__}",
        ) from run_error


@app.post("/v1/flights/history")
async def record_flight_history(
    request: FlightObservationRequest, _: None = Depends(require_api_key)
) -> JSONResponse:
    result = flight_history.record(
        FlightObservation(
            aircraft_id=request.aircraft_id,
            timestamp=request.timestamp,
            latitude=request.latitude,
            longitude=request.longitude,
            altitude_ft=request.altitude_ft,
            groundspeed_kts=request.groundspeed_kts,
            heading_deg=request.heading_deg,
            squawk=request.squawk,
            event_type=request.event_type,
            source=request.source,
            metadata=request.metadata,
        )
    )
    audit_event(
        "flight_history_recorded",
        {
            "aircraft_id": request.aircraft_id,
            "event_type": request.event_type,
            "source": request.source,
            "anomaly_count": len(result["anomalies"]),
        },
    )
    for anomaly in result["anomalies"]:
        record_security_event(f"flight_{anomaly['type']}")
    return JSONResponse(content=result)


@app.get("/v1/flights/timeline")
async def get_flight_timeline(
    aircraft_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    _: None = Depends(require_api_key),
) -> JSONResponse:
    timeline = flight_history.timeline(
        aircraft_id=aircraft_id,
        start_time=start_time,
        end_time=end_time,
    )
    audit_event(
        "flight_timeline_requested",
        {
            "aircraft_id": aircraft_id,
            "event_count": timeline["event_count"],
        },
    )
    return JSONResponse(content=timeline)


@app.get("/v1/flights/{aircraft_id}/replay")
async def replay_flight_history(
    aircraft_id: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    interval_seconds: Optional[int] = None,
    _: None = Depends(require_api_key),
) -> JSONResponse:
    replay = flight_history.replay(
        aircraft_id=aircraft_id,
        start_time=start_time,
        end_time=end_time,
        interval_seconds=interval_seconds,
    )
    audit_event(
        "flight_replay_requested",
        {
            "aircraft_id": aircraft_id,
            "frame_count": replay["frame_count"],
        },
    )
    return JSONResponse(content=replay)
