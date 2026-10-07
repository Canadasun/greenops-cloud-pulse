"""Security tests for the local IoT Hub stand-in (Role 2 – Marcelbriaud Wafotchoupe).
They need a running broker: BROKER_HOST / BROKER_PORT (default localhost:8883) and CERT_DIR (default ../certs).
Acceptance criterion FR-03: unregistered certificates are refused. FR-04: a truck can publish only to its own topic."""
import os
import json
import uuid
from datetime import datetime, timezone, timedelta
import ssl
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest

HOST = os.getenv("BROKER_HOST", "localhost")
PORT = int(os.getenv("BROKER_PORT", "8883"))
CERTS = Path(os.getenv("CERT_DIR", Path(__file__).resolve().parents[1] / "certs"))


def client(name, ca="ca.crt", with_cert=True):
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{name}-{time.time_ns()}", protocol=mqtt.MQTTv5)
    kw = {"certfile": str(CERTS / f"{name}.crt"), "keyfile": str(CERTS / f"{name}.key")} if with_cert else {}
    c.tls_set(ca_certs=str(CERTS / ca), tls_version=ssl.PROTOCOL_TLS_CLIENT, **kw)
    return c


def connects(c) -> bool:
    done = threading.Event()
    ok = {}
    c.on_connect = lambda cl, u, f, rc, p=None: (ok.update(rc=rc), done.set())
    try:
        c.connect(HOST, PORT, keepalive=10)
    except (ssl.SSLError, OSError):
        return False
    c.loop_start()
    done.wait(5)
    good = ok.get("rc") is not None and not ok["rc"].is_failure
    return good


def listen():
    """Subscribe as the router identity and collect everything it receives."""
    got = []
    r = client("router")
    r.on_message = lambda cl, u, m: got.append((m.topic, m.payload.decode()))
    assert connects(r)
    r.subscribe("devices/+/messages/events/", qos=1)
    time.sleep(0.5)
    return r, got


def payload(truck):
    data = json.loads((Path(__file__).resolve().parents[2] / "contracts/fleet.json").read_text())
    profiles = json.loads((Path(__file__).resolve().parents[2] / "contracts/cargo_profiles.json").read_text())
    t = next(t for t in data['trucks'] if t['truck_id'] == truck)
    profile = profiles[t['cargo_type']]
    # A complete historical sample, distinguishable from real fleet traffic. It cannot
    # overwrite a current reading due to the processing watermark.
    when = datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=uuid.uuid4().int % 1000000)
    lat,lon = data['routes'][t['route_id']]['waypoints'][0]
    return json.dumps({**t, 'timestamp':when.isoformat(), 'scheduled_eta':(when+timedelta(hours=4)).isoformat(),
        'lat':lat,'lon':lon,'speed_kmh':0,'temp_c':(profile['temp_min_c']+profile['temp_max_c'])/2,
        'humidity_pct':60,'door_open':False,'temp_min_c':profile['temp_min_c'],'temp_max_c':profile['temp_max_c']})


def test_registered_truck_connects_and_its_message_reaches_the_router():
    r, got = listen()
    t = client("TRK-001")
    assert connects(t)
    body = payload("TRK-001")
    t.publish("devices/TRK-001/messages/events/", body, qos=1).wait_for_publish(5)
    time.sleep(1)
    assert ("devices/TRK-001/messages/events/", body) in got
    t.disconnect(); r.disconnect()


def test_truck_cannot_publish_as_another_truck():  # FR-04
    r, got = listen()
    t = client("TRK-001")
    assert connects(t)
    body = payload("TRK-002")
    t.publish("devices/TRK-002/messages/events/", body, qos=1)
    time.sleep(1.5)
    assert ("devices/TRK-002/messages/events/", body) not in got
    t.disconnect(); r.disconnect()


def test_device_signed_by_an_unknown_ca_is_refused():  # FR-03
    assert connects(client("TRK-666")) is False


def test_client_without_a_certificate_is_refused():  # FR-03, NFR-03
    assert connects(client("TRK-001", with_cert=False)) is False


def test_truck_cannot_read_other_trucks_data():
    got = []
    t = client("TRK-003")
    t.on_message = lambda cl, u, m: got.append((m.topic, m.payload.decode()))
    assert connects(t)
    t.subscribe("devices/+/messages/events/", qos=1)
    other = client("TRK-001"); assert connects(other)
    other.publish("devices/TRK-001/messages/events/", payload("TRK-001"), qos=1)
    time.sleep(1.5)
    assert got == []
    t.disconnect(); other.disconnect()
