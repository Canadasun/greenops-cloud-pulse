"""Dashboard API logic (Role 5 – Idowu Ayeni): FR-10 (map, status colours, detail) and FR-11 (history, acknowledge)."""
from datetime import timedelta

from shared import dashboard_api as api
from shared.alerting import process_batch
from shared.fleet_watcher import check_fleet
from test_alerting import T0, FakeNotifier, reading, setup


def test_truck_list_shows_position_readings_and_normal_status():
    repo, _, svc = setup()
    process_batch([reading()], repo, svc, now=T0)
    trucks = api.trucks_view(repo, now=T0 + timedelta(seconds=3))
    t = next(x for x in trucks if x["truck_id"] == "TRK-001")
    assert t["status"] == "normal" and t["seconds_ago"] == 3 and t["origin"] == "Ottawa" and t["destination"] == "Toronto"
    assert {x["truck_id"] for x in trucks} == {f"TRK-00{i}" for i in range(1, 7)}  # unseen trucks are listed as "waiting"
    assert next(x for x in trucks if x["truck_id"] == "TRK-006")["status"] == "waiting"


def test_status_colour_rules():  # breach = red, warning = amber, offline = grey (Part 1, Section 5.5)
    repo, _, svc = setup()
    late = T0 + timedelta(seconds=190)
    process_batch([reading(truck="TRK-001", t=late, temp=9), reading(truck="TRK-002", t=late, cargo="fresh_produce", lim=(1, 6), temp=3, route="TOR-OTT-02")], repo, svc, now=late)
    for s in range(0, 200, 10):
        process_batch([reading(truck="TRK-003", t=T0 + timedelta(seconds=s), door=True, route="MTL-OTT-03")], repo, svc, now=T0 + timedelta(seconds=s))
    process_batch([reading(truck="TRK-004", cargo="frozen_food", lim=(-25, -15), temp=-20, route="OTT-KGN-04")], repo, svc, now=T0)
    check_fleet(repo, svc, now=T0 + timedelta(seconds=200), offline_after_s=150)
    status = {t["truck_id"]: t["status"] for t in api.trucks_view(repo, now=T0 + timedelta(seconds=200))}
    assert status["TRK-001"] == "breach" and status["TRK-002"] == "normal" and status["TRK-003"] == "warning" and status["TRK-004"] == "offline"


def test_history_returns_the_last_hour_in_time_order():  # F4 one-hour chart
    repo, _, svc = setup()
    for m in range(0, 90, 10):
        process_batch([reading(t=T0 + timedelta(minutes=m), temp=4 + m / 100)], repo, svc, now=T0 + timedelta(minutes=m))
    h = api.history_view(repo, "TRK-001", hours=1, now=T0 + timedelta(minutes=80))
    assert [p["timestamp"][11:16] for p in h["points"]] == ["14:20", "14:30", "14:40", "14:50", "15:00", "15:10", "15:20"]
    assert h["temp_min_c"] == 2 and h["temp_max_c"] == 8


def test_alert_list_and_acknowledge():  # FR-11
    repo, _, svc = setup()
    process_batch([reading(temp=9)], repo, svc, now=T0)
    alerts = api.alerts_view(repo)
    assert len(alerts) == 1 and alerts[0]["status"] == "ACTIVE" and alerts[0]["truck_id"] == "TRK-001"
    code, body = api.acknowledge(svc, alerts[0]["id"], {"user": "Dispatcher (demo)"}, now=T0 + timedelta(seconds=20))
    assert code == 200 and body["status"] == "ACKNOWLEDGED" and body["acknowledged_by"] == "Dispatcher (demo)"
    assert api.acknowledge(svc, alerts[0]["id"], {"user": "x"}, now=T0)[0] == 409
    assert api.acknowledge(svc, "alt-missing", {"user": "x"}, now=T0)[0] == 409
    assert api.acknowledge(svc, alerts[0]["id"], {}, now=T0)[0] == 400


def test_health_panel_counts_messages_and_estimates_cost():  # F11
    repo, notifier, svc = setup()
    for i in range(12):
        process_batch([reading(t=T0 + timedelta(seconds=10 * i), temp=9 if i == 5 else 4)], repo, svc, now=T0 + timedelta(seconds=10 * i))
    h = api.health_view(repo, now=T0 + timedelta(minutes=2))
    assert h["messages_today"] == 12 and h["alerts_today"] == 1 and h["emails_today"] == 1
    assert h["iot_hub_free_daily_limit"] == 8000 and h["estimated_monthly_cost_usd"] == 0.0


def test_cost_estimate_for_a_24_7_fleet_matches_the_part_1_report():
    assert api.monthly_cost_usd(messages_per_day=8640 * 10) == 10.65   # 10 trucks 24/7 (Part 1, Appendix B)
    assert api.monthly_cost_usd(messages_per_day=6000) == 0.0          # course use inside the free tier
