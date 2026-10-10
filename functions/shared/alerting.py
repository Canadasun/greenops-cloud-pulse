"""Alert Function logic – runs for every batch of readings (Role 3 – Shi Wang; Part 2, Figure 4 part A).

For each reading: store it (Role 4 repository), compare it with its cargo limits (FR-05), check how long the door
has been open (FR-07), then raise, update or resolve alerts through AlertService.
"""
import os

from .models import AlertType, parse, iso
from .reference import cargo_profiles
from .validation import validate_reading

DOOR_LIMIT_S = int(os.getenv("DOOR_LIMIT_S", "120"))


def evaluate(msg, door_open_seconds):
    """Return {alert_type: details} for every problem found in one reading."""
    problems = {}
    profile = cargo_profiles()[msg["cargo_type"]]
    lo, hi = profile["temp_min_c"], profile["temp_max_c"]
    if not lo <= msg["temp_c"] <= hi:
        problems[AlertType.TEMPERATURE.value] = f"{msg['temp_c']:.1f} °C outside {lo}–{hi} °C ({msg['cargo_type']})"
    hum_max = cargo_profiles().get(msg["cargo_type"], {}).get("humidity_max_pct", 100)
    if msg["humidity_pct"] > hum_max:
        problems[AlertType.HUMIDITY.value] = f"humidity {msg['humidity_pct']:.0f} % above {hum_max} %"
    if door_open_seconds is not None and door_open_seconds > DOOR_LIMIT_S:
        problems[AlertType.DOOR_OPEN.value] = f"door open {int(door_open_seconds)} s (limit {DOOR_LIMIT_S} s)"
    return problems


def process_batch(messages, repo, alerts, now):
    readings = []
    for raw in messages:
        try:
            readings.append(validate_reading(raw, now))
        except (ValueError, TypeError, KeyError) as e:
            repo.quarantine_event(raw, str(e), now)
    readings.sort(key=lambda m: parse(m["timestamp"]))
    readings = repo.save_readings(readings)
    created = []
    for msg in readings:
        def apply(tx):
            state = tx.state
            t = parse(msg["timestamp"])
            if state.get("last_seen") and t <= parse(state["last_seen"]):
                return []  # history is retained, but current state and side effects cannot regress
            previous = state.get("last_reading")
            if msg["door_open"]:
                state["door_open_since"] = state.get("door_open_since") or msg["timestamp"]
                door_s = (t - parse(state["door_open_since"])).total_seconds()
            else:
                state["door_open_since"], door_s = None, None
            state["last_seen"], state["last_reading"] = msg["timestamp"], msg
            state.setdefault("activated_at", iso(now))
            found = []
            problems = evaluate(msg, door_s)
            for kind in ("TEMPERATURE", "HUMIDITY", "DOOR_OPEN"):
                if kind in problems:
                    alert, new = alerts.raise_in(tx, kind, problems[kind], now, event_at=t)
                    if new:
                        found.append(alert)
                else:
                    alerts.resolve_in(tx, kind, now)
            if (now - t).total_seconds() <= int(os.getenv("OFFLINE_AFTER_S", "300")):
                alerts.resolve_in(tx, "OFFLINE", now)
            if previous and previous["scheduled_eta"] != msg["scheduled_eta"]:
                alerts.resolve_in(tx, "DELAYED", now)
            # A planned end of run: the truck is parked, so the silence that follows is not a breakdown.
            state["parked_at"] = msg["timestamp"] if msg.get("parked") else None
            if msg.get("parked"):
                alerts.resolve_in(tx, "OFFLINE", now)
                alerts.resolve_in(tx, "DELAYED", now)
            return found
        created.extend(repo.mutate_truck(msg["truck_id"], apply))
    alerts.retry_notifications(now)
    return created
