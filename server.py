#!/usr/bin/env python3
"""
FastAPI service for the personal AI agent with observability and basic auth.
Run: uvicorn server:app --host 0.0.0.0 --port 8000
"""
import os
from contextlib import asynccontextmanager
from typing import Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
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


load_dotenv()

API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")
AUTH_DISABLED = os.getenv("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
flight_data_service = FlightDataService(signing_key=os.getenv("FLIGHT_DATA_SIGNING_KEY"))


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
agent = None


class ChatRequest(BaseModel):
    prompt: str = Field(..., description="User prompt for the AI agent.")


class ChatResponse(BaseModel):
    response: str
    latency_ms: float
    suspicious: Optional[str] = None


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
    flight_id: str = Field(..., min_length=1)
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
        reply = runtime_agent.invoke({"input": request.prompt})["output"]
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
