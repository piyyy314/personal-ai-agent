#!/usr/bin/env python3
"""
Historical flight tracking primitives for replay and investigation workflows.
"""
from __future__ import annotations

import json
import os
import threading
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import atan2, cos, radians, sin, sqrt
from typing import Any, Dict, List, Optional


EMERGENCY_SQUAWKS = {
    "7500": "hijacking",
    "7600": "radio_failure",
    "7700": "general_emergency",
}


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _isoformat(value: datetime) -> str:
    return _to_utc(value).isoformat().replace("+00:00", "Z")


def _distance_nm(
    first_latitude: float,
    first_longitude: float,
    second_latitude: float,
    second_longitude: float,
) -> float:
    earth_radius_nm = 3440.065
    first_lat = radians(first_latitude)
    second_lat = radians(second_latitude)
    latitude_delta = radians(second_latitude - first_latitude)
    longitude_delta = radians(second_longitude - first_longitude)

    a_value = (
        sin(latitude_delta / 2) ** 2
        + cos(first_lat) * cos(second_lat) * sin(longitude_delta / 2) ** 2
    )
    c_value = 2 * atan2(sqrt(a_value), sqrt(1 - a_value))
    return earth_radius_nm * c_value


@dataclass(frozen=True)
class FlightObservation:
    aircraft_id: str
    timestamp: datetime
    latitude: float
    longitude: float
    altitude_ft: Optional[float] = None
    groundspeed_kts: Optional[float] = None
    heading_deg: Optional[float] = None
    squawk: Optional[str] = None
    event_type: str = "position"
    source: str = "manual"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlightObservation":
        timestamp = str(data["timestamp"]).replace("Z", "+00:00")
        return cls(
            aircraft_id=str(data["aircraft_id"]),
            timestamp=_to_utc(datetime.fromisoformat(timestamp)),
            latitude=float(data["latitude"]),
            longitude=float(data["longitude"]),
            altitude_ft=(
                None if data.get("altitude_ft") is None else float(data["altitude_ft"])
            ),
            groundspeed_kts=(
                None
                if data.get("groundspeed_kts") is None
                else float(data["groundspeed_kts"])
            ),
            heading_deg=(
                None if data.get("heading_deg") is None else float(data["heading_deg"])
            ),
            squawk=None if data.get("squawk") is None else str(data["squawk"]),
            event_type=str(data.get("event_type") or "position"),
            source=str(data.get("source") or "manual"),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "aircraft_id": self.aircraft_id,
            "timestamp": _isoformat(self.timestamp),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude_ft": self.altitude_ft,
            "groundspeed_kts": self.groundspeed_kts,
            "heading_deg": self.heading_deg,
            "squawk": self.squawk,
            "event_type": self.event_type,
            "source": self.source,
            "metadata": dict(self.metadata),
        }


class FlightHistoryStore:
    def __init__(self, storage_path: Optional[str] = None) -> None:
        default_path = os.path.join(os.getcwd(), "data", "flight_history.jsonl")
        self.storage_path = storage_path or os.getenv("FLIGHT_HISTORY_PATH", default_path)
        self._lock = threading.RLock()
        self._timeline: List[FlightObservation] = []
        self._aircraft_index: Dict[str, List[FlightObservation]] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.storage_path):
            return
        with open(self.storage_path, "r", encoding="utf-8") as history_file:
            for line in history_file:
                entry = line.strip()
                if not entry:
                    continue
                self._insert(FlightObservation.from_dict(json.loads(entry)))

    def _insert(self, observation: FlightObservation) -> None:
        aircraft_track = self._aircraft_index.setdefault(observation.aircraft_id, [])
        aircraft_position = bisect_left(
            [item.timestamp for item in aircraft_track], observation.timestamp
        )
        aircraft_track.insert(aircraft_position, observation)

        timeline_position = bisect_left(
            [item.timestamp for item in self._timeline], observation.timestamp
        )
        self._timeline.insert(timeline_position, observation)

    def record(self, observation: FlightObservation) -> Dict[str, Any]:
        serialized = json.dumps(observation.to_dict(), sort_keys=True)
        with self._lock:
            directory = os.path.dirname(self.storage_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(self.storage_path, "a", encoding="utf-8") as history_file:
                history_file.write(serialized + "\n")
            self._insert(observation)
            track = list(self._aircraft_index[observation.aircraft_id])

        return {
            "observation": observation.to_dict(),
            "track_summary": self._track_summary(track),
            "anomalies": self._detect_anomalies(track[-2:]),
        }

    def replay(
        self,
        aircraft_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        interval_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        track = self._filter_track(aircraft_id, start_time, end_time)
        frames = self._sample_track(track, interval_seconds)
        return {
            "aircraft_id": aircraft_id,
            "start_time": _isoformat(track[0].timestamp) if track else None,
            "end_time": _isoformat(track[-1].timestamp) if track else None,
            "frame_count": len(frames),
            "frames": self._frames_with_offsets(frames),
            "segments": self._segments(frames),
            "summary": self._track_summary(track),
            "anomalies": self._detect_anomalies(track),
        }

    def timeline(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        aircraft_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        events = self._filter_timeline(start_time, end_time, aircraft_id)
        tracks: Dict[str, List[FlightObservation]] = {}
        for event in events:
            tracks.setdefault(event.aircraft_id, []).append(event)

        return {
            "event_count": len(events),
            "aircraft_count": len(tracks),
            "events": [event.to_dict() for event in events],
            "tracks": [
                {
                    **self._track_summary(track),
                    "aircraft_id": tracked_aircraft,
                    "anomaly_count": len(self._detect_anomalies(track)),
                }
                for tracked_aircraft, track in sorted(tracks.items())
            ],
            "visual_layers": {
                "activity_windows": self._activity_windows(tracks),
                "altitude_bands": self._altitude_bands(events),
                "event_markers": self._event_markers(events),
            },
        }

    def _filter_track(
        self,
        aircraft_id: str,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
    ) -> List[FlightObservation]:
        with self._lock:
            track = list(self._aircraft_index.get(aircraft_id, []))
        return self._filter(track, start_time, end_time)

    def _filter_timeline(
        self,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        aircraft_id: Optional[str],
    ) -> List[FlightObservation]:
        with self._lock:
            events = (
                list(self._aircraft_index.get(aircraft_id, []))
                if aircraft_id
                else list(self._timeline)
            )
        return self._filter(events, start_time, end_time)

    def _filter(
        self,
        observations: List[FlightObservation],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
    ) -> List[FlightObservation]:
        start_time = None if start_time is None else _to_utc(start_time)
        end_time = None if end_time is None else _to_utc(end_time)
        filtered: List[FlightObservation] = []
        for observation in observations:
            if start_time and observation.timestamp < start_time:
                continue
            if end_time and observation.timestamp > end_time:
                continue
            filtered.append(observation)
        return filtered

    def _sample_track(
        self, track: List[FlightObservation], interval_seconds: Optional[int]
    ) -> List[FlightObservation]:
        if not track or not interval_seconds or interval_seconds <= 0:
            return track

        frames = [track[0]]
        last_included = track[0]
        for observation in track[1:-1]:
            elapsed = (observation.timestamp - last_included.timestamp).total_seconds()
            if elapsed >= interval_seconds:
                frames.append(observation)
                last_included = observation
        if len(track) > 1:
            frames.append(track[-1])
        return frames

    def _frames_with_offsets(
        self, track: List[FlightObservation]
    ) -> List[Dict[str, Any]]:
        if not track:
            return []
        baseline = track[0].timestamp
        frames: List[Dict[str, Any]] = []
        for observation in track:
            frame = observation.to_dict()
            frame["offset_seconds"] = int(
                (observation.timestamp - baseline).total_seconds()
            )
            frames.append(frame)
        return frames

    def _segments(self, track: List[FlightObservation]) -> List[Dict[str, Any]]:
        segments: List[Dict[str, Any]] = []
        for previous, current in zip(track, track[1:]):
            elapsed_seconds = (current.timestamp - previous.timestamp).total_seconds()
            distance_nm = _distance_nm(
                previous.latitude,
                previous.longitude,
                current.latitude,
                current.longitude,
            )
            segment = {
                "start_time": _isoformat(previous.timestamp),
                "end_time": _isoformat(current.timestamp),
                "distance_nm": round(distance_nm, 3),
                "elapsed_seconds": int(elapsed_seconds),
                "altitude_change_ft": None,
                "computed_groundspeed_kts": None,
            }
            if previous.altitude_ft is not None and current.altitude_ft is not None:
                segment["altitude_change_ft"] = round(
                    current.altitude_ft - previous.altitude_ft, 2
                )
            if elapsed_seconds > 0:
                segment["computed_groundspeed_kts"] = round(
                    distance_nm / (elapsed_seconds / 3600), 3
                )
            segments.append(segment)
        return segments

    def _track_summary(self, track: List[FlightObservation]) -> Dict[str, Any]:
        if not track:
            return {
                "position_count": 0,
                "first_seen": None,
                "last_seen": None,
                "estimated_distance_nm": 0.0,
                "bounding_box": None,
            }

        latitudes = [observation.latitude for observation in track]
        longitudes = [observation.longitude for observation in track]
        total_distance = sum(
            _distance_nm(previous.latitude, previous.longitude, current.latitude, current.longitude)
            for previous, current in zip(track, track[1:])
        )
        return {
            "position_count": len(track),
            "first_seen": _isoformat(track[0].timestamp),
            "last_seen": _isoformat(track[-1].timestamp),
            "estimated_distance_nm": round(total_distance, 3),
            "bounding_box": {
                "min_latitude": round(min(latitudes), 6),
                "max_latitude": round(max(latitudes), 6),
                "min_longitude": round(min(longitudes), 6),
                "max_longitude": round(max(longitudes), 6),
            },
            "latest_position": track[-1].to_dict(),
        }

    def _detect_anomalies(
        self, track: List[FlightObservation]
    ) -> List[Dict[str, Any]]:
        anomalies: List[Dict[str, Any]] = []
        for observation in track:
            if observation.squawk in EMERGENCY_SQUAWKS:
                anomalies.append(
                    {
                        "type": "emergency_squawk",
                        "severity": "critical",
                        "timestamp": _isoformat(observation.timestamp),
                        "details": {
                            "squawk": observation.squawk,
                            "meaning": EMERGENCY_SQUAWKS[observation.squawk],
                        },
                    }
                )

        for previous, current in zip(track, track[1:]):
            elapsed_seconds = (current.timestamp - previous.timestamp).total_seconds()
            if elapsed_seconds <= 0:
                continue
            distance_nm = _distance_nm(
                previous.latitude,
                previous.longitude,
                current.latitude,
                current.longitude,
            )
            computed_speed = distance_nm / (elapsed_seconds / 3600)
            if computed_speed > 700:
                anomalies.append(
                    {
                        "type": "improbable_speed",
                        "severity": "high",
                        "timestamp": _isoformat(current.timestamp),
                        "details": {
                            "computed_groundspeed_kts": round(computed_speed, 3),
                            "distance_nm": round(distance_nm, 3),
                            "elapsed_seconds": int(elapsed_seconds),
                        },
                    }
                )
            if (
                previous.altitude_ft is not None
                and current.altitude_ft is not None
                and elapsed_seconds <= 300
                and abs(current.altitude_ft - previous.altitude_ft) >= 5000
            ):
                anomalies.append(
                    {
                        "type": "rapid_altitude_change",
                        "severity": "medium",
                        "timestamp": _isoformat(current.timestamp),
                        "details": {
                            "altitude_change_ft": round(
                                current.altitude_ft - previous.altitude_ft, 2
                            ),
                            "elapsed_seconds": int(elapsed_seconds),
                        },
                    }
                )
        return anomalies

    def _activity_windows(
        self, tracks: Dict[str, List[FlightObservation]]
    ) -> List[Dict[str, Any]]:
        windows: List[Dict[str, Any]] = []
        gap_threshold_seconds = 30 * 60
        for aircraft_id, track in sorted(tracks.items()):
            if not track:
                continue
            window_start = track[0]
            previous = track[0]
            event_count = 1
            for current in track[1:]:
                gap = (current.timestamp - previous.timestamp).total_seconds()
                if gap > gap_threshold_seconds:
                    windows.append(
                        {
                            "aircraft_id": aircraft_id,
                            "start_time": _isoformat(window_start.timestamp),
                            "end_time": _isoformat(previous.timestamp),
                            "event_count": event_count,
                        }
                    )
                    window_start = current
                    event_count = 1
                else:
                    event_count += 1
                previous = current
            windows.append(
                {
                    "aircraft_id": aircraft_id,
                    "start_time": _isoformat(window_start.timestamp),
                    "end_time": _isoformat(previous.timestamp),
                    "event_count": event_count,
                }
            )
        return windows

    def _altitude_bands(
        self, events: List[FlightObservation]
    ) -> List[Dict[str, Any]]:
        bands: Dict[str, int] = {}
        for event in events:
            if event.altitude_ft is None:
                band_name = "unknown"
            else:
                band_floor = int(event.altitude_ft // 5000) * 5000
                band_name = f"{band_floor}-{band_floor + 4999}"
            bands[band_name] = bands.get(band_name, 0) + 1
        return [
            {"band": band, "event_count": count}
            for band, count in sorted(bands.items())
        ]

    def _event_markers(
        self, events: List[FlightObservation]
    ) -> List[Dict[str, Any]]:
        markers: List[Dict[str, Any]] = []
        for event in events:
            if event.event_type != "position" or event.squawk in EMERGENCY_SQUAWKS:
                markers.append(
                    {
                        "aircraft_id": event.aircraft_id,
                        "timestamp": _isoformat(event.timestamp),
                        "event_type": event.event_type,
                        "squawk": event.squawk,
                    }
                )
        return markers
