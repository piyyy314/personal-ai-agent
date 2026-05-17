#!/usr/bin/env python3
"""
FastAPI service for the personal AI agent with observability and basic auth.
Run: uvicorn server:app --host 0.0.0.0 --port 8000
"""
import os
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dotenv import load_dotenv
from flight_data_backend import FlightDataService
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
from radar_api import router as radar_router, radar_shutdown, radar_startup_async


load_dotenv()

API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")
AUTH_DISABLED = os.getenv("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
MIN_SIGNING_KEY_LENGTH = 16


def get_flight_data_signing_key() -> Optional[str]:
    signing_key = os.getenv("FLIGHT_DATA_SIGNING_KEY")
    if not signing_key:
        warnings.warn(
            "FLIGHT_DATA_SIGNING_KEY is not configured; flight data integrity hashes will use unsigned SHA-256 digests.",
            stacklevel=2,
        )
        return None
    if len(signing_key) < MIN_SIGNING_KEY_LENGTH:
        warnings.warn(
            f"FLIGHT_DATA_SIGNING_KEY is shorter than {MIN_SIGNING_KEY_LENGTH} characters; use a longer secret for stronger integrity protection.",
            stacklevel=2,
        )
    return signing_key


flight_data_service = FlightDataService(signing_key=get_flight_data_signing_key())


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
agent = None

# ── Static files & radar dashboard ────────────────────────────────
_static_dir = Path(__file__).parent / "static"
_static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# ── Radar API router ───────────────────────────────────────────────
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


class FlightPointRequest(BaseModel):
    timestamp: str
    latitude: float
    longitude: float
    altitude: float
    altitude_unit: Literal["ft", "m"] = "ft"
    speed: float
    speed_unit: Literal["kts", "kmh", "mph"] = "kts"
    heading: float
    vertical_rate: Optional[float] = None
    vertical_rate_unit: Literal["fpm", "mps"] = "fpm"
    transponder: Literal["on", "off", "unknown"] = "unknown"
    signature: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    source: str = "unknown"


class FlightIngestRequest(BaseModel):
    flight_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._-]+$",
        description="Path-safe flight identifier used in /v1/flight-data/{flight_id}.",
    )
    callsign: Optional[str] = None
    tail_number: Optional[str] = None
    aircraft_type: Optional[str] = None
    operator: Optional[str] = None
    stealth_mode: bool = False
    metadata: Dict[str, object] = Field(default_factory=dict)
    points: List[FlightPointRequest]


def get_agent_instance():
    global agent
    if agent is None:
        from agent import create_agent

        agent = create_agent()
    return agent


def model_to_dict(model: BaseModel) -> Dict[str, object]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


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


@app.post("/v1/flight-data")
async def ingest_flight_data(
    request: FlightIngestRequest, _: None = Depends(require_api_key)
) -> JSONResponse:
    try:
        snapshot = flight_data_service.ingest(model_to_dict(request))
    except ValueError as validation_error:
        raise HTTPException(status_code=422, detail=str(validation_error)) from validation_error

    audit_event(
        "flight_data_ingested",
        {
            "flight_id": snapshot["flight_id"],
            "records_ingested": snapshot["records_ingested"],
            "stealth_mode": snapshot["stealth_mode"],
        },
    )
    return JSONResponse(content=snapshot)


@app.get("/v1/flight-data")
async def list_flight_data(_: None = Depends(require_api_key)) -> JSONResponse:
    snapshots = flight_data_service.list_flights()
    return JSONResponse(content={"items": snapshots, "count": len(snapshots)})


@app.get("/v1/flight-data/{flight_id}")
async def get_flight_data(
    flight_id: str, _: None = Depends(require_api_key)
) -> JSONResponse:
    try:
        snapshot = flight_data_service.get_flight(flight_id)
    except KeyError as missing_flight:
        raise HTTPException(status_code=404, detail="Flight not found") from missing_flight
    return JSONResponse(content=snapshot)


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
        runtime_agent = get_agent_instance()
    except RuntimeError as init_error:
        record_security_event("agent_unavailable")
        audit_event("agent_unavailable", {"error": str(init_error), "source": "api"})
        raise HTTPException(
            status_code=503,
            detail="Chat agent unavailable; configure OPENAI_API_KEY to enable /v1/chat.",
        ) from init_error

    try:
        result = runtime_agent.invoke(
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
