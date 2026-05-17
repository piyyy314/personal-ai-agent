#!/usr/bin/env python3
"""
FastAPI service for the personal AI agent with observability and basic auth.
Run: uvicorn server:app --host 0.0.0.0 --port 8000
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ValidationError

from dotenv import load_dotenv
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
PRIORITY_ORDER = {"low": 0, "normal": 1, "high": 2, "critical": 3}


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
    if health_server is not None:
        health_server.shutdown()
        if hasattr(health_server, "server_close"):
            health_server.server_close()


app = FastAPI(title="Personal AI Agent", version="1.0.0", lifespan=lifespan)
_agent = None


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


class FlightStreamFilters(BaseModel):
    flight_ids: List[str] = Field(default_factory=list)
    event_types: List[str] = Field(default_factory=list)
    scenarios: List[Literal["precision", "stealth-edge"]] = Field(default_factory=list)
    priorities: List[Literal["low", "normal", "high", "critical"]] = Field(default_factory=list)
    min_priority: Optional[Literal["low", "normal", "high", "critical"]] = None

    def matches(self, event: "FlightEvent") -> bool:
        if self.flight_ids and event.flight_id not in self.flight_ids:
            return False
        if self.event_types and event.event_type not in self.event_types:
            return False
        if self.scenarios and event.scenario not in self.scenarios:
            return False
        if self.priorities and event.priority not in self.priorities:
            return False
        if self.min_priority and PRIORITY_ORDER[event.priority] < PRIORITY_ORDER[self.min_priority]:
            return False
        return True


class FlightEvent(BaseModel):
    flight_id: str = Field(..., description="Flight identifier used to route stream updates.")
    event_type: str = Field(..., description="Update type such as position_update or status_change.")
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    scenario: Optional[Literal["precision", "stealth-edge"]] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Dict[str, Any] = Field(default_factory=dict)


class FlightEventPublishResponse(BaseModel):
    accepted: bool
    sequence: int
    delivered_subscribers: int


@dataclass
class FlightStreamConnection:
    websocket: WebSocket
    filters: FlightStreamFilters
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=100))


class FlightStreamManager:
    def __init__(self) -> None:
        self._connections: Dict[int, FlightStreamConnection] = {}
        self._lock = asyncio.Lock()
        self._sequence = 0

    async def connect(
        self, websocket: WebSocket, filters: FlightStreamFilters
    ) -> FlightStreamConnection:
        connection = FlightStreamConnection(websocket=websocket, filters=filters)
        async with self._lock:
            self._connections[id(websocket)] = connection
        return connection

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.pop(id(websocket), None)

    async def update_filters(self, websocket: WebSocket, filters: FlightStreamFilters) -> None:
        async with self._lock:
            connection = self._connections.get(id(websocket))
            if connection is not None:
                connection.filters = filters

    async def publish(self, event: FlightEvent) -> tuple[Dict[str, Any], int]:
        async with self._lock:
            self._sequence += 1
            sequence = self._sequence
            connections = list(self._connections.values())

        payload = jsonable_encoder(
            {
                "type": "flight_event",
                "sequence": sequence,
                "published_at": datetime.now(timezone.utc),
                **_model_to_dict(event),
            }
        )
        delivered = 0

        for connection in connections:
            if not connection.filters.matches(event):
                continue
            if connection.queue.full():
                try:
                    connection.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                connection.queue.put_nowait(payload)
                delivered += 1
            except asyncio.QueueFull:
                continue

        return payload, delivered


flight_stream_manager = FlightStreamManager()


def get_agent():
    global _agent
    if _agent is None:
        from agent import create_agent

        _agent = create_agent()
    return _agent


def _parse_csv_values(raw_value: Optional[str]) -> List[str]:
    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _filters_from_query_params(query_params) -> FlightStreamFilters:
    return FlightStreamFilters(
        flight_ids=_parse_csv_values(query_params.get("flight_ids")),
        event_types=_parse_csv_values(query_params.get("event_types")),
        scenarios=_parse_csv_values(query_params.get("scenarios")),
        priorities=_parse_csv_values(query_params.get("priorities")),
        min_priority=query_params.get("min_priority"),
    )


def _model_to_dict(model: BaseModel) -> Dict[str, Any]:
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


async def require_websocket_api_key(websocket: WebSocket) -> bool:
    if AUTH_DISABLED:
        return True
    if not API_AUTH_TOKEN:
        await websocket.close(code=1011, reason="API_AUTH_TOKEN is not configured")
        return False

    provided = websocket.headers.get("x-api-key") or websocket.query_params.get("api_key")
    if provided != API_AUTH_TOKEN:
        record_security_event("unauthorized_request")
        audit_event(
            "unauthorized_request",
            {
                "client": websocket.client.host if websocket.client else "unknown",
                "path": websocket.url.path,
            },
        )
        await websocket.close(code=1008, reason="Unauthorized")
        return False
    return True


async def pump_flight_events(connection: FlightStreamConnection) -> None:
    while True:
        payload = await connection.queue.get()
        await connection.websocket.send_json(payload)


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

    audit_event("query", {"query_length": len(request.prompt), "source": "api"})
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
                "outcome": "success",
                "source": "api",
                "response_length": len(reply),
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
                "outcome": "error",
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



@app.post("/v1/flight-events", response_model=FlightEventPublishResponse)
async def publish_flight_event(
    event: FlightEvent, _: None = Depends(require_api_key)
) -> JSONResponse:
    payload, delivered = await flight_stream_manager.publish(event)
    audit_event(
        "flight_event_published",
        {
            "flight_id": event.flight_id,
            "event_type": event.event_type,
            "priority": event.priority,
            "scenario": event.scenario,
            "delivered_subscribers": delivered,
            "sequence": payload["sequence"],
        },
    )
    return JSONResponse(
        content={
            "accepted": True,
            "sequence": payload["sequence"],
            "delivered_subscribers": delivered,
        }
    )


@app.websocket("/ws/flight-events")
async def websocket_flight_events(websocket: WebSocket) -> None:
    if not await require_websocket_api_key(websocket):
        return

    try:
        filters = _filters_from_query_params(websocket.query_params)
    except ValidationError:
        await websocket.close(code=1008, reason="Invalid subscription filters")
        return

    await websocket.accept()
    connection = await flight_stream_manager.connect(websocket, filters)
    sender_task = asyncio.create_task(pump_flight_events(connection))

    encoded_filters = jsonable_encoder(_model_to_dict(filters))
    await websocket.send_json({"type": "subscribed", "filters": encoded_filters})
    audit_event(
        "flight_stream_subscribed",
        {
            "client": websocket.client.host if websocket.client else "unknown",
            "filters": encoded_filters,
        },
    )

    try:
        while True:
            try:
                raw_message = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "detail": "Subscription messages must be valid JSON."}
                )
                continue

            action = message.get("action", "subscribe")
            if action == "subscribe":
                try:
                    filters = FlightStreamFilters(**message.get("filters", {}))
                except ValidationError:
                    await websocket.send_json(
                        {"type": "error", "detail": "Invalid subscription filters."}
                    )
                    continue
                await flight_stream_manager.update_filters(websocket, filters)
                await websocket.send_json(
                    {"type": "subscribed", "filters": jsonable_encoder(_model_to_dict(filters))}
                )
            elif action == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json(
                    {"type": "error", "detail": f"Unsupported websocket action: {action}"}
                )
    finally:
        sender_task.cancel()
        with suppress(asyncio.CancelledError):
            await sender_task
        await flight_stream_manager.disconnect(websocket)
        audit_event(
            "flight_stream_disconnected",
            {"client": websocket.client.host if websocket.client else "unknown"},
        )
