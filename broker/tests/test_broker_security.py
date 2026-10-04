"""Security tests for the local IoT Hub stand-in (Role 2 – Marcelbriaud Wafotchoupe).
They need a running broker: BROKER_HOST / BROKER_PORT (default localhost:8883) and CERT_DIR (default ../certs).
Acceptance criterion FR-03: unregistered certificates are refused. FR-04: a truck can publish only to its own topic."""
import os
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
    r.on_message = lambda cl, u, m: got.append(m.topic)
    assert connects(r)
    r.subscribe("devices/+/messages/events/", qos=1)
    time.sleep(0.5)
    return r, got


def test_registered_truck_connects_and_its_message_reaches_the_router():
    r, got = listen()
    t = client("TRK-001")
    assert connects(t)
    t.publish("devices/TRK-001/messages/events/", '{"truck_id":"TRK-001"}', qos=1).wait_for_publish(5)
    time.sleep(1)
    assert "devices/TRK-001/messages/events/" in got
    t.disconnect(); r.disconnect()


def test_truck_cannot_publish_as_another_truck():  # FR-04
    r, got = listen()
    t = client("TRK-001")
    assert connects(t)
    t.publish("devices/TRK-002/messages/events/", '{"truck_id":"TRK-002"}', qos=1)
    time.sleep(1.5)
    assert "devices/TRK-002/messages/events/" not in got
    t.disconnect(); r.disconnect()


def test_device_signed_by_an_unknown_ca_is_refused():  # FR-03
    assert connects(client("TRK-666")) is False


def test_client_without_a_certificate_is_refused():  # FR-03, NFR-03
    assert connects(client("TRK-001", with_cert=False)) is False


def test_truck_cannot_read_other_trucks_data():
    got = []
    t = client("TRK-003")
    t.on_message = lambda cl, u, m: got.append(m.topic)
    assert connects(t)
    t.subscribe("devices/+/messages/events/", qos=1)
    other = client("TRK-001"); assert connects(other)
    other.publish("devices/TRK-001/messages/events/", "{}", qos=1)
    time.sleep(1.5)
    assert got == []
    t.disconnect(); other.disconnect()
