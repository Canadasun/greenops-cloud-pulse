"""Validate each event independently before it can change live fleet state."""
import json
import math
from datetime import timezone, timedelta

from .models import iso, parse
from .reference import cargo_profiles, fleet

MAX_EVENT_BYTES = 16384


def validate_reading(raw, now):
    if isinstance(raw, bytes):
        if len(raw) > MAX_EVENT_BYTES:
            raise ValueError("event exceeds 16 KiB")
        raw = json.loads(raw)
    if not isinstance(raw, dict):
        raise ValueError("event must be an object")
    if len(json.dumps(raw, default=str).encode()) > MAX_EVENT_BYTES:
        raise ValueError("event exceeds 16 KiB")
    truck = next((t for t in fleet()["trucks"] if t["truck_id"] == raw.get("truck_id")), None)
    if not truck:
        raise ValueError("unknown truck")
    for key in ("route_id", "cargo_type"):
        if raw.get(key) != truck[key]:
            raise ValueError(f"{key} does not match registered truck")
    profile = cargo_profiles()[truck["cargo_type"]]
    msg = {k: raw[k] for k in ("truck_id", "route_id", "cargo_type")}
    for key, low, high in (("lat", -90, 90), ("lon", -180, 180), ("speed_kmh", 0, 200),
                           ("temp_c", -40, 60), ("humidity_pct", 0, 100)):
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"invalid {key}")
        msg[key] = value
    if not isinstance(raw.get("door_open"), bool):
        raise ValueError("door_open must be boolean")
    msg["door_open"] = raw["door_open"]
    for key in ("timestamp", "scheduled_eta"):
        try:
            t = parse(raw[key])
            if t.tzinfo is None:
                raise ValueError("timezone is required")
            msg[key] = iso(t.astimezone(timezone.utc))
        except (KeyError, TypeError, AttributeError, ValueError) as e:
            raise ValueError(f"invalid {key}") from e
    if parse(msg["timestamp"]) > now + timedelta(minutes=2):
        raise ValueError("timestamp is too far in the future")
    # Device-reported limits never control safety decisions. Preserve discrepancies for diagnosis.
    for key in ("temp_min_c", "temp_max_c"):
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"invalid {key}")
        msg[key] = profile[key]
        if value != profile[key]:
            msg.setdefault("reported_limits", {})[key] = value
    if "simulation_time_scale" in raw:
        scale = raw["simulation_time_scale"]
        if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale) or scale < 1:
            raise ValueError("invalid simulation_time_scale")
        msg["simulation_time_scale"] = scale
    return msg
