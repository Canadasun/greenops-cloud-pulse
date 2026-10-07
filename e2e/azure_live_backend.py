"""Live checks of the Azure deployment that the browser cannot see (Role 2 – Marcelbriaud Wafotchoupe; Role 4 – Durmusali Unal).

F5: every truck is registered in IoT Hub with its own X.509 certificate and is connected; an unregistered device and a
    device signed by an unknown CA are refused by the real IoT Hub (FR-03).
F6: the raw archive in Blob Storage received a new batch within the last 10 minutes (FR-09).
Usage: python e2e/azure_live_backend.py <resource-group> <iot-hub-name> <storage-account>   (needs: az login, azure-iot ext)
"""
import json
import ssl
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

RG, HUB, STORAGE = sys.argv[1:4]
CERTS = Path(__file__).resolve().parents[1] / "broker" / "certs"
TRUCKS = [f"TRK-00{i}" for i in range(1, 7)]


def az(*args):
    return json.loads(subprocess.run(["az", *args, "-o", "json"], check=True, capture_output=True, text=True).stdout)


def iot_hub_accepts(device):
    """Try to sign in to the real IoT Hub with this device's certificate."""
    host = f"{HUB}.azure-devices.net"
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=device)
    c.username_pw_set(f"{host}/{device}/?api-version=2021-04-12")
    c.tls_set(certfile=str(CERTS / f"{device}.crt"), keyfile=str(CERTS / f"{device}.key"), tls_version=ssl.PROTOCOL_TLS_CLIENT)
    done, result = threading.Event(), {}
    c.on_connect = lambda cl, u, f, rc, p=None: (result.update(rc=rc), done.set())
    try:
        c.connect(host, 8883, keepalive=10)
    except (OSError, ssl.SSLError):
        return False
    c.loop_start()
    done.wait(10)
    c.loop_stop()
    c.disconnect()
    return result.get("rc") is not None and not result["rc"].is_failure


devices = {d["deviceId"]: d for d in az("iot", "hub", "device-identity", "list", "-n", HUB)}
for t in TRUCKS:
    d = devices[t]
    assert d["authenticationType"] == "selfSigned", f"{t} is not using X.509 thumbprint authentication"
    assert d["connectionState"] == "Connected", f"{t} is not connected"
assert "TRK-099" not in devices
# Positive control: a registered truck's certificate is accepted by the same code (TRK-005 is "offline" in the demo,
# so taking over its connection for a moment does not interrupt live data; the simulator reconnects by itself).
assert iot_hub_accepts("TRK-005"), "registered device was refused – the check itself is broken"
assert not iot_hub_accepts("TRK-099"), "unregistered device was accepted"
assert not iot_hub_accepts("TRK-666"), "device from an unknown CA was accepted"
print("✓ F5   6 trucks registered with their own X.509 certificate and connected; registered TRK-005 accepted, "
      "unregistered TRK-099 and unknown-CA TRK-666 refused by Azure IoT Hub")

key = az("storage", "account", "keys", "list", "-n", STORAGE, "-g", RG)[0]["value"]
blobs = az("storage", "blob", "list", "--account-name", STORAGE, "--account-key", key, "-c", "telemetry-archive",
           "--prefix", f"{HUB}/telemetry/{datetime.now(timezone.utc):%Y/%m/%d}/", "--num-results", "5000")
newest = max(datetime.fromisoformat(b["properties"]["lastModified"]) for b in blobs)
age = datetime.now(timezone.utc) - newest
assert age < timedelta(minutes=10), f"newest archive batch is {age} old"
print(f"✓ F6   {len(blobs)} archive batches today in Blob Storage; newest written {int(age.total_seconds())} s ago (FR-09: < 10 min)")
