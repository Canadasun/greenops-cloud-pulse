"""Logic behind the read-only Fleet API (Role 5 – Idowu Ayeni; Part 2, Figure 5 FleetApi, Figure 8 wireframe)."""
from datetime import timedelta
import base64
import json
import os

from .models import AlertType, iso, parse
from .fleet_watcher import is_parked
from .reference import fleet, cargo_profiles

BREACH = {AlertType.TEMPERATURE.value, AlertType.HUMIDITY.value}
WARNING = {AlertType.DOOR_OPEN.value, AlertType.DELAYED.value}
FREE_DAILY = 8000


def _status(open_types, has_data, parked=False):
    if AlertType.OFFLINE.value in open_types:
        return "offline"
    if not has_data:
        return "waiting"
    if parked:  # a planned end of a demo run, not a breakdown
        return "parked"
    if open_types & BREACH:
        return "breach"
    if open_types & WARNING:
        return "warning"
    return "normal"


def trucks_view(repo, now):
    latest = {r["truck_id"]: r for r in repo.latest_readings()}
    parked = {s["truck_id"] for s in repo.all_states() if is_parked(s)}
    open_by_truck = {}
    for a in repo.open_alerts():
        open_by_truck.setdefault(a.truck_id, set()).add(a.type)
    out = []
    data = fleet()
    for t in data["trucks"]:
        r = latest.get(t["truck_id"])
        route = data["routes"][t["route_id"]]
        types = open_by_truck.get(t["truck_id"], set())
        item = {"truck_id": t["truck_id"], "route_id": t["route_id"], "cargo_type": t["cargo_type"], "origin": route["origin"],
                "destination": route["destination"], "status": _status(types, r is not None, t["truck_id"] in parked), "open_alerts": sorted(types)}
        item.update({k: cargo_profiles()[t["cargo_type"]][k] for k in ("temp_min_c", "temp_max_c")})
        if r:
            item.update({k: r[k] for k in ("lat", "lon", "speed_kmh", "temp_c", "humidity_pct", "door_open", "temp_min_c", "temp_max_c", "scheduled_eta")})
            item["simulation_time_scale"] = r.get("simulation_time_scale", 1)
            item.update(last_seen=r["timestamp"], seconds_ago=int((now - parse(r["timestamp"])).total_seconds()))
        out.append(item)
    return out


def routes_view():
    return {rid: {"origin": r["origin"], "destination": r["destination"], "waypoints": r["waypoints"]} for rid, r in fleet()["routes"].items()}


def history_view(repo, truck_id, hours, now, max_points=None, offset=0, limit=None):
    start = now - timedelta(hours=hours)
    pts = [p for p in repo.history(truck_id, start) if parse(p["timestamp"]) <= now]
    truck = next(t for t in fleet()["trucks"] if t["truck_id"] == truck_id)
    lim = cargo_profiles()[truck["cargo_type"]]
    total = len(pts)
    # Bucket first/last/min/max retain excursions; retain both sides of every outage.
    # Outage boundaries can exceed the requested budget: correctness takes priority.
    indices = list(range(total))
    if max_points and total > max_points:
        bucket_size = max(1, (total + max_points // 4 - 1) // (max_points // 4))
        chosen = set()
        for left in range(0, total, bucket_size):
            right = min(left + bucket_size, total)
            chunk = range(left, right)
            chosen.update((left, right - 1, min(chunk, key=lambda i: pts[i]["temp_c"]), max(chunk, key=lambda i: pts[i]["temp_c"])))
        for i in range(1, total):
            if (parse(pts[i]["timestamp"]) - parse(pts[i - 1]["timestamp"])).total_seconds() > 90:
                chosen.update((i - 1, i))
        indices = sorted(chosen)
    elif limit is not None:
        indices = indices[offset:offset + limit]
    points = []
    previous = None
    for i in indices:
        p = pts[i]
        point = {k: p[k] for k in ("timestamp", "temp_c", "humidity_pct", "door_open")}
        if max_points:
            point["contiguous"] = previous is not None and all(
                (parse(pts[j]["timestamp"]) - parse(pts[j - 1]["timestamp"])).total_seconds() <= 90
                for j in range(previous + 1, i + 1))
        points.append(point)
        previous = i
    return {"truck_id": truck_id, "hours": hours, "temp_min_c": lim.get("temp_min_c"), "temp_max_c": lim.get("temp_max_c"),
            "window_start": iso(start), "window_end": iso(now), "total_points": total,
            "points": points}


def alerts_view(repo, limit=50, status=None):
    return [a.to_doc() for a in repo.list_alerts(limit=limit, status=status)]


def truck_ids():
    return {t["truck_id"] for t in fleet()["trucks"]}


def alert_page(repo, limit=50, status=None, truck_id=None, cursor=None):
    before = None
    if cursor:
        if len(cursor) > 512:
            raise ValueError("cursor too long")
        try:
            before = json.loads(base64.urlsafe_b64decode(cursor).decode())
            if not isinstance(before, list) or len(before) != 2 or not all(isinstance(v, str) for v in before):
                raise ValueError()
            parse(before[0])
        except Exception as e:
            raise ValueError("invalid cursor") from e
    if status == "OPEN":
        # Bounded by fleet size and alert types, not historical volume. Never truncate active incidents.
        items = sorted((a for a in repo.open_alerts(truck_id)), key=lambda a: (a.started_at, a.id), reverse=True)
        return {"items": [a.to_doc() for a in items], "next_cursor": None}
    items = repo.list_alerts(limit + 1, status, before=before, truck_id=truck_id)
    next_cursor = None
    if len(items) > limit:
        last = items[limit - 1]
        next_cursor = base64.urlsafe_b64encode(json.dumps([last.started_at, last.id]).encode()).decode()
    return {"items": [a.to_doc() for a in items[:limit]], "next_cursor": next_cursor}


def acknowledge(alert_service, alert_id, body, now):
    user = body.get("user", "") if isinstance(body, dict) else ""
    user = user.strip() if isinstance(user, str) else ""
    if not user:
        return 400, {"error": "user is required"}
    alert = alert_service.acknowledge(alert_id, user, now)
    if not alert:
        return 409, {"error": "alert not found or not ACTIVE"}
    return 200, alert.to_doc()


FAULT_SCENARIOS = ("none", "compressor", "door", "delay", "offline")  # same list as the simulator (FR-02)


def faults_view(repo):
    chosen = repo.get_faults()
    return {t["truck_id"]: chosen.get(t["truck_id"], "none") for t in fleet()["trucks"]}


def set_fault(repo, truck_id, body):
    if truck_id not in {t["truck_id"] for t in fleet()["trucks"]}:
        return 404, {"error": f"unknown truck {truck_id}"}
    scenario = body.get("scenario") if isinstance(body, dict) else None
    if scenario not in FAULT_SCENARIOS:
        return 400, {"error": f"scenario must be one of {list(FAULT_SCENARIOS)}"}
    repo.set_fault(truck_id, scenario)
    return 200, {"truck_id": truck_id, "scenario": scenario}


def monthly_cost_usd(messages_per_day):
    """Same model as Part 1, Appendix B: IoT Hub is free up to 8,000 messages a day, otherwise B1 units of 400,000/day at USD 10;
    Functions, Blob and Monitor add about USD 0.65 for a 10-truck 24/7 fleet."""
    if messages_per_day <= FREE_DAILY:
        return 0.0
    units = -(-messages_per_day // 400_000)
    other = 0.65 * (messages_per_day / 86_400)
    return round(10.0 * units + other, 2)


def health_view(repo, now):
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    msgs = repo.count_readings_since(start)
    daily = repo.alert_stats(start)
    seconds_today = max((now - start).total_seconds(), 60)
    per_day = msgs * 86_400 / seconds_today
    sku = os.getenv("IOT_HUB_SKU", "local")
    allowance = 8000 if sku == "F1" else 400000 if sku == "B1" else None
    base_cost = float(os.getenv("IOT_HUB_MONTHLY_USD", "0"))
    return {"messages_today": msgs, "iot_hub_free_daily_limit": FREE_DAILY, **daily,
            "projected_messages_per_day": int(per_day), "iot_hub_sku": sku, "daily_allowance": allowance,
            "capacity_warning": allowance is not None and per_day > allowance,
            "estimated_monthly_cost_usd": base_cost, "cost_note": "Configured IoT Hub base cost only; excludes usage, storage, email and monitoring. Not a billing forecast.",
            "budget_alerts_usd": [1, 5]}
