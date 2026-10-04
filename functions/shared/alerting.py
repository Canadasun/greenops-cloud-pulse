"""Alert Function logic – runs for every batch of readings (Role 3 – Shi Wang; Part 2, Figure 4 part A).

For each reading: store it (Role 4 repository), compare it with its cargo limits (FR-05), check how long the door
has been open (FR-07), then raise, update or resolve alerts through AlertService.
"""
import os

from .models import AlertType, parse
from .reference import cargo_profiles

DOOR_LIMIT_S = int(os.getenv("DOOR_LIMIT_S", "120"))


def evaluate(msg, door_open_seconds):
    """Return {alert_type: details} for every problem found in one reading."""
    problems = {}
    lo, hi = msg["temp_min_c"], msg["temp_max_c"]
    if not lo <= msg["temp_c"] <= hi:
        problems[AlertType.TEMPERATURE.value] = f"{msg['temp_c']:.1f} °C outside {lo}–{hi} °C ({msg['cargo_type']})"
    hum_max = cargo_profiles().get(msg["cargo_type"], {}).get("humidity_max_pct", 100)
    if msg["humidity_pct"] > hum_max:
        problems[AlertType.HUMIDITY.value] = f"humidity {msg['humidity_pct']:.0f} % above {hum_max} %"
    if door_open_seconds is not None and door_open_seconds > DOOR_LIMIT_S:
        problems[AlertType.DOOR_OPEN.value] = f"door open {int(door_open_seconds)} s (limit {DOOR_LIMIT_S} s)"
    return problems


def process_batch(messages, repo, alerts, now):
    readings = sorted(messages, key=lambda m: m["timestamp"])
    repo.save_readings(readings)
    created = []
    for msg in readings:
        state = repo.get_state(msg["truck_id"])
        t = parse(msg["timestamp"])
        if msg["door_open"]:
            state["door_open_since"] = state.get("door_open_since") or msg["timestamp"]
            door_s = (t - parse(state["door_open_since"])).total_seconds()
        else:
            state["door_open_since"], door_s = None, None
        state["last_seen"], state["last_reading"] = msg["timestamp"], msg
        repo.save_state(state)

        problems = evaluate(msg, door_s)
        for alert_type in (AlertType.TEMPERATURE.value, AlertType.HUMIDITY.value, AlertType.DOOR_OPEN.value):
            if alert_type in problems:
                alert, new = alerts.raise_or_update(msg["truck_id"], alert_type, problems[alert_type], now)
                if new:
                    created.append(alert)
            else:
                alerts.resolve(msg["truck_id"], alert_type, now)
        alerts.resolve(msg["truck_id"], AlertType.OFFLINE.value, now)  # data is arriving again
    return created
