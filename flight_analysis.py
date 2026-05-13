#!/usr/bin/env python3
"""
Flight and event filtering, search, and analytic overlays.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SEARCH_FIELDS = (
    "id",
    "flight_id",
    "callsign",
    "tail",
    "registration",
    "origin",
    "destination",
    "operator",
    "aircraft_type",
    "status",
    "event_type",
    "description",
    "notes",
)
RESERVED_FILTER_KEYS = {
    "text",
    "fields",
    "ranges",
    "tags_any",
    "tags_all",
    "flagged_only",
    "time_range",
    "map_bounds",
    "bounding_box",
    "boolean_fields",
}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _iter_values(value: Any) -> Iterable[Any]:
    if isinstance(value, (list, tuple, set)):
        return value
    if value is None:
        return []
    return [value]


def _to_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _record_text(record: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key, value in record.items():
        if isinstance(value, dict):
            parts.extend(f"{key}:{sub_key}={sub_value}" for sub_key, sub_value in value.items())
        elif isinstance(value, (list, tuple, set)):
            parts.extend(f"{key}:{item}" for item in value)
        else:
            parts.append(f"{key}:{value}")
    return " ".join(parts).lower()


def _match_value(actual: Any, expected: Any) -> bool:
    actual_values = {_normalize_text(item) for item in _iter_values(actual)}
    expected_values = {_normalize_text(item) for item in _iter_values(expected)}
    if not expected_values:
        return True
    return bool(actual_values & expected_values)


def _top_counts(records: Sequence[Dict[str, Any]], field: str, limit: int = 5) -> List[Dict[str, Any]]:
    counts = Counter(
        str(value).strip()
        for record in records
        for value in _iter_values(record.get(field))
        if str(value).strip()
    )
    return [{"value": value, "count": count} for value, count in counts.most_common(limit)]


def _timeline_buckets(records: Sequence[Dict[str, Any]], timestamp_field: str) -> List[Dict[str, Any]]:
    counts: Counter[str] = Counter()
    for record in records:
        parsed = _parse_datetime(record.get(timestamp_field))
        if parsed:
            counts[parsed.strftime("%Y-%m-%dT%H:00:00")] += 1
    return [{"bucket": bucket, "count": count} for bucket, count in sorted(counts.items())]


def _boolean_flag(record: Dict[str, Any], *names: str) -> bool:
    truthy = {"1", "true", "yes", "on"}
    for name in names:
        value = record.get(name)
        if isinstance(value, bool):
            if value:
                return True
            continue
        if _normalize_text(value) in truthy:
            return True
    return False


def build_signal_flags(record: Dict[str, Any]) -> List[str]:
    signals: List[str] = []
    squawk = _normalize_text(record.get("squawk"))
    altitude = _to_float(record.get("altitude"))
    speed = _to_float(record.get("speed"))
    status = _normalize_text(record.get("status"))
    tags = {_normalize_text(tag) for tag in _iter_values(record.get("tags"))}
    callsign = _normalize_text(record.get("callsign"))

    if squawk in {"7500", "7600", "7700"}:
        signals.append(f"emergency_squawk_{squawk}")
    if not callsign:
        signals.append("missing_callsign")
    if altitude is not None and speed is not None and altitude <= 5000 and speed >= 400:
        signals.append("fast_low_altitude")
    if _boolean_flag(record, "transponder_off", "adsb_off", "dark", "stealth"):
        signals.append("dark_flight")
    if status in {"holding", "orbit", "loitering"}:
        signals.append("persistent_loitering")
    if altitude is not None and altitude > 0 and not _normalize_text(record.get("destination")):
        signals.append("airborne_without_destination")
    if tags & {"priority", "suspicious", "watch", "intercept", "surveillance"}:
        signals.append("watchlist_tagged")
    return signals


def filter_flights(flights: Sequence[Dict[str, Any]], filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    filters = filters or {}
    text_query = _normalize_text(filters.get("text"))
    equality_filters = dict(filters.get("fields") or {})
    range_filters = dict(filters.get("ranges") or {})
    boolean_filters = dict(filters.get("boolean_fields") or {})
    time_range = dict(filters.get("time_range") or {})
    bounds = dict(filters.get("map_bounds") or filters.get("bounding_box") or {})
    tags_any = {_normalize_text(tag) for tag in _iter_values(filters.get("tags_any"))}
    tags_all = {_normalize_text(tag) for tag in _iter_values(filters.get("tags_all"))}
    flagged_only = bool(filters.get("flagged_only"))

    for key, value in filters.items():
        if key in RESERVED_FILTER_KEYS:
            continue
        equality_filters.setdefault(key, value)

    start = _parse_datetime(time_range.get("start"))
    end = _parse_datetime(time_range.get("end"))
    time_field = str(time_range.get("field") or "timestamp")
    north = _to_float(bounds.get("north"))
    south = _to_float(bounds.get("south"))
    east = _to_float(bounds.get("east"))
    west = _to_float(bounds.get("west"))

    results: List[Dict[str, Any]] = []
    for flight in flights:
        if text_query and text_query not in _record_text(flight):
            continue

        failed = False
        for field, expected in equality_filters.items():
            if not _match_value(flight.get(field), expected):
                failed = True
                break
        if failed:
            continue

        for field, limits in range_filters.items():
            actual = _to_float(flight.get(field))
            if actual is None:
                failed = True
                break
            minimum = _to_float((limits or {}).get("min"))
            maximum = _to_float((limits or {}).get("max"))
            if minimum is not None and actual < minimum:
                failed = True
                break
            if maximum is not None and actual > maximum:
                failed = True
                break
        if failed:
            continue

        for field, expected in boolean_filters.items():
            if bool(flight.get(field)) is not bool(expected):
                failed = True
                break
        if failed:
            continue

        flight_tags = {_normalize_text(tag) for tag in _iter_values(flight.get("tags"))}
        if tags_any and not (flight_tags & tags_any):
            continue
        if tags_all and not tags_all.issubset(flight_tags):
            continue
        if flagged_only and not build_signal_flags(flight):
            continue

        if start or end:
            timestamp = _parse_datetime(flight.get(time_field))
            if not timestamp:
                continue
            if start and timestamp < start:
                continue
            if end and timestamp > end:
                continue

        latitude = _to_float(flight.get("latitude", flight.get("lat")))
        longitude = _to_float(flight.get("longitude", flight.get("lon", flight.get("lng"))))
        if north is not None and (latitude is None or latitude > north):
            continue
        if south is not None and (latitude is None or latitude < south):
            continue
        if east is not None and (longitude is None or longitude > east):
            continue
        if west is not None and (longitude is None or longitude < west):
            continue

        results.append(dict(flight))
    return results


def search_records(
    flights: Sequence[Dict[str, Any]],
    events: Sequence[Dict[str, Any]],
    query: Optional[str],
    limit: int = 10,
) -> Dict[str, Any]:
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return {"query": "", "results": [], "total_matches": 0}

    terms = [term for term in normalized_query.split() if term]
    ranked: List[Tuple[int, Dict[str, Any]]] = []
    for record_type, records in (("flight", flights), ("event", events)):
        for record in records:
            matched_fields: List[str] = []
            score = 0
            for field, value in record.items():
                haystack = _normalize_text(value)
                if not haystack:
                    continue
                if normalized_query in haystack:
                    score += 5
                    matched_fields.append(field)
                    continue
                matches = sum(1 for term in terms if term in haystack)
                if matches:
                    score += matches
                    matched_fields.append(field)
            if score:
                ranked.append(
                    (
                        score,
                        {
                            "record_type": record_type,
                            "score": score,
                            "matched_fields": sorted(set(matched_fields)),
                            "record": dict(record),
                        },
                    )
                )

    ranked.sort(key=lambda item: (-item[0], item[1]["record_type"]))
    results = [item[1] for item in ranked[:limit]]
    return {"query": normalized_query, "results": results, "total_matches": len(ranked)}


def build_analytic_overlays(
    flights: Sequence[Dict[str, Any]],
    events: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    altitude_bands = {"low": 0, "medium": 0, "high": 0, "unknown": 0}
    speed_bands = {"slow": 0, "cruise": 0, "fast": 0, "unknown": 0}
    threats: List[Dict[str, Any]] = []
    stealth_tracks: List[Dict[str, Any]] = []

    for flight in flights:
        altitude = _to_float(flight.get("altitude"))
        speed = _to_float(flight.get("speed"))
        if altitude is None:
            altitude_bands["unknown"] += 1
        elif altitude < 10000:
            altitude_bands["low"] += 1
        elif altitude < 30000:
            altitude_bands["medium"] += 1
        else:
            altitude_bands["high"] += 1

        if speed is None:
            speed_bands["unknown"] += 1
        elif speed < 200:
            speed_bands["slow"] += 1
        elif speed < 500:
            speed_bands["cruise"] += 1
        else:
            speed_bands["fast"] += 1

        signals = build_signal_flags(flight)
        if signals:
            entry = {
                "id": flight.get("id") or flight.get("flight_id") or flight.get("callsign"),
                "callsign": flight.get("callsign"),
                "signals": signals,
                "risk_score": len(signals),
            }
            threats.append(entry)
            if any(signal in {"dark_flight", "missing_callsign", "fast_low_altitude"} for signal in signals):
                stealth_tracks.append(entry)

    flagged_events = []
    for event in events:
        severity = _normalize_text(event.get("severity"))
        if severity in {"high", "critical"} or _normalize_text(event.get("event_type")) in {
            "intercept",
            "surveillance",
            "airspace_violation",
        }:
            flagged_events.append(dict(event))

    return {
        "summary": {
            "flight_count": len(flights),
            "event_count": len(events),
            "flagged_flights": len(threats),
            "flagged_events": len(flagged_events),
        },
        "hotspots": {
            "origins": _top_counts(flights, "origin"),
            "destinations": _top_counts(flights, "destination"),
            "operators": _top_counts(flights, "operator"),
            "statuses": _top_counts(flights, "status"),
            "event_types": _top_counts(events, "event_type"),
        },
        "altitude_bands": altitude_bands,
        "speed_bands": speed_bands,
        "threat_signals": threats,
        "stealth_tracks": stealth_tracks,
        "event_timeline": _timeline_buckets(events, "timestamp"),
    }


def analyze_flight_operations(
    flights: Sequence[Dict[str, Any]],
    events: Sequence[Dict[str, Any]],
    filters: Optional[Dict[str, Any]] = None,
    search_query: Optional[str] = None,
    search_limit: int = 10,
) -> Dict[str, Any]:
    filtered = filter_flights(flights, filters)
    overlays = build_analytic_overlays(filtered, events)
    search = search_records(filtered, events, search_query, limit=search_limit)
    return {
        "filtered_flights": filtered,
        "search": search,
        "overlays": overlays,
    }
