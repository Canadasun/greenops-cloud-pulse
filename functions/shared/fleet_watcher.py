"""Fleet Watcher logic – runs every minute (Role 3 – Shi Wang; Part 2, Figure 4 part B).

OFFLINE: no reading for offline_after_s (5 minutes, FR-08).  DELAYED: past the scheduled ETA and not at the destination.
"""
import os

from .models import AlertType, parse
from .reference import destination, fleet, km_between

ARRIVED_WITHIN_KM = 1.0


def check_fleet(repo, alerts, now, offline_after_s=None):
    offline_after_s = offline_after_s or int(os.getenv("OFFLINE_AFTER_S", "300"))
    raised = []
    for truck in fleet()["trucks"]:
        state = repo.get_state(truck["truck_id"])
        last = state.get("last_reading")
        if not last:
            continue  # never seen yet
        silent_s = (now - parse(state["last_seen"])).total_seconds()
        if silent_s > offline_after_s:
            a, new = alerts.raise_or_update(truck["truck_id"], AlertType.OFFLINE.value, f"no data for {int(silent_s // 60)} min {int(silent_s % 60)} s", now)
            raised += [a] if new else []
        arrived = km_between((last["lat"], last["lon"]), destination(last["route_id"])) <= ARRIVED_WITHIN_KM
        if arrived:
            alerts.resolve(truck["truck_id"], AlertType.DELAYED.value, now)
        elif now > parse(last["scheduled_eta"]):
            late_min = int((now - parse(last["scheduled_eta"])).total_seconds() // 60)
            a, new = alerts.raise_or_update(truck["truck_id"], AlertType.DELAYED.value, f"{late_min} min past scheduled arrival", now)
            raised += [a] if new else []
    return raised
