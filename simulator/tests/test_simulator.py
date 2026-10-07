"""Tests for the truck simulator (Role 1 – Ying Song). They describe FR-01 and FR-02 from Part 1."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jsonschema
import pytest

from greenops_sim.cargo import CargoProfile, load_profiles
from greenops_sim.route import Route
from greenops_sim.simulator import TruckSimulator, SCENARIOS

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
SCHEMA = json.loads((CONTRACTS / "telemetry.schema.json").read_text())
START = datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self, t):
        self.t = t

    def now(self):
        return self.t

    def advance(self, seconds):
        self.t += timedelta(seconds=seconds)


def make_truck(cargo="vaccines", journey_s=600, seed=7):
    clock = FakeClock(START)
    route = Route("OTT-TOR-01", [(45.4215, -75.6972), (44.2312, -76.4860), (43.6532, -79.3832)])
    profile = load_profiles(CONTRACTS / "cargo_profiles.json")[cargo]
    truck = TruckSimulator("TRK-001", route, profile, clock=clock.now, journey_s=journey_s, seed=seed)
    return truck, clock


def test_reading_matches_the_data_contract():  # FR-01, Appendix A
    truck, _ = make_truck()
    msg = truck.next_reading()
    jsonschema.validate(msg, SCHEMA, format_checker=jsonschema.FormatChecker())
    assert msg["truck_id"] == "TRK-001" and msg["route_id"] == "OTT-TOR-01"
    assert (msg["temp_min_c"], msg["temp_max_c"]) == (2, 8)


def test_message_is_smaller_than_half_a_kilobyte():  # IoT Hub counts messages in 0.5 KB blocks
    truck, _ = make_truck()
    assert len(json.dumps(truck.next_reading()).encode()) < 512


def test_normal_readings_stay_inside_the_safe_range():
    truck, clock = make_truck()
    for _ in range(50):
        clock.advance(10)
        msg = truck.next_reading()
        assert 2 <= msg["temp_c"] <= 8
        assert msg["door_open"] is False


def test_truck_moves_along_the_route_and_arrives():
    truck, clock = make_truck(journey_s=600)
    first = truck.next_reading()
    clock.advance(300)
    middle = truck.next_reading()
    assert (middle["lat"], middle["lon"]) != (first["lat"], first["lon"])
    clock.advance(400)
    last = truck.next_reading()
    assert (last["lat"], last["lon"]) == pytest.approx((43.6532, -79.3832), abs=1e-4)
    assert truck.arrived and last["speed_kmh"] == 0


def test_compressor_failure_makes_the_temperature_rise_above_the_limit():  # FR-02
    truck, clock = make_truck()
    truck.inject_fault("compressor")
    temps = []
    for _ in range(12):
        clock.advance(10)
        temps.append(truck.next_reading()["temp_c"])
    assert temps[-1] > 8 and temps == sorted(temps)


def test_door_fault_opens_the_door_and_clear_fault_recovers():
    truck, clock = make_truck()
    truck.inject_fault("door")
    assert truck.next_reading()["door_open"] is True
    truck.clear_fault()
    clock.advance(10)
    assert truck.next_reading()["door_open"] is False


def test_delay_fault_slows_the_truck_down():
    normal, c1 = make_truck(journey_s=600)
    delayed, c2 = make_truck(journey_s=600)
    delayed.inject_fault("delay")
    for _ in range(30):
        c1.advance(10); c2.advance(10)
        a, b = normal.next_reading(), delayed.next_reading()
    assert b["speed_kmh"] < a["speed_kmh"] / 2
    assert delayed.progress < normal.progress


def test_offline_fault_means_nothing_is_published():
    truck, _ = make_truck()
    truck.inject_fault("offline")
    assert truck.should_publish() is False
    truck.clear_fault()
    assert truck.should_publish() is True


def test_unknown_fault_is_rejected():
    truck, _ = make_truck()
    with pytest.raises(ValueError):
        truck.inject_fault("meteor")
    assert set(SCENARIOS) == {"none", "compressor", "door", "delay", "offline"}


def test_topic_is_the_trucks_own_iot_hub_topic():  # FR-04
    truck, _ = make_truck()
    assert truck.topic == "devices/TRK-001/messages/events/"


def test_frozen_cargo_uses_its_own_limits():
    truck, _ = make_truck(cargo="frozen_food")
    msg = truck.next_reading()
    assert (msg["temp_min_c"], msg["temp_max_c"]) == (-25, -15)
    assert -25 <= msg["temp_c"] <= -15


def test_cargo_profile_breach_rule():
    p = CargoProfile("vaccines", 2, 8, 75)
    assert not p.is_breach(4.0, 60) and p.is_breach(8.5, 60) and p.is_breach(1.5, 60) and p.is_breach(5, 80)


def test_compressor_failure_stops_warming_at_the_outside_temperature():
    truck, clock = make_truck()
    truck.inject_fault("compressor")
    for _ in range(100):
        clock.advance(10)
        msg = truck.next_reading()
    assert msg["temp_c"] == 24.0


def test_next_trip_keeps_the_cargo_temperature_and_the_fault():
    truck, clock = make_truck(journey_s=60)
    truck.inject_fault("compressor")
    for _ in range(7):
        clock.advance(10)
        last = truck.next_reading()
    assert truck.arrived
    truck.start_next_trip()
    clock.advance(10)
    nxt = truck.next_reading()
    assert truck.scenario == "compressor" and nxt["temp_c"] > last["temp_c"]
    assert nxt["lat"] != last["lat"] and nxt["scheduled_eta"] > last["scheduled_eta"]


def test_accelerated_route_matches_reported_speed_and_scale():
    truck, clock = make_truck(journey_s=600)
    before = truck.progress
    clock.advance(10)
    msg = truck.next_reading()
    map_kmh = (truck.progress - before) * truck.route.length_km / (10 / 3600)
    assert msg['speed_kmh'] <= 120
    assert map_kmh == pytest.approx(msg['speed_kmh'] * msg['simulation_time_scale'], abs=0.1)
