"""Alerting rules (Role 3 – Shi Wang). Each test is one acceptance criterion from Part 1, Table 4, or a rule from Part 2, Figure 4."""
from datetime import datetime, timedelta, timezone

from shared.alert_service import AlertService
from shared.alerting import process_batch, DOOR_LIMIT_S
from shared.fleet_watcher import check_fleet
from shared.models import AlertStatus, AlertType, iso
from shared.repository import InMemoryFleetRepository

T0 = datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, alert):
        self.sent.append(alert)
        return {"channel": "email", "to": "cold-chain-ops@greenops.local"}


def reading(truck="TRK-001", t=T0, temp=4.2, hum=60, door=False, cargo=None, lim=None, lat=45.4215, lon=-75.6972, eta=None, route=None):
    from shared.reference import fleet, cargo_profiles
    registered = next(t for t in fleet()["trucks"] if t["truck_id"] == truck)
    cargo = cargo or registered["cargo_type"]
    route = route or registered["route_id"]
    lim = lim or (cargo_profiles()[cargo]["temp_min_c"], cargo_profiles()[cargo]["temp_max_c"])
    return {"truck_id": truck, "route_id": route, "timestamp": iso(t), "lat": lat, "lon": lon, "speed_kmh": 80, "temp_c": temp,
            "humidity_pct": hum, "door_open": door, "cargo_type": cargo, "temp_min_c": lim[0], "temp_max_c": lim[1],
            "scheduled_eta": iso(eta or T0 + timedelta(hours=4))}


def setup():
    repo, notifier = InMemoryFleetRepository(), FakeNotifier()
    return repo, notifier, AlertService(repo, notifier)


def test_normal_reading_is_stored_and_raises_nothing():
    repo, notifier, svc = setup()
    process_batch([reading()], repo, svc, now=T0)
    assert len(repo.readings) == 1 and repo.alerts == {} and notifier.sent == []
    assert repo.latest_readings()[0]["temp_c"] == 4.2


def test_vaccine_above_8_degrees_gives_one_alert_and_one_email():  # FR-05, FR-06, Table 4
    repo, notifier, svc = setup()
    process_batch([reading(temp=8.6)], repo, svc, now=T0)
    alerts = list(repo.alerts.values())
    assert [a.type for a in alerts] == ["TEMPERATURE"] and alerts[0].status == "ACTIVE"
    assert len(notifier.sent) == 1 and alerts[0].email_sent_at is not None
    assert len(repo.notifications) == 1


def test_ongoing_breach_does_not_send_more_emails():  # de-duplication, Part 2 Figure 4 part C
    repo, notifier, svc = setup()
    for i in range(30):  # five minutes of 10-second readings above the limit
        process_batch([reading(t=T0 + timedelta(seconds=10 * i), temp=9 + i * 0.1)], repo, svc, now=T0 + timedelta(seconds=10 * i))
    assert len(repo.alerts) == 1 and len(notifier.sent) == 1
    a = next(iter(repo.alerts.values()))
    assert a.last_seen_at == iso(T0 + timedelta(seconds=290))


def test_breach_clears_when_the_reading_is_back_in_range():
    repo, notifier, svc = setup()
    process_batch([reading(temp=9)], repo, svc, now=T0)
    process_batch([reading(t=T0 + timedelta(seconds=10), temp=5)], repo, svc, now=T0 + timedelta(seconds=10))
    a = next(iter(repo.alerts.values()))
    assert a.status == "RESOLVED" and a.resolved_at == iso(T0 + timedelta(seconds=10))


def test_a_new_breach_after_recovery_is_a_new_alert():
    repo, notifier, svc = setup()
    for i, temp in enumerate([9, 5, 9.5]):
        process_batch([reading(t=T0 + timedelta(seconds=10 * i), temp=temp)], repo, svc, now=T0 + timedelta(seconds=10 * i))
    assert len(repo.alerts) == 2 and len(notifier.sent) == 2


def test_temperature_below_the_minimum_is_also_a_breach():
    repo, notifier, svc = setup()
    process_batch([reading(temp=1.2)], repo, svc, now=T0)
    assert [a.type for a in repo.alerts.values()] == ["TEMPERATURE"]


def test_limits_come_from_each_cargo_type():  # FR-05, F10
    repo, notifier, svc = setup()
    process_batch([reading(truck="TRK-004", cargo="frozen_food", lim=(-25, -15), temp=-20)], repo, svc, now=T0)
    process_batch([reading(truck="TRK-005", cargo="frozen_food", lim=(-25, -15), temp=-10)], repo, svc, now=T0)
    assert [(a.truck_id, a.type) for a in repo.alerts.values()] == [("TRK-005", "TEMPERATURE")]


def test_humidity_above_the_cargo_limit_raises_a_humidity_alert():
    repo, notifier, svc = setup()
    process_batch([reading(hum=82)], repo, svc, now=T0)  # vaccines: humidity_max_pct 75
    assert [a.type for a in repo.alerts.values()] == ["HUMIDITY"]


def test_door_open_for_120_seconds_or_less_is_not_an_alert():  # FR-07
    repo, notifier, svc = setup()
    for s in range(0, DOOR_LIMIT_S + 1, 10):
        process_batch([reading(t=T0 + timedelta(seconds=s), door=True)], repo, svc, now=T0 + timedelta(seconds=s))
    assert repo.alerts == {}


def test_door_open_longer_than_120_seconds_gives_one_alert():  # FR-07, Table 4
    repo, notifier, svc = setup()
    for s in range(0, 300, 10):
        process_batch([reading(t=T0 + timedelta(seconds=s), door=True)], repo, svc, now=T0 + timedelta(seconds=s))
    assert [a.type for a in repo.alerts.values()] == ["DOOR_OPEN"] and len(notifier.sent) == 1


def test_closing_the_door_resets_the_timer():
    repo, notifier, svc = setup()
    plan = [True] * 10 + [False] + [True] * 10  # 100 s open, closed, 100 s open
    for i, door in enumerate(plan):
        process_batch([reading(t=T0 + timedelta(seconds=10 * i), door=door)], repo, svc, now=T0 + timedelta(seconds=10 * i))
    assert repo.alerts == {}


def test_truck_silent_for_five_minutes_is_flagged_offline_once():  # FR-08, Table 4
    repo, notifier, svc = setup()
    process_batch([reading()], repo, svc, now=T0)
    for minute in range(1, 9):
        check_fleet(repo, svc, now=T0 + timedelta(minutes=minute), offline_after_s=300)
    offline = [a for a in repo.alerts.values() if a.type == "OFFLINE" and a.truck_id == "TRK-001"]
    assert len(offline) == 1 and offline[0].started_at == iso(T0 + timedelta(minutes=6)) and len([a for a in notifier.sent if a.truck_id == "TRK-001"]) == 1


def test_offline_alert_resolves_when_data_arrives_again():
    repo, notifier, svc = setup()
    process_batch([reading()], repo, svc, now=T0)
    check_fleet(repo, svc, now=T0 + timedelta(minutes=6), offline_after_s=300)
    process_batch([reading(t=T0 + timedelta(minutes=7))], repo, svc, now=T0 + timedelta(minutes=7))
    assert next(iter(repo.alerts.values())).status == "RESOLVED"


def test_truck_past_its_eta_and_not_arrived_is_delayed():  # FR-08
    repo, notifier, svc = setup()
    process_batch([reading(eta=T0 + timedelta(minutes=2))], repo, svc, now=T0)
    check_fleet(repo, svc, now=T0 + timedelta(minutes=1), offline_after_s=300)
    assert repo.alerts == {}
    process_batch([reading(t=T0 + timedelta(minutes=3), eta=T0 + timedelta(minutes=2))], repo, svc, now=T0 + timedelta(minutes=3))
    check_fleet(repo, svc, now=T0 + timedelta(minutes=3), offline_after_s=300)
    assert [a.type for a in repo.alerts.values()] == ["DELAYED"]


def test_truck_at_its_destination_is_not_delayed_and_delay_resolves():
    repo, notifier, svc = setup()
    process_batch([reading(eta=T0 - timedelta(minutes=1))], repo, svc, now=T0)
    check_fleet(repo, svc, now=T0, offline_after_s=300)
    process_batch([reading(t=T0 + timedelta(seconds=10), lat=43.6532, lon=-79.3832, eta=T0 - timedelta(minutes=1))], repo, svc, now=T0 + timedelta(seconds=10))
    check_fleet(repo, svc, now=T0 + timedelta(seconds=20), offline_after_s=300)
    assert next(iter(repo.alerts.values())).status == "RESOLVED"


def test_acknowledging_keeps_the_alert_open_but_records_who_and_when():  # FR-11
    repo, notifier, svc = setup()
    process_batch([reading(temp=9)], repo, svc, now=T0)
    a = next(iter(repo.alerts.values()))
    svc.acknowledge(a.id, "Dispatcher (demo)", now=T0 + timedelta(seconds=30))
    a = repo.get_alert(a.id)
    assert a.status == "ACKNOWLEDGED" and a.acknowledged_by == "Dispatcher (demo)"
    process_batch([reading(t=T0 + timedelta(seconds=40), temp=9.4)], repo, svc, now=T0 + timedelta(seconds=40))
    assert len(repo.alerts) == 1 and len(notifier.sent) == 1   # still suppressed after acknowledgement


def test_cannot_acknowledge_a_resolved_alert():
    repo, notifier, svc = setup()
    process_batch([reading(temp=9)], repo, svc, now=T0)
    process_batch([reading(t=T0 + timedelta(seconds=10), temp=5)], repo, svc, now=T0 + timedelta(seconds=10))
    a = next(iter(repo.alerts.values()))
    assert svc.acknowledge(a.id, "x", now=T0) is None and repo.get_alert(a.id).status == "RESOLVED"


def test_batch_with_many_trucks_is_processed_in_time_order():
    repo, notifier, svc = setup()
    batch = [reading(truck=f"TRK-00{i}", t=T0 + timedelta(seconds=s), temp=4) for i in range(1, 7) for s in (10, 0)]
    process_batch(batch, repo, svc, now=T0 + timedelta(seconds=10))
    assert len(repo.readings) == 12
    assert all(r["timestamp"] == iso(T0 + timedelta(seconds=10)) for r in repo.latest_readings())


def test_email_failure_still_records_the_alert():
    repo, _, _ = setup()

    class Broken:
        def send(self, alert):
            raise ConnectionError("mail service down")
    svc = AlertService(repo, Broken())
    process_batch([reading(temp=9)], repo, svc, now=T0)
    a = next(iter(repo.alerts.values()))
    assert a.status == "ACTIVE" and a.email_sent_at is None


# ---- Planned end of a demo run (Role 3 – Shi Wang): a parked truck is not a breakdown
def parked(**kw):
    return {**reading(**kw), "parked": True}


def test_parked_truck_is_not_flagged_offline_or_delayed_and_sends_no_email():
    repo, notifier, svc = setup()
    process_batch([reading(eta=T0 + timedelta(minutes=2))], repo, svc, now=T0)
    process_batch([parked(t=T0 + timedelta(seconds=10), eta=T0 + timedelta(minutes=2))], repo, svc, now=T0 + timedelta(seconds=10))
    for minute in range(1, 30):
        check_fleet(repo, svc, now=T0 + timedelta(minutes=minute), offline_after_s=300)
    assert [a for a in repo.alerts.values() if a.truck_id == "TRK-001"] == []
    assert [a for a in notifier.sent if a.truck_id == "TRK-001"] == []


def test_parking_closes_open_offline_and_delayed_alerts():
    repo, notifier, svc = setup()
    process_batch([reading(eta=T0 - timedelta(minutes=1))], repo, svc, now=T0)
    check_fleet(repo, svc, now=T0, offline_after_s=300)
    assert [a.type for a in repo.alerts.values()] == ["DELAYED"]
    process_batch([parked(t=T0 + timedelta(seconds=10), eta=T0 - timedelta(minutes=1))], repo, svc, now=T0 + timedelta(seconds=10))
    assert all(a.status == "RESOLVED" for a in repo.alerts.values())


def test_a_new_run_unparks_the_truck_so_real_silence_is_offline_again():  # FR-08 still holds during a run
    repo, notifier, svc = setup()
    process_batch([parked()], repo, svc, now=T0)
    restart = T0 + timedelta(hours=1)
    process_batch([reading(t=restart, eta=restart + timedelta(hours=4))], repo, svc, now=restart)
    check_fleet(repo, svc, now=restart + timedelta(minutes=6), offline_after_s=300)
    assert [a.type for a in repo.alerts.values()] == ["OFFLINE"]


def test_parked_flag_must_be_boolean():
    repo, notifier, svc = setup()
    process_batch([{**reading(), "parked": "yes"}], repo, svc, now=T0)
    assert repo.latest_readings() == []
