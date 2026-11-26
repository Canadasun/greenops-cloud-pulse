"""Performance budget (Part 4 – Roles 3, 4 and 5): how many database operations each hot path may use.

A budget is a number the team measured and improved; a change that makes a path chattier again fails here, in CI, instead of
showing up later as a slow dashboard or a Cosmos DB bill."""
from collections import Counter
from datetime import timedelta

import pytest

from shared import dashboard_api as api
from shared.alert_service import AlertService
from shared.alerting import process_batch
from shared.fleet_watcher import check_fleet
from shared.repository import InMemoryFleetRepository
from test_alerting import T0, FakeNotifier, reading
from test_reliability import store  # noqa: F401 – the same checks run in memory and on the Cosmos DB emulator

TRUCKS = [f"TRK-00{i}" for i in range(1, 7)]


def ok(truck, t=T0):
    """A reading inside the limits of this truck's own cargo, so only the path under test uses the database."""
    from shared.reference import cargo_profiles, fleet
    cargo = cargo_profiles()[next(x["cargo_type"] for x in fleet()["trucks"] if x["truck_id"] == truck)]
    return reading(truck=truck, t=t, temp=(cargo["temp_min_c"] + cargo["temp_max_c"]) / 2)


class Counting(InMemoryFleetRepository):
    """Counts the calls that cost a database round trip in the Cosmos DB version."""
    def __init__(self):
        super().__init__()
        self.calls = Counter()

    def __getattribute__(self, name):
        if name in {"mutate_truck", "all_states", "latest_readings", "open_alerts", "fleet_snapshot", "save_readings", "alert_stats",
                    "count_readings_since", "pending_notifications"}:
            object.__getattribute__(self, "calls")[name] += 1
        return object.__getattribute__(self, name)


def fleet_running(repo, now=T0):
    svc = AlertService(repo, FakeNotifier())
    process_batch([ok(t, now) for t in TRUCKS], repo, svc, now)
    repo.calls.clear() if hasattr(repo, "calls") else None
    return svc


def test_fleet_view_reads_the_database_once():
    repo = Counting(); fleet_running(repo)
    assert len(api.trucks_view(repo, T0)) == 6
    assert repo.calls["fleet_snapshot"] == 1
    assert sum(repo.calls.values()) == 1


def test_a_quiet_fleet_check_writes_and_locks_nothing():
    repo = Counting(); svc = fleet_running(repo)
    assert check_fleet(repo, svc, T0 + timedelta(seconds=30)) == []
    assert repo.calls["mutate_truck"] == 0 and repo.calls["fleet_snapshot"] == 1


def test_a_quiet_check_still_catches_the_one_silent_truck():
    repo = Counting(); svc = fleet_running(repo)
    later = T0 + timedelta(minutes=6)
    process_batch([ok(t, later) for t in TRUCKS if t != "TRK-004"], repo, svc, later)
    repo.calls.clear()
    raised = check_fleet(repo, svc, later)
    assert [(a.truck_id, a.type) for a in raised] == [("TRK-004", "OFFLINE")]
    assert repo.calls["mutate_truck"] <= 4  # the alert plus its email claim and result, never one lock per truck


def test_a_batch_commits_once_per_truck_not_once_per_reading():
    repo = Counting(); svc = AlertService(repo, FakeNotifier())
    batch = [ok(t, T0 + timedelta(seconds=10 * i)) for i in range(10) for t in TRUCKS]
    process_batch(batch, repo, svc, T0 + timedelta(seconds=100))
    assert repo.calls["mutate_truck"] == 6 and len(repo.readings) == 60


def test_batching_keeps_every_incident_inside_the_batch(store):  # noqa: F811
    """A breach that starts and ends between two deliveries is still one resolved alert, and a second breach is a second alert."""
    svc = AlertService(store, FakeNotifier())
    temps = [4, 10, 10, 4, 11]
    process_batch([reading(t=T0 + timedelta(seconds=10 * i), temp=t) for i, t in enumerate(temps)], store, svc, T0 + timedelta(seconds=50))
    assert sorted(a.status for a in store.list_alerts()) == ["ACTIVE", "RESOLVED"]


def test_one_bad_truck_does_not_hold_back_the_others(store):  # noqa: F811
    svc = AlertService(store, FakeNotifier())
    process_batch([reading(truck=t) for t in TRUCKS] + [{"truck_id": "TRK-001"}], store, svc, T0)
    assert {r["truck_id"] for r in store.latest_readings()} == set(TRUCKS)


def test_snapshot_matches_the_separate_queries(store):  # noqa: F811
    svc = AlertService(store, FakeNotifier())
    process_batch([reading(truck=t, temp=20 if t == "TRK-003" else 4) for t in ("TRK-001", "TRK-003")], store, svc, T0)
    snap = store.fleet_snapshot()
    assert {t: s["last_seen"] for t, s in snap.states.items()} == {s["truck_id"]: s["last_seen"] for s in store.all_states()}
    assert sorted(a.id for a in snap.open_alerts) == sorted(a.id for a in store.open_alerts())


def test_bulk_save_keeps_the_first_copy_of_a_replayed_reading(store):  # noqa: F811
    first = [reading(t=T0 + timedelta(seconds=10 * i), temp=4) for i in range(3)]
    store.save_readings(first)
    saved = store.save_readings([{**first[1], "temp_c": 99}, reading(t=T0 + timedelta(seconds=40), temp=5)])
    assert [r["temp_c"] for r in saved] == [4, 5] and store.count_readings_since(T0) == 4


@pytest.mark.parametrize("n", [1, 250])
def test_bulk_save_handles_more_than_one_cosmos_batch(store, n):  # noqa: F811 – a Cosmos DB batch takes at most 100 items
    out = store.save_readings([reading(t=T0 + timedelta(seconds=i)) for i in range(n)])
    assert len(out) == n and store.count_readings_since(T0) == n


def test_history_points_carry_only_the_fields_the_chart_needs(store):  # noqa: F811
    store.save_readings([reading()])
    assert set(store.history("TRK-001", T0)[0]) == {"truck_id", "timestamp", "temp_c", "humidity_pct", "door_open"}
