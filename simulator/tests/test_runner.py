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


def test_control_api_switches_faults_on_and_off(monkeypatch):
    monkeypatch.setenv("SIM_CONTROL_TOKEN", "test-operator")
    faults = {}
    server = ControlServer(("127.0.0.1", 0), faults, valid_trucks={"TRK-001"})
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(method, path, body=None):
        req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body else None,
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer test-operator"})
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


# ---- Azure IoT Hub mode (Role 2 – Marcelbriaud Wafotchoupe): same truck code, real IoT Hub
from greenops_sim.runner import iothub_settings, apply_remote_faults


def test_iothub_settings_use_the_device_username_and_json_topic():
    s = iothub_settings("iot-greenops.azure-devices.net", "TRK-003")
    assert s["username"] == "iot-greenops.azure-devices.net/TRK-003/?api-version=2021-04-12"
    assert s["ca_certs"] is None  # IoT Hub uses a public certificate, so the system CA list is used
    assert s["topic_suffix"] == "$.ct=application%2Fjson&$.ce=utf-8"  # body stays readable JSON in routing and the archive


def test_remote_faults_update_only_known_trucks_and_valid_scenarios():
    faults = {}
    apply_remote_faults(faults, {"TRK-001": "door", "TRK-999": "door", "TRK-002": "explode"}, {"TRK-001", "TRK-002"})
    assert faults == {"TRK-001": "door"}


# ---- Cloud run (Role 1 – Ying Song): the Azure job stops the trucks itself after RUN_FOR_S seconds
from greenops_sim.runner import serve


def test_serve_returns_after_run_for_s_so_the_cloud_job_ends_cleanly():
    server = ControlServer(("127.0.0.1", 0), {}, valid_trucks={"TRK-001"})
    done = threading.Event()
    threading.Thread(target=lambda: (serve(server, run_for_s=0.3), done.set()), daemon=True).start()
    assert done.wait(5), "serve() should return once the run time is over"


def test_serve_without_run_time_keeps_running_until_shutdown():
    server = ControlServer(("127.0.0.1", 0), {}, valid_trucks={"TRK-001"})
    done = threading.Event()
    threading.Thread(target=lambda: (serve(server, run_for_s=None), done.set()), daemon=True).start()
    assert not done.wait(0.5)
    server.shutdown()
    assert done.wait(5)
