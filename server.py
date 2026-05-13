#!/usr/bin/env python3
"""
FastAPI service for the personal AI agent with observability and basic auth.
Run: uvicorn server:app --host 0.0.0.0 --port 8000
"""
import os
from functools import lru_cache
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from dotenv import load_dotenv
from agent import create_agent
from flight_analysis import analyze_flight_operations
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


@lru_cache(maxsize=1)
def get_agent():
    return create_agent()


class ChatRequest(BaseModel):
    prompt: str = Field(..., description="User prompt for the AI agent.")


class ChatResponse(BaseModel):
    response: str
    latency_ms: float
    suspicious: Optional[str] = None


class FlightAnalysisRequest(BaseModel):
    flights: List[Dict[str, Any]] = Field(default_factory=list)
    events: List[Dict[str, Any]] = Field(default_factory=list)
    filters: Dict[str, Any] = Field(default_factory=dict)
    search_query: Optional[str] = None
    search_limit: int = Field(default=10, ge=1, le=100)


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
        raise HTTPException(status_code=400, detail="Flight analysis failed") from run_error
