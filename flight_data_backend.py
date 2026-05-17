#!/usr/bin/env python3
"""
Flight data ingestion, normalization, and analytics backend.

Architecture note
-----------------
This module uses a **process-local, in-memory** store.  In a multi-replica
deployment (e.g. Kubernetes with >1 pod) data written to one pod is NOT visible
to other pods.  This is intentional for the current single-node / dev topology;
switch to a shared-storage backend (Redis, database) before scaling out.
"""
import hashlib
import hmac
import json
import math
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, Iterable, List, Optional


# ---------------------------------------------------------------------------
# Limits (bounded in-memory growth)
# ---------------------------------------------------------------------------

MAX_FLIGHTS = 10_000          # maximum number of distinct flight records kept
MAX_POINTS_PER_FLIGHT = 5_000 # maximum normalised telemetry points per flight


# ---------------------------------------------------------------------------
# Unit-conversion constants
# ---------------------------------------------------------------------------

EARTH_RADIUS_NM = 3440.065
FEET_PER_METER = 3.28084
KNOTS_PER_KMH = 0.539957
KNOTS_PER_MPH = 0.868976
FPM_PER_MPS = 196.850394
LOW_OBSERVABILITY_INDEX = 0.35
NORMAL_OBSERVABILITY_INDEX = 0.8
HIGH_SPEED_THRESHOLD_KTS = 450
LOW_ALTITUDE_THRESHOLD_FT = 10000


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _convert_altitude(value: float, unit: str) -> float:
    if unit == "m":
        return value * FEET_PER_METER
    return value


def _convert_speed(value: float, unit: str) -> float:
    if unit == "kmh":
        return value * KNOTS_PER_KMH
    if unit == "mph":
        return value * KNOTS_PER_MPH
    return value


def _convert_vertical_rate(value: float, unit: str) -> float:
    if unit == "mps":
        return value * FPM_PER_MPS
    return value


def _haversine_nm(
    start_lat: float, start_lon: float, end_lat: float, end_lon: float
) -> float:
    start_lat_rad = math.radians(start_lat)
    start_lon_rad = math.radians(start_lon)
    end_lat_rad = math.radians(end_lat)
    end_lon_rad = math.radians(end_lon)
    delta_lat = end_lat_rad - start_lat_rad
    delta_lon = end_lon_rad - start_lon_rad
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(start_lat_rad)
        * math.cos(end_lat_rad)
        * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_NM * math.asin(math.sqrt(haversine))


def _mask_identifier(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    if len(value) <= 3:
        return "*" * len(value)
    return "*" * (len(value) - 3) + value[-3:]


def _normalize_point(point: Dict[str, object], previous: Optional[Dict[str, object]]) -> Dict[str, object]:
    timestamp = _parse_timestamp(str(point["timestamp"]))
    latitude = float(point["latitude"])
    longitude = float(point["longitude"])
    altitude_ft = _convert_altitude(
        float(point["altitude"]), str(point.get("altitude_unit", "ft")).lower()
    )
    speed_kts = _convert_speed(
        float(point["speed"]), str(point.get("speed_unit", "kts")).lower()
    )
    heading_deg = float(point["heading"]) % 360
    transponder = str(point.get("transponder", "unknown")).lower()
    signature = point.get("signature")
    signature_score = None if signature is None else min(max(float(signature), 0.0), 1.0)

    vertical_rate = point.get("vertical_rate")
    if vertical_rate is not None:
        vertical_rate_fpm = _convert_vertical_rate(
            float(vertical_rate), str(point.get("vertical_rate_unit", "fpm")).lower()
        )
    elif previous:
        previous_timestamp = _parse_timestamp(str(previous["timestamp"]))
        elapsed_seconds = (timestamp - previous_timestamp).total_seconds()
        if elapsed_seconds > 0:
            vertical_rate_fpm = (
                (altitude_ft - float(previous["altitude_ft"])) / elapsed_seconds
            ) * 60
        else:
            vertical_rate_fpm = 0.0
    else:
        vertical_rate_fpm = 0.0

    return {
        "timestamp": _isoformat_utc(timestamp),
        "latitude": round(latitude, 6),
        "longitude": round(longitude, 6),
        "altitude_ft": round(altitude_ft, 2),
        "speed_kts": round(speed_kts, 2),
        "heading_deg": round(heading_deg, 2),
        "vertical_rate_fpm": round(vertical_rate_fpm, 2),
        "transponder": transponder,
        "signature_score": signature_score,
        "source": str(point.get("source", "unknown")),
    }


def _visibility_profile(points: Iterable[Dict[str, object]], stealth_mode: bool) -> Dict[str, object]:
    signatures = [
        float(point["signature_score"])
        for point in points
        if point.get("signature_score") is not None
    ]
    average_signature = round(sum(signatures) / len(signatures), 3) if signatures else None
    transponder_silent = any(point["transponder"] == "off" for point in points)
    observability_index = average_signature if average_signature is not None else (
        LOW_OBSERVABILITY_INDEX
        if stealth_mode or transponder_silent
        else NORMAL_OBSERVABILITY_INDEX
    )
    return {
        "stealth_mode": stealth_mode,
        "average_signature_score": average_signature,
        "observability_index": round(observability_index, 3),
        "transponder_silent": transponder_silent,
        "identifier_redacted": stealth_mode,
    }


def _build_analytics(points: List[Dict[str, object]], stealth_mode: bool) -> Dict[str, object]:
    total_distance_nm = 0.0
    for current, following in zip(points, points[1:]):
        total_distance_nm += _haversine_nm(
            float(current["latitude"]),
            float(current["longitude"]),
            float(following["latitude"]),
            float(following["longitude"]),
        )

    average_speed = sum(float(point["speed_kts"]) for point in points) / len(points)
    min_altitude = min(float(point["altitude_ft"]) for point in points)
    max_altitude = max(float(point["altitude_ft"]) for point in points)
    max_climb = max(float(point["vertical_rate_fpm"]) for point in points)
    min_climb = min(float(point["vertical_rate_fpm"]) for point in points)
    alert_flags = []

    if any(
        float(point["speed_kts"]) > HIGH_SPEED_THRESHOLD_KTS
        and float(point["altitude_ft"]) < LOW_ALTITUDE_THRESHOLD_FT
        for point in points
    ):
        alert_flags.append("high_speed_low_altitude")
    if any(point["transponder"] == "off" for point in points):
        alert_flags.append("transponder_silent")

    visibility = _visibility_profile(points, stealth_mode)
    if visibility["observability_index"] <= LOW_OBSERVABILITY_INDEX:
        alert_flags.append("low_observability_profile")

    return {
        "trajectory_overlay": {
            "samples": len(points),
            "total_distance_nm": round(total_distance_nm, 3),
            "bounding_box": {
                "min_latitude": min(float(point["latitude"]) for point in points),
                "max_latitude": max(float(point["latitude"]) for point in points),
                "min_longitude": min(float(point["longitude"]) for point in points),
                "max_longitude": max(float(point["longitude"]) for point in points),
            },
        },
        "performance_overlay": {
            "average_speed_kts": round(average_speed, 2),
            "min_altitude_ft": round(min_altitude, 2),
            "max_altitude_ft": round(max_altitude, 2),
            "max_climb_rate_fpm": round(max_climb, 2),
            "max_descent_rate_fpm": round(min_climb, 2),
        },
        "observability_overlay": visibility,
        "alert_overlay": alert_flags,
    }


def _serialize_point(point: Dict[str, object], stealth_mode: bool) -> Dict[str, object]:
    serialized = dict(point)
    if stealth_mode:
        serialized["latitude"] = round(float(serialized["latitude"]), 2)
        serialized["longitude"] = round(float(serialized["longitude"]), 2)
    return serialized


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class FlightDataService:
    """Thread-safe, in-memory flight data store.

    Bounded by ``MAX_FLIGHTS`` total entries and ``MAX_POINTS_PER_FLIGHT``
    telemetry points per flight.  Oldest flights are evicted when the flight
    limit is reached (LRU-style via insertion-order dict).

    Signing key is **required** – pass the value of the
    ``FLIGHT_DATA_SIGNING_KEY`` environment variable.
    """

    def __init__(self, signing_key: str) -> None:
        if not signing_key:
            raise ValueError(
                "signing_key is required; set FLIGHT_DATA_SIGNING_KEY in the environment."
            )
        self._signing_key = signing_key.encode("utf-8")
        self._store: Dict[str, Dict[str, object]] = {}
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Integrity
    # ------------------------------------------------------------------

    def _integrity_hash(self, payload: Dict[str, object]) -> str:
        """HMAC-SHA256 of the *serialised* payload using the configured signing key."""
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        return hmac.new(self._signing_key, serialized, hashlib.sha256).hexdigest()

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------

    def ingest(self, payload: Dict[str, object]) -> Dict[str, object]:
        """Normalise and store a batch of telemetry points, returning the snapshot."""
        raw_points = list(payload["points"])
        if not raw_points:
            raise ValueError("points must include at least one sample")

        # Sort incoming points by timestamp so rates and latest_state are correct
        # even when a batch arrives out of order.
        raw_points.sort(key=lambda p: _parse_timestamp(str(p["timestamp"])))

        stealth_mode = bool(payload.get("stealth_mode", False))
        normalized_points: List[Dict[str, object]] = []
        previous_point: Optional[Dict[str, object]] = None
        for point in raw_points:
            normalized = _normalize_point(point, previous_point)
            normalized_points.append(normalized)
            previous_point = normalized

        analytics = _build_analytics(normalized_points, stealth_mode)

        # latest_state is derived from the point with the highest timestamp
        # (already guaranteed by the sort above – last element is newest).
        latest_state = _serialize_point(normalized_points[-1], stealth_mode)

        flight_id = str(payload["flight_id"])

        # Stealth: exclude metadata to prevent identifier leakage through
        # arbitrary client-supplied fields.
        if stealth_mode:
            metadata: Dict[str, object] = {}
        else:
            metadata = dict(payload.get("metadata", {}))

        snapshot: Dict[str, object] = {
            "flight_id": flight_id,
            "callsign": str(payload["callsign"]) if payload.get("callsign") else None,
            "tail_number": str(payload["tail_number"])
            if payload.get("tail_number")
            else None,
            "aircraft_type": str(payload["aircraft_type"])
            if payload.get("aircraft_type")
            else None,
            "operator": str(payload["operator"]) if payload.get("operator") else None,
            "stealth_mode": stealth_mode,
            "records_ingested": len(normalized_points),
            "latest_state": latest_state,
            "recent_track": [
                _serialize_point(point, stealth_mode) for point in normalized_points[-10:]
            ],
            "analytics": analytics,
            "metadata": metadata,
        }

        # Apply identifier masking before computing the integrity hash so that
        # the hash corresponds to the exact payload that will be returned.
        if stealth_mode:
            snapshot["callsign"] = _mask_identifier(snapshot["callsign"])  # type: ignore[arg-type]
            snapshot["tail_number"] = _mask_identifier(snapshot["tail_number"])  # type: ignore[arg-type]

        snapshot["security"] = {
            "data_classification": "restricted" if stealth_mode else "internal",
            "integrity_hash": self._integrity_hash(snapshot),
            "identifier_redacted": stealth_mode,
        }

        with self._lock:
            existing = self._store.get(flight_id)
            stored_snapshot = dict(snapshot)

            if existing:
                # Merge with existing point history, cap at MAX_POINTS_PER_FLIGHT
                prior_points: List[Dict[str, object]] = existing.get("normalized_points", [])  # type: ignore[assignment]
                merged = prior_points + normalized_points
                stored_snapshot["normalized_points"] = merged[-MAX_POINTS_PER_FLIGHT:]
            else:
                stored_snapshot["normalized_points"] = normalized_points[-MAX_POINTS_PER_FLIGHT:]
                # Evict oldest entry if the flight limit is reached
                if len(self._store) >= MAX_FLIGHTS:
                    oldest_key = next(iter(self._store))
                    del self._store[oldest_key]

            self._store[flight_id] = stored_snapshot

        return self._build_public_view(flight_id)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_flight(self, flight_id: str) -> Dict[str, object]:
        with self._lock:
            if flight_id not in self._store:
                raise KeyError(flight_id)
            stored = dict(self._store[flight_id])

        stored.pop("normalized_points", None)
        return stored

    def list_flights(self) -> List[Dict[str, object]]:
        with self._lock:
            flight_ids = sorted(self._store)
        return [self._build_public_view(fid) for fid in flight_ids if fid in self._store]

    def _build_public_view(self, flight_id: str) -> Dict[str, object]:
        with self._lock:
            if flight_id not in self._store:
                raise KeyError(flight_id)
            stored = dict(self._store[flight_id])
        stored.pop("normalized_points", None)
        return stored
