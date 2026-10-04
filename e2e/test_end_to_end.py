"""End-to-end tests against the running local stack (all roles). Start it with:
    scripts/make_certs.sh && docker compose -f docker-compose.yml -f e2e/compose.e2e.yml up -d --build
Each test is an acceptance criterion from Part 1, Table 4, checked through the real services."""
import json
import ssl
import subprocess
import time
import urllib.request
from pathlib import Path

import jsonschema
import paho.mqtt.client as mqtt
import pytest

ROOT = Path(__file__).resolve().parents[1]
API, SIM, MAIL = "http://localhost:7071/api", "http://localhost:8090", "http://localhost:8025/api/v1"
CERTS = ROOT / "broker" / "certs"
AZURITE = ("DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
           "BlobEndpoint=http://localhost:10000/devstoreaccount1;")


def http(method, url, body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    try:
        return json.loads(raw or b"null")
    except json.JSONDecodeError:  # e.g. Mailpit answers "ok" as plain text
        return raw.decode()


def wait_for(check, timeout, every=2):
    end = time.time() + timeout
    while time.time() < end:
        try:
            result = check()
        except OSError:  # a service may still be starting (connection refused / reset)
            result = None
        if result:
            return result
        time.sleep(every)
    return None


def alerts(truck, kind, statuses=("ACTIVE", "ACKNOWLEDGED")):
    return [a for a in http("GET", f"{API}/alerts?limit=200") if a["truck_id"] == truck and a["type"] == kind and a["status"] in statuses]


def emails_for(truck, kind_title):
    msgs = http("GET", f"{MAIL}/messages?limit=500")["messages"]
    return [m for m in msgs if truck in m["Subject"] and kind_title in m["Subject"]]


def fault(truck, scenario):
    if scenario == "none":
        return http("DELETE", f"{SIM}/trucks/{truck}/fault")
    return http("POST", f"{SIM}/trucks/{truck}/fault", {"scenario": scenario})


@pytest.fixture(scope="session", autouse=True)
def stack_ready():
    ok = wait_for(lambda: all(t.get("seconds_ago") is not None for t in http("GET", f"{API}/trucks")), 180, 5)
    assert ok, "stack did not start: not every truck has reported"
    for i in range(1, 7):
        fault(f"TRK-00{i}", "none")
    http("DELETE", f"{MAIL}/messages")


def test_every_truck_reports_and_messages_follow_the_contract():  # FR-01, Appendix A
    schema = json.loads((ROOT / "contracts" / "telemetry.schema.json").read_text())
    got = []
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"e2e-{time.time_ns()}", protocol=mqtt.MQTTv5)
    c.tls_set(ca_certs=str(CERTS / "ca.crt"), certfile=str(CERTS / "e2e-tester.crt"), keyfile=str(CERTS / "e2e-tester.key"), tls_version=ssl.PROTOCOL_TLS_CLIENT)
    c.on_message = lambda cl, u, m: got.append(json.loads(m.payload))
    c.connect("localhost", 8883); c.loop_start(); c.subscribe("devices/+/messages/events/", qos=1)
    wait_for(lambda: len({m["truck_id"] for m in got}) == 6, 30, 1)
    c.disconnect()
    assert {m["truck_id"] for m in got} == {f"TRK-00{i}" for i in range(1, 7)}
    for m in got:
        jsonschema.validate(m, schema, format_checker=jsonschema.FormatChecker())
    trucks = http("GET", f"{API}/trucks")
    assert all(t["seconds_ago"] <= 20 for t in trucks)


def test_temperature_breach_gives_one_alert_and_one_email_within_30_seconds():  # FR-05, FR-06, NFR-01
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    fault("TRK-001", "compressor")
    first_bad = wait_for(lambda: next((h for h in http("GET", f"{API}/trucks/TRK-001/history?hours=0.2")["points"]
                                       if h["timestamp"] >= started and h["temp_c"] > 8), None), 150, 2)
    assert first_bad, "temperature never went above 8 °C"
    alert = wait_for(lambda: alerts("TRK-001", "TEMPERATURE"), 30, 1)
    assert alert, "no alert within 30 s of the first reading above 8 °C"
    mail = wait_for(lambda: emails_for("TRK-001", "Temperature breach"), 30, 1)
    assert mail and alert[0]["email_seconds"] < 30
    time.sleep(40)  # four more breaching readings
    assert len(alerts("TRK-001", "TEMPERATURE")) == 1 and len(emails_for("TRK-001", "Temperature breach")) == 1
    fault("TRK-001", "none")
    assert wait_for(lambda: not alerts("TRK-001", "TEMPERATURE"), 120, 3), "alert did not resolve after recovery"


def test_door_open_too_long_gives_one_alert():  # FR-07 (limit shortened to 30 s for this run)
    fault("TRK-002", "door")
    assert wait_for(lambda: alerts("TRK-002", "DOOR_OPEN"), 75, 3)
    assert wait_for(lambda: emails_for("TRK-002", "Cargo door left open"), 20, 2)
    fault("TRK-002", "none")
    assert wait_for(lambda: not alerts("TRK-002", "DOOR_OPEN"), 40, 3)


def test_silent_truck_is_flagged_offline_and_recovers():  # FR-08 (40 s for this run)
    fault("TRK-004", "offline")
    assert wait_for(lambda: alerts("TRK-004", "OFFLINE"), 90, 3)
    assert next(t for t in http("GET", f"{API}/trucks") if t["truck_id"] == "TRK-004")["status"] == "offline"
    fault("TRK-004", "none")
    assert wait_for(lambda: not alerts("TRK-004", "OFFLINE"), 40, 3)


def test_delayed_truck_is_flagged_after_its_eta():  # FR-08 (150 s trips for this run)
    fault("TRK-005", "delay")
    assert wait_for(lambda: alerts("TRK-005", "DELAYED"), 240, 5)
    assert next(t for t in http("GET", f"{API}/trucks") if t["truck_id"] == "TRK-005")["status"] == "warning"
    fault("TRK-005", "none")


def test_dispatcher_can_acknowledge_an_alert():  # FR-11
    open_alerts = wait_for(lambda: [a for a in http("GET", f"{API}/alerts") if a["status"] == "ACTIVE"], 30, 2)
    assert open_alerts, "no active alert to acknowledge"
    a = http("POST", f"{API}/alerts/{open_alerts[0]['id']}/ack", {"user": "e2e dispatcher"})
    assert a["status"] == "ACKNOWLEDGED" and a["acknowledged_by"] == "e2e dispatcher"


def test_raw_messages_are_archived_to_blob_storage():  # FR-09 (archive every 30 s for this run)
    from azure.storage.blob import BlobServiceClient
    container = BlobServiceClient.from_connection_string(AZURITE).get_container_client("telemetry-archive")
    blobs = wait_for(lambda: [b.name for b in container.list_blobs(name_starts_with="telemetry/")], 60, 5)
    assert blobs and blobs[0].endswith(".jsonl")
    lines = container.download_blob(blobs[-1]).readall().decode().splitlines()
    assert lines and all(json.loads(x)["truck_id"].startswith("TRK-") for x in lines)


def test_revoked_certificate_is_refused():  # FR-03, Table 4
    import sys
    sys.path.insert(0, str(ROOT / "broker" / "tests"))
    from test_broker_security import client, connects
    device = f"TRK-9{int(time.time()) % 100:02d}"   # a fresh device each run, so the test can be repeated
    subprocess.run(["bash", str(ROOT / "scripts" / "issue_cert.sh"), device], check=True, capture_output=True)
    assert connects(client(device)) is True
    subprocess.run(["bash", str(ROOT / "scripts" / "revoke_cert.sh"), device], check=True, capture_output=True)
    subprocess.run(["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "kill", "-s", "HUP", "mosquitto"], check=True, capture_output=True)
    time.sleep(2)
    assert connects(client(device)) is False


def test_dashboard_page_and_api_proxy_are_served():  # FR-10 hosting
    with urllib.request.urlopen("http://localhost:5173/", timeout=10) as r:
        assert r.status == 200 and b'<div id="root">' in r.read()
    assert len(http("GET", "http://localhost:5173/api/trucks")) == 6
