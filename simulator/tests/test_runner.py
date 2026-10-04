"""Tests for the publish loop and the fault-control API (Role 1 – Ying Song)."""
import json
import threading
import urllib.request
from pathlib import Path

from greenops_sim.runner import tick, backoff_delays, ControlServer, build_fleet

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"


class FakePublisher:
    def __init__(self):
        self.sent = []

    def publish(self, topic, payload):
        self.sent.append((topic, json.loads(payload)))


def test_tick_publishes_one_reading_to_the_trucks_topic():
    fleet = build_fleet(CONTRACTS, journey_s=600)
    truck = fleet["TRK-001"]
    pub = FakePublisher()
    assert tick(truck, pub) is True
    topic, msg = pub.sent[0]
    assert topic == "devices/TRK-001/messages/events/" and msg["truck_id"] == "TRK-001"


def test_tick_sends_nothing_while_offline():
    truck = build_fleet(CONTRACTS)["TRK-002"]
    truck.inject_fault("offline")
    pub = FakePublisher()
    assert tick(truck, pub) is False and pub.sent == []


def test_reconnect_waits_grow_5_10_20_and_cap_at_60():
    assert backoff_delays(6) == [5, 10, 20, 40, 60, 60]


def test_fleet_has_six_trucks_from_reference_data():
    fleet = build_fleet(CONTRACTS)
    assert sorted(fleet) == [f"TRK-00{i}" for i in range(1, 7)]
    assert fleet["TRK-004"].profile.cargo_type == "frozen_food"


def test_control_api_switches_faults_on_and_off():
    faults = {}
    server = ControlServer(("127.0.0.1", 0), faults, valid_trucks={"TRK-001"})
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(method, path, body=None):
        req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    assert call("POST", "/trucks/TRK-001/fault", {"scenario": "compressor"}) == (200, {"truck_id": "TRK-001", "scenario": "compressor"})
    assert faults["TRK-001"] == "compressor"
    assert call("GET", "/trucks")[1] == {"TRK-001": "compressor"}
    assert call("POST", "/trucks/TRK-001/fault", {"scenario": "meteor"})[0] == 400
    assert call("POST", "/trucks/TRK-999/fault", {"scenario": "door"})[0] == 404
    assert call("DELETE", "/trucks/TRK-001/fault")[1]["scenario"] == "none"
    server.shutdown()
