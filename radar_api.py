#!/usr/bin/env python3
"""
Airplane / Radar Dashboard API
================================
Provides real-time aircraft tracking, threat analytics, and Palantir-style
entity intelligence via REST endpoints and a WebSocket stream.

Endpoints
---------
GET  /radar/aircraft          – current snapshot of all tracked aircraft
GET  /radar/threats           – ranked threat assessments
GET  /radar/analytics         – aggregated telemetry analytics
GET  /radar/geofences         – active geofence zones
POST /radar/geofences         – create a new geofence
GET  /radar/events            – recent alert/event log
WS   /radar/ws                – real-time push stream (JSON frames @ ~1 Hz)
GET  /dashboard               – serves the HTML ops-center dashboard
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import random
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/radar", tags=["radar"])

STATIC_DIR = Path(__file__).parent / "static"
DASHBOARD_FILE = STATIC_DIR / "radar_dashboard.html"

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

AIRCRAFT_TYPES = [
    "B737", "B738", "B739", "B77W", "B772", "B788", "B789",
    "A319", "A320", "A321", "A332", "A333", "A359", "A35K",
    "C130", "C17",  "F16",  "F22",  "F35",  "E3CF", "P8",
    "MQ9",  "RQ4",  "SR71", "U2",   "RC135",
]

SQUAWK_NORMAL   = [f"{i:04d}" for i in range(1000, 7600, 37)]
SQUAWK_EMERGENCY = ["7500", "7600", "7700"]

AIRLINES = [
    "AAL", "UAL", "DAL", "SWA", "BAW", "DLH", "AFR",
    "UAE", "SIA", "QFA", "KAL", "JAL", "THY", "EZY",
    "USAF", "USN",  "NATO", "UNKN",
]

COUNTRIES = [
    "US", "GB", "DE", "FR", "JP", "CN", "RU", "IN",
    "AU", "BR", "CA", "IL", "IR", "KP", "UA",
]


@dataclass
class Aircraft:
    icao: str          # 6-char hex ICAO 24-bit address
    callsign: str
    aircraft_type: str
    lat: float
    lon: float
    altitude: int      # feet
    speed: int         # knots ground speed
    heading: int       # degrees 0-359
    vertical_rate: int # fpm
    squawk: str
    origin: str        # country of origin
    airline: str
    threat_score: float  # 0.0 – 1.0
    threat_label: str    # CLEAR / MONITOR / SUSPECT / HOSTILE
    signature: str       # radar / adsb / mlat / stealth
    transponder_on: bool
    track: List[tuple]   # last N (lat, lon) positions
    anomalies: List[str]
    first_seen: str
    last_updated: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["track"] = list(self.track)  # deque → list via asdict already handles it
        return d


@dataclass
class GeofenceZone:
    zone_id: str
    name: str
    lat: float
    lon: float
    radius_nm: float   # nautical miles
    alert_level: str   # INFO / WARNING / CRITICAL
    active: bool = True
    triggered_by: List[str] = field(default_factory=list)


@dataclass
class ThreatEvent:
    event_id: str
    timestamp: str
    icao: str
    callsign: str
    event_type: str
    severity: str
    description: str
    lat: float
    lon: float


# ---------------------------------------------------------------------------
# Simulation state
# ---------------------------------------------------------------------------

_aircraft: Dict[str, Aircraft] = {}
_geofences: List[GeofenceZone] = []
_events: deque = deque(maxlen=200)
_ws_clients: List[WebSocket] = []

FLEET_SIZE = 80
TRACK_LENGTH = 40          # position history points per aircraft
UPDATE_HZ = 1.0            # simulation tick rate
_sim_task: Optional[asyncio.Task] = None


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _hex_icao() -> str:
    return "".join(random.choices("0123456789ABCDEF", k=6))


def _random_callsign() -> str:
    airline = random.choice(AIRLINES)
    num = random.randint(1, 9999)
    return f"{airline}{num}"


def _wrap_lon(lon: float) -> float:
    while lon > 180:
        lon -= 360
    while lon < -180:
        lon += 360
    return lon


def _great_circle_step(lat: float, lon: float, heading: int, speed_kts: int) -> tuple:
    """Advance position by one second of flight."""
    dist_nm = speed_kts / 3600.0           # nm per second
    dist_rad = dist_nm / 3438.0            # earth radius ≈ 3438 nm
    hdg_rad = math.radians(heading)
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    new_lat_rad = math.asin(
        math.sin(lat_rad) * math.cos(dist_rad)
        + math.cos(lat_rad) * math.sin(dist_rad) * math.cos(hdg_rad)
    )
    new_lon_rad = lon_rad + math.atan2(
        math.sin(hdg_rad) * math.sin(dist_rad) * math.cos(lat_rad),
        math.cos(dist_rad) - math.sin(lat_rad) * math.sin(new_lat_rad),
    )
    return math.degrees(new_lat_rad), _wrap_lon(math.degrees(new_lon_rad))


def _threat_label(score: float) -> str:
    if score < 0.25:
        return "CLEAR"
    if score < 0.55:
        return "MONITOR"
    if score < 0.80:
        return "SUSPECT"
    return "HOSTILE"


def _compute_threat(ac: Aircraft) -> tuple[float, List[str]]:
    """Heuristic threat scoring with anomaly tags."""
    score = 0.0
    anomalies: List[str] = []

    # Squawk emergency
    if ac.squawk in SQUAWK_EMERGENCY:
        score += 0.4
        anomalies.append(f"SQUAWK-{ac.squawk}")

    # Transponder off
    if not ac.transponder_on:
        score += 0.3
        anomalies.append("XPNDR-OFF")

    # Military type flying in civilian corridor
    mil_types = {"C130", "C17", "F16", "F22", "F35", "E3CF", "P8", "MQ9", "RQ4", "SR71", "U2", "RC135"}
    if ac.aircraft_type in mil_types:
        score += 0.15
        anomalies.append("MIL-ACFT")

    # High-risk origin
    high_risk = {"RU", "CN", "IR", "KP"}
    if ac.origin in high_risk:
        score += 0.2
        anomalies.append(f"ORIGIN-{ac.origin}")

    # Erratic heading (changes >90° between ticks detected elsewhere)
    if "ERRATIC-HDG" in ac.anomalies:
        score += 0.1

    # Geofence breach
    for gz in _geofences:
        if not gz.active:
            continue
        dlat = ac.lat - gz.lat
        dlon = ac.lon - gz.lon
        dist_nm = math.sqrt(dlat**2 + dlon**2) * 60  # approx
        if dist_nm < gz.radius_nm:
            score += 0.25
            anomalies.append(f"GEOFENCE-{gz.name.upper()}")

    # Stealth signature
    if ac.signature == "stealth":
        score += 0.25
        anomalies.append("STEALTH-SIG")

    return min(score, 1.0), anomalies


def _spawn_aircraft() -> Aircraft:
    """Generate a new random aircraft."""
    atype = random.choice(AIRCRAFT_TYPES)
    mil_types = {"C130", "C17", "F16", "F22", "F35", "E3CF", "P8", "MQ9", "RQ4", "SR71", "U2", "RC135"}
    is_mil = atype in mil_types

    airline  = random.choice(["USAF", "USN", "NATO", "UNKN"]) if is_mil else random.choice(AIRLINES[:-4])
    origin   = random.choice(COUNTRIES)
    lat      = random.uniform(-70, 70)
    lon      = random.uniform(-180, 180)
    alt      = random.randint(1000, 45000)
    speed    = random.randint(80 if is_mil else 250, 650)
    heading  = random.randint(0, 359)
    squawk   = (random.choice(SQUAWK_EMERGENCY) if random.random() < 0.015
                else random.choice(SQUAWK_NORMAL))
    xpndr_on = random.random() > 0.05
    sig      = (random.choice(["stealth", "mlat"]) if is_mil and random.random() < 0.2
                else random.choice(["adsb", "mlat", "radar"]))

    now = datetime.now(timezone.utc).isoformat()
    ac = Aircraft(
        icao=_hex_icao(),
        callsign=_random_callsign(),
        aircraft_type=atype,
        lat=lat,
        lon=lon,
        altitude=alt,
        speed=speed,
        heading=heading,
        vertical_rate=random.randint(-2000, 2000),
        squawk=squawk,
        origin=origin,
        airline=airline,
        threat_score=0.0,
        threat_label="CLEAR",
        signature=sig,
        transponder_on=xpndr_on,
        track=deque(maxlen=TRACK_LENGTH),
        anomalies=[],
        first_seen=now,
        last_updated=now,
    )
    ac.track.append((lat, lon))
    score, anomalies = _compute_threat(ac)
    ac.threat_score = score
    ac.threat_label = _threat_label(score)
    ac.anomalies = anomalies
    return ac


def _seed_geofences() -> None:
    zones = [
        GeofenceZone("GF001", "Area 51",         37.23, -115.81, 50,  "CRITICAL"),
        GeofenceZone("GF002", "North Korea",      40.00,  127.00, 300, "CRITICAL"),
        GeofenceZone("GF003", "Strait of Hormuz", 26.50,   56.50, 120, "WARNING"),
        GeofenceZone("GF004", "Black Sea",        43.00,   33.00, 200, "WARNING"),
        GeofenceZone("GF005", "South China Sea",  12.00,  114.00, 400, "WARNING"),
        GeofenceZone("GF006", "Persian Gulf",     26.00,   52.00, 250, "WARNING"),
        GeofenceZone("GF007", "DC Prohibited",    38.90,  -77.04, 15,  "CRITICAL"),
    ]
    _geofences.extend(zones)


def _seed_fleet() -> None:
    for _ in range(FLEET_SIZE):
        ac = _spawn_aircraft()
        _aircraft[ac.icao] = ac


# ---------------------------------------------------------------------------
# Simulation loop
# ---------------------------------------------------------------------------

async def _simulation_loop() -> None:
    """Runs forever, updating aircraft positions and streaming to WS clients."""
    global _aircraft
    tick = 0
    while True:
        start = time.monotonic()
        tick += 1
        now_iso = datetime.now(timezone.utc).isoformat()

        # Occasionally add / remove aircraft to simulate arrivals/departures
        if tick % 30 == 0:
            if len(_aircraft) < FLEET_SIZE + 20:
                ac = _spawn_aircraft()
                _aircraft[ac.icao] = ac
        if tick % 45 == 0 and len(_aircraft) > FLEET_SIZE - 10:
            victim = random.choice(list(_aircraft.keys()))
            del _aircraft[victim]

        # Update each aircraft
        events_this_tick: List[Dict] = []
        for ac in list(_aircraft.values()):
            # Drift heading slightly
            if random.random() < 0.05:
                ac.heading = (ac.heading + random.randint(-15, 15)) % 360

            # Altitude changes
            ac.altitude = max(500, min(50000, ac.altitude + ac.vertical_rate // 3600))
            if random.random() < 0.02:
                ac.vertical_rate = random.randint(-2000, 2000)

            # Move aircraft
            new_lat, new_lon = _great_circle_step(ac.lat, ac.lon, ac.heading, ac.speed)
            ac.lat = new_lat
            ac.lon = new_lon
            ac.track.append((round(new_lat, 5), round(new_lon, 5)))

            # Re-score threat
            prev_label = ac.threat_label
            score, anomalies = _compute_threat(ac)
            ac.threat_score = round(score, 3)
            ac.threat_label = _threat_label(score)
            ac.anomalies = anomalies
            ac.last_updated = now_iso

            # Emit events on threat escalation
            if prev_label != ac.threat_label and ac.threat_label in ("SUSPECT", "HOSTILE"):
                evt = ThreatEvent(
                    event_id=str(uuid.uuid4())[:8],
                    timestamp=now_iso,
                    icao=ac.icao,
                    callsign=ac.callsign,
                    event_type="THREAT_ESCALATION",
                    severity=ac.threat_label,
                    description=(
                        f"{ac.callsign} escalated to {ac.threat_label} "
                        f"[{', '.join(ac.anomalies)}]"
                    ),
                    lat=round(ac.lat, 4),
                    lon=round(ac.lon, 4),
                )
                _events.appendleft(asdict(evt))
                events_this_tick.append(asdict(evt))

        # Build WS frame
        aircraft_list = [_ac_summary(ac) for ac in _aircraft.values()]
        analytics     = _build_analytics()
        frame = {
            "type": "update",
            "tick": tick,
            "timestamp": now_iso,
            "aircraft": aircraft_list,
            "analytics": analytics,
            "new_events": events_this_tick,
        }
        frame_json = json.dumps(frame)

        # Broadcast to connected clients
        disconnected = []
        for ws in _ws_clients:
            try:
                await ws.send_text(frame_json)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            _ws_clients.remove(ws)

        elapsed = time.monotonic() - start
        await asyncio.sleep(max(0, 1.0 / UPDATE_HZ - elapsed))


def _ac_summary(ac: Aircraft) -> Dict[str, Any]:
    """Lightweight dict for WebSocket frames (omit full track for size)."""
    return {
        "icao":          ac.icao,
        "callsign":      ac.callsign,
        "type":          ac.aircraft_type,
        "lat":           round(ac.lat, 5),
        "lon":           round(ac.lon, 5),
        "altitude":      ac.altitude,
        "speed":         ac.speed,
        "heading":       ac.heading,
        "vertical_rate": ac.vertical_rate,
        "squawk":        ac.squawk,
        "origin":        ac.origin,
        "airline":       ac.airline,
        "threat_score":  ac.threat_score,
        "threat_label":  ac.threat_label,
        "signature":     ac.signature,
        "transponder_on": ac.transponder_on,
        "anomalies":     ac.anomalies,
        "track":         list(ac.track)[-10:],  # send last 10 positions
        "last_updated":  ac.last_updated,
    }


def _build_analytics() -> Dict[str, Any]:
    acs = list(_aircraft.values())
    if not acs:
        return {}
    threat_counts = {"CLEAR": 0, "MONITOR": 0, "SUSPECT": 0, "HOSTILE": 0}
    sig_counts: Dict[str, int] = {}
    origin_counts: Dict[str, int] = {}
    for ac in acs:
        threat_counts[ac.threat_label] = threat_counts.get(ac.threat_label, 0) + 1
        sig_counts[ac.signature] = sig_counts.get(ac.signature, 0) + 1
        origin_counts[ac.origin] = origin_counts.get(ac.origin, 0) + 1

    avg_alt   = int(sum(a.altitude for a in acs) / len(acs))
    avg_speed = int(sum(a.speed for a in acs) / len(acs))

    top_origins = sorted(origin_counts.items(), key=lambda x: -x[1])[:5]

    return {
        "total_tracked":    len(acs),
        "threat_breakdown": threat_counts,
        "signature_types":  sig_counts,
        "top_origins":      dict(top_origins),
        "avg_altitude_ft":  avg_alt,
        "avg_speed_kts":    avg_speed,
        "geofence_alerts":  sum(1 for a in acs if any("GEOFENCE" in x for x in a.anomalies)),
        "stealth_contacts":  sum(1 for a in acs if a.signature == "stealth"),
        "emergency_squawks": sum(1 for a in acs if a.squawk in SQUAWK_EMERGENCY),
    }


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------

def radar_startup() -> None:
    """Call this from the FastAPI startup event."""
    _seed_geofences()
    _seed_fleet()


async def radar_startup_async() -> None:
    """Call from async startup to launch background task."""
    global _sim_task
    radar_startup()
    _sim_task = asyncio.create_task(_simulation_loop())


async def radar_shutdown() -> None:
    if _sim_task:
        _sim_task.cancel()


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@router.get("/dashboard", include_in_schema=False)
async def serve_dashboard() -> FileResponse:
    """Serve the HTML ops-center dashboard."""
    return FileResponse(str(DASHBOARD_FILE), media_type="text/html")


@router.get("/aircraft")
async def get_aircraft(
    threat: Optional[str] = None,
    origin: Optional[str] = None,
    limit: int = 200,
) -> JSONResponse:
    """Return current snapshot of tracked aircraft.

    Query params:
    - threat  : filter by threat_label (CLEAR|MONITOR|SUSPECT|HOSTILE)
    - origin  : filter by 2-letter country code
    - limit   : max records returned (default 200)
    """
    results = list(_aircraft.values())
    if threat:
        results = [a for a in results if a.threat_label == threat.upper()]
    if origin:
        results = [a for a in results if a.origin == origin.upper()]
    results = sorted(results, key=lambda a: -a.threat_score)[:limit]
    return JSONResponse({"count": len(results), "aircraft": [_ac_summary(a) for a in results]})


@router.get("/threats")
async def get_threats() -> JSONResponse:
    """Return ranked threat assessments (SUSPECT and HOSTILE contacts)."""
    threats = [
        a for a in _aircraft.values()
        if a.threat_label in ("SUSPECT", "HOSTILE")
    ]
    threats.sort(key=lambda a: -a.threat_score)
    return JSONResponse({
        "count": len(threats),
        "threats": [_ac_summary(a) for a in threats],
    })


@router.get("/analytics")
async def get_analytics() -> JSONResponse:
    """Return aggregated radar analytics."""
    return JSONResponse(_build_analytics())


@router.get("/geofences")
async def get_geofences() -> JSONResponse:
    return JSONResponse({
        "count": len(_geofences),
        "geofences": [asdict(g) for g in _geofences],
    })


@router.post("/geofences")
async def create_geofence(body: Dict[str, Any]) -> JSONResponse:
    """Create a new geofence zone."""
    gz = GeofenceZone(
        zone_id=f"GF{random.randint(100,999)}",
        name=body.get("name", "Custom Zone"),
        lat=float(body["lat"]),
        lon=float(body["lon"]),
        radius_nm=float(body.get("radius_nm", 50)),
        alert_level=body.get("alert_level", "WARNING"),
    )
    _geofences.append(gz)
    return JSONResponse(asdict(gz), status_code=201)


@router.get("/events")
async def get_events(limit: int = 50) -> JSONResponse:
    """Return recent alert/event log."""
    return JSONResponse({
        "count": len(_events),
        "events": list(_events)[:limit],
    })


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws")
async def websocket_stream(ws: WebSocket) -> None:
    """Real-time push stream of aircraft positions and analytics."""
    await ws.accept()
    _ws_clients.append(ws)
    # Send initial full snapshot including track history
    snapshot = {
        "type": "snapshot",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "aircraft": [ac.to_dict() for ac in _aircraft.values()],
        "geofences": [asdict(g) for g in _geofences],
        "analytics": _build_analytics(),
        "events": list(_events)[:50],
    }
    await ws.send_text(json.dumps(snapshot))
    try:
        while True:
            await ws.receive_text()   # keep-alive / command channel
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _ws_clients:
            _ws_clients.remove(ws)
