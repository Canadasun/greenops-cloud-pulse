"""Storage contract (Role 4 – Durmusali Unal): the in-memory and Cosmos DB repositories must behave the same.
The Cosmos tests run when COSMOS_ENDPOINT is set (e.g. the local emulator: http://localhost:8081)."""
import os
import uuid
from datetime import timedelta

import pytest

from shared.models import Alert, iso
from shared.repository import TELEMETRY_TTL_S, InMemoryFleetRepository
from test_alerting import T0, reading

EMULATOR_KEY = "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
kinds = ["memory"] + (["cosmos"] if os.getenv("COSMOS_ENDPOINT") else [])


@pytest.fixture(params=kinds)
def repo(request):
    if request.param == "memory":
        return InMemoryFleetRepository()
    from shared.repository import CosmosFleetRepository
    return CosmosFleetRepository(os.environ["COSMOS_ENDPOINT"], os.getenv("COSMOS_KEY", EMULATOR_KEY), database=f"test-{uuid.uuid4().hex[:8]}")


def test_history_is_filtered_by_truck_and_time_and_sorted(repo):
    repo.save_readings([reading(t=T0 + timedelta(minutes=m)) for m in (30, 0, 10)] + [reading(truck="TRK-002", t=T0)])
    h = repo.history("TRK-001", T0 + timedelta(minutes=5))
    assert [r["timestamp"] for r in h] == [iso(T0 + timedelta(minutes=10)), iso(T0 + timedelta(minutes=30))]


def test_counting_readings_since_a_time(repo):
    repo.save_readings([reading(t=T0 + timedelta(seconds=10 * i)) for i in range(5)])
    assert repo.count_readings_since(T0 + timedelta(seconds=20)) == 3


def test_saving_the_same_reading_twice_keeps_one_copy(repo):  # idempotent: a retried delivery is not duplicated
    repo.save_readings([reading()]); repo.save_readings([reading()])
    assert repo.count_readings_since(T0) == 1


def test_open_alert_lookup_ignores_resolved_alerts(repo):
    old = Alert("TRK-001", "TEMPERATURE", "x", iso(T0), iso(T0), status="RESOLVED")
    new = Alert("TRK-001", "TEMPERATURE", "y", iso(T0), iso(T0))
    repo.save_alert(old); repo.save_alert(new)
    assert repo.find_open("TRK-001", "TEMPERATURE").id == new.id
    assert repo.find_open("TRK-002", "TEMPERATURE") is None
    assert [a.id for a in repo.open_alerts()] == [new.id]


def test_alerts_are_listed_newest_first_and_found_by_id(repo):
    a1 = Alert("TRK-001", "DOOR_OPEN", "x", iso(T0), iso(T0))
    a2 = Alert("TRK-002", "OFFLINE", "y", iso(T0 + timedelta(minutes=1)), iso(T0))
    repo.save_alert(a1); repo.save_alert(a2)
    assert [a.id for a in repo.list_alerts()] == [a2.id, a1.id]
    assert repo.get_alert(a1.id).type == "DOOR_OPEN" and repo.get_alert("alt-missing") is None


def test_truck_state_round_trip(repo):
    assert repo.get_state("TRK-001") == {"truck_id": "TRK-001"}
    repo.save_state({"truck_id": "TRK-001", "last_seen": iso(T0), "last_reading": reading()})
    assert repo.get_state("TRK-001")["last_seen"] == iso(T0)
    assert [r["truck_id"] for r in repo.latest_readings()] == ["TRK-001"]


@pytest.mark.skipif("cosmos" not in kinds, reason="needs the Cosmos DB emulator")
def test_telemetry_container_expires_readings_after_7_days():
    from shared.repository import CosmosFleetRepository
    r = CosmosFleetRepository(os.environ["COSMOS_ENDPOINT"], os.getenv("COSMOS_KEY", EMULATOR_KEY), database=f"test-{uuid.uuid4().hex[:8]}")
    assert r.telemetry_ttl() == TELEMETRY_TTL_S == 604800


def test_fault_choices_are_stored_per_truck(repo):  # Azure demo: the dashboard and the trucks share this table
    assert repo.get_faults() == {}
    repo.set_fault("TRK-003", "compressor"); repo.set_fault("TRK-001", "door"); repo.set_fault("TRK-003", "none")
    assert repo.get_faults() == {"TRK-001": "door", "TRK-003": "none"}
