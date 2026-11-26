"""Scale test (NFR-04, Part 4 – Roles 1, 2 and 4): N trucks, each with its own certificate and connection, one reading every 10 s.

It answers three questions with numbers: was every reading stored, how long after the truck sent it was it visible on the fleet
view, and did an alert still arrive in time while the system was busy?

Local stack:  python load/make_fleet.py 100 load/contracts-100
              for i in $(seq -f %03g 7 100); do bash scripts/issue_cert.sh TRK-$i; done
              docker compose -p greenops-load -f docker-compose.yml -f load/compose.load.yml up -d --build --scale simulator=0
              python load/loadtest.py --trucks 100 --minutes 5
Azure:        add --iothub <hub>.azure-devices.net --api https://<function app>/api   (6,000 messages for 100 trucks x 10 minutes;
              the free IoT Hub tier allows 8,000 a day)
"""
import argparse
import json
import os
import ssl
import statistics
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "simulator"), str(ROOT / "functions")]
from greenops_sim.runner import MqttPublisher, build_fleet  # noqa: E402 – the same truck code as the demo fleet
from shared import session  # noqa: E402


def percentile(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * p / 100))] if values else None


def summary(delays, sent, stored, refused, alert_s, trucks, minutes, expected=None):
    """Passed only when every truck delivered its full schedule, not just when nothing that was sent got lost."""
    lost = sent - stored
    expected = sent if expected is None else expected
    return {"trucks": trucks, "minutes": minutes, "expected": expected, "sent": sent, "stored": stored, "lost": lost, "publish_errors": refused,
            "messages_per_second": round(sent / (minutes * 60), 1),
            "visible_after_s": {"median": round(statistics.median(delays), 2), "p95": round(percentile(delays, 95), 2), "max": round(max(delays), 2)} if delays else None,
            "alert_email_s_under_load": alert_s,
            "passed": lost == 0 and refused == 0 and sent >= 0.98 * expected and bool(delays) and percentile(delays, 95) <= 10 and alert_s is not None and alert_s <= 30}


class Api:
    def __init__(self, base, key):
        self.base, self.key = base, key

    def get(self, path):
        req = urllib.request.Request(self.base + path, headers={"Authorization": "Bearer " + session.issue("dispatcher@greenops.local", self.key)})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--trucks", type=int, default=100)
    a.add_argument("--minutes", type=float, default=5)
    a.add_argument("--interval", type=float, default=10)
    a.add_argument("--api", default="http://localhost:7071/api")
    a.add_argument("--iothub")
    a.add_argument("--broker", default="localhost")
    a.add_argument("--contracts", default=str(ROOT / "load" / "contracts-100"))
    a.add_argument("--certs", default=str(ROOT / "broker" / "certs"))
    a.add_argument("--out")
    o = a.parse_args()
    env = dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines() if "=" in line)
    api = Api(o.api, os.getenv("SESSION_SIGNING_KEY") or env["SESSION_SIGNING_KEY"])
    fleet = dict(list(build_fleet(o.contracts, journey_s=3600).items())[:o.trucks])
    before = api.get("/health")["messages_today"]

    print(f"connecting {len(fleet)} trucks…", flush=True)
    pubs = {t: MqttPublisher(t, o.broker, 8883, o.certs, o.iothub) for t in fleet}
    for p in pubs.values():
        p.connect()
    time.sleep(3)
    sent, errors, lock, stop = [0], [0], threading.Lock(), threading.Event()
    hot = next(t for t in fleet if fleet[t].profile.cargo_type == "vaccines")

    def drive(i, truck_id):
        truck, pub = fleet[truck_id], pubs[truck_id]
        stop.wait(o.interval * i / len(fleet))  # spread over the interval, as a real fleet is
        end = time.monotonic() + o.minutes * 60
        while time.monotonic() < end - 0.5:
            started = time.monotonic()
            info = pub.client.publish(truck.topic + pub.topic_suffix, json.dumps(truck.next_reading(), separators=(",", ":")), qos=1)
            try:
                info.wait_for_publish(15)
                ok = info.is_published()
            except RuntimeError:  # the truck is not connected (refused certificate, lost network)
                ok = False
            with lock:
                sent[0] += ok
                errors[0] += not ok
            stop.wait(max(0, o.interval - (time.monotonic() - started)))

    threads = [threading.Thread(target=drive, args=(i, t), daemon=True) for i, t in enumerate(fleet)]
    for t in threads:
        t.start()
    seen, delays, poll = {}, [], time.monotonic()
    fault_at = time.monotonic() + o.minutes * 60 * 0.4
    faulted = False
    while any(t.is_alive() for t in threads):
        if not faulted and time.monotonic() > fault_at:
            fleet[hot].inject_fault("compressor"); faulted = True
            print(f"{hot}: compressor failure injected", flush=True)
        try:
            now_rows = api.get("/trucks")
            now = datetime.now(timezone.utc)
            for row in now_rows:
                ts = row.get("last_seen")
                if ts and seen.get(row["truck_id"]) != ts:
                    if row["truck_id"] in seen:
                        delays.append((now - datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds())
                    seen[row["truck_id"]] = ts
        except OSError as e:
            print("poll failed:", e, flush=True)
        time.sleep(max(0.2, 1 - (time.monotonic() - poll))); poll = time.monotonic()
    time.sleep(15)
    alert = next((x for x in api.get("/alerts?status=OPEN")["items"] if x["truck_id"] == hot and x["type"] == "TEMPERATURE"), None)
    stored = api.get("/health")["messages_today"] - before
    for p in pubs.values():
        p.client.disconnect(); p.client.loop_stop()
    result = summary(delays, sent[0], stored, errors[0], alert and alert["email_seconds"], len(fleet), o.minutes, expected=int(o.trucks * o.minutes * 60 / o.interval))
    print(json.dumps(result, indent=1))
    if o.out:
        Path(o.out).write_text(json.dumps(result, indent=1))
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
