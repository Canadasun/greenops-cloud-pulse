"""Logic behind the read-only Fleet API (Role 5 – Idowu Ayeni; Part 2, Figure 5 FleetApi, Figure 8 wireframe)."""
from datetime import timedelta

from .models import AlertType, iso, parse
from .reference import fleet

BREACH = {AlertType.TEMPERATURE.value, AlertType.HUMIDITY.value}
WARNING = {AlertType.DOOR_OPEN.value, AlertType.DELAYED.value}
FREE_DAILY = 8000


def _status(open_types, has_data):
    if not has_data:
        return "waiting"
    if AlertType.OFFLINE.value in open_types:
        return "offline"
    if open_types & BREACH:
        return "breach"
    if open_types & WARNING:
        return "warning"
    return "normal"


def trucks_view(repo, now):
    latest = {r["truck_id"]: r for r in repo.latest_readings()}
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
                "destination": route["destination"], "status": _status(types, r is not None), "open_alerts": sorted(types)}
        if r:
            item.update({k: r[k] for k in ("lat", "lon", "speed_kmh", "temp_c", "humidity_pct", "door_open", "temp_min_c", "temp_max_c", "scheduled_eta")})
            item.update(last_seen=r["timestamp"], seconds_ago=int((now - parse(r["timestamp"])).total_seconds()))
        out.append(item)
    return out


def routes_view():
    return {rid: {"origin": r["origin"], "destination": r["destination"], "waypoints": r["waypoints"]} for rid, r in fleet()["routes"].items()}


def history_view(repo, truck_id, hours, now):
    pts = repo.history(truck_id, now - timedelta(hours=hours))
    lim = pts[-1] if pts else next((r for r in repo.latest_readings() if r["truck_id"] == truck_id), {})
    return {"truck_id": truck_id, "hours": hours, "temp_min_c": lim.get("temp_min_c"), "temp_max_c": lim.get("temp_max_c"),
            "points": [{"timestamp": p["timestamp"], "temp_c": p["temp_c"], "humidity_pct": p["humidity_pct"], "door_open": p["door_open"]} for p in pts]}


def alerts_view(repo, limit=50, status=None):
    return [a.to_doc() for a in repo.list_alerts(limit=limit, status=status)]


def acknowledge(alert_service, alert_id, body, now):
    user = (body or {}).get("user", "").strip()
    if not user:
        return 400, {"error": "user is required"}
    alert = alert_service.acknowledge(alert_id, user, now)
    if not alert:
        return 409, {"error": "alert not found or not ACTIVE"}
    return 200, alert.to_doc()


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
    today = [a for a in repo.list_alerts(limit=10_000) if a.started_at >= iso(start)]
    seconds_today = max((now - start).total_seconds(), 60)
    per_day = msgs * 86_400 / seconds_today
    return {"messages_today": msgs, "iot_hub_free_daily_limit": FREE_DAILY, "alerts_today": len(today),
            "emails_today": sum(1 for a in today if a.email_sent_at), "projected_messages_per_day": int(per_day),
            "estimated_monthly_cost_usd": monthly_cost_usd(per_day), "budget_alerts_usd": [1, 5],
            "avg_email_seconds": round(sum(a.email_seconds or 0 for a in today if a.email_seconds is not None) / max(1, sum(1 for a in today if a.email_seconds is not None)), 2)}
