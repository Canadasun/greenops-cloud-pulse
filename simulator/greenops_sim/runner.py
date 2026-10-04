"""Runs the simulated fleet: one process per truck, plus a small HTTP API for fault scenarios.

Environment variables (all optional):
  MQTT_HOST / MQTT_PORT   broker address (default mosquitto:8883)
  CERT_DIR                folder with ca.crt and <truck_id>.crt / <truck_id>.key
  INTERVAL_S              seconds between readings (default 10, FR-01)
  JOURNEY_S               how long one trip takes (default 3600)
  CONTROL_PORT            port of the fault-control API (default 8090)
"""
import json
import logging
import multiprocessing as mp
import os
import ssl
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .cargo import load_profiles
from .route import Route
from .simulator import SCENARIOS, TruckSimulator

log = logging.getLogger("simulator")


def build_fleet(contracts_dir, journey_s=3600):
    contracts_dir = Path(contracts_dir)
    fleet_data = json.loads((contracts_dir / "fleet.json").read_text())
    profiles = load_profiles(contracts_dir / "cargo_profiles.json")
    fleet = {}
    for t in fleet_data["trucks"]:
        r = fleet_data["routes"][t["route_id"]]
        route = Route(t["route_id"], [tuple(p) for p in r["waypoints"]])
        fleet[t["truck_id"]] = TruckSimulator(t["truck_id"], route, profiles[t["cargo_type"]], journey_s=journey_s)
    return fleet


def backoff_delays(n, first=5, cap=60):
    """Wait 5 s, 10 s, 20 s … between reconnect attempts, never more than 60 s (Part 2, Figure 3)."""
    return [min(first * 2 ** i, cap) for i in range(n)]


def tick(truck, publisher) -> bool:
    """One pass of the loop: read the sensors and publish, unless the truck is offline. Returns True if sent."""
    msg = truck.next_reading()
    if not truck.should_publish():
        return False
    publisher.publish(truck.topic, json.dumps(msg, separators=(",", ":")))
    return True


class MqttPublisher:
    """Connects with the truck's own X.509 certificate over TLS 1.2+ (FR-03, NFR-03)."""

    def __init__(self, truck_id, host, port, cert_dir):
        import paho.mqtt.client as mqtt
        self.truck_id = truck_id
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=truck_id)
        cert_dir = Path(cert_dir)
        self.client.tls_set(ca_certs=str(cert_dir / "ca.crt"), certfile=str(cert_dir / f"{truck_id}.crt"),
                            keyfile=str(cert_dir / f"{truck_id}.key"), tls_version=ssl.PROTOCOL_TLS_CLIENT)
        self.host, self.port = host, port

    def connect(self):
        for wait in backoff_delays(1000):
            try:
                self.client.connect(self.host, self.port, keepalive=30)
                self.client.loop_start()
                log.info("%s connected to %s:%s", self.truck_id, self.host, self.port)
                return
            except OSError as e:
                log.warning("%s cannot connect (%s); retrying in %s s", self.truck_id, e, wait)
                time.sleep(wait)

    def publish(self, topic, payload):
        self.client.publish(topic, payload, qos=1)


def truck_process(truck, faults, cfg):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    pub = MqttPublisher(truck.truck_id, cfg["host"], cfg["port"], cfg["cert_dir"])
    pub.connect()
    while True:
        scenario = faults.get(truck.truck_id, "none")
        if scenario != truck.scenario:
            truck.inject_fault(scenario)
            log.info("%s scenario -> %s", truck.truck_id, scenario)
        if truck.arrived:  # start the next trip so the demo keeps running
            truck.start_next_trip()
        tick(truck, pub)
        time.sleep(cfg["interval"])


class ControlServer(ThreadingHTTPServer):
    """POST /trucks/<id>/fault {"scenario": "..."} · DELETE /trucks/<id>/fault · GET /trucks"""

    def __init__(self, addr, faults, valid_trucks):
        self.faults, self.valid = faults, set(valid_trucks)
        super().__init__(addr, _Handler)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(data)

    def _truck(self):
        parts = self.path.strip("/").split("/")
        return parts[1] if len(parts) == 3 and parts[0] == "trucks" and parts[2] == "fault" else None

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        if self.path.rstrip("/") == "/trucks":
            return self._send(200, {t: self.server.faults.get(t, "none") for t in sorted(self.server.valid)})
        if self.path.rstrip("/") == "/health":
            return self._send(200, {"status": "ok"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        t = self._truck()
        if t not in self.server.valid:
            return self._send(404, {"error": f"unknown truck {t}"})
        try:
            scenario = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}").get("scenario")
        except json.JSONDecodeError:
            scenario = None
        if scenario not in SCENARIOS:
            return self._send(400, {"error": f"scenario must be one of {list(SCENARIOS)}"})
        self.server.faults[t] = scenario
        self._send(200, {"truck_id": t, "scenario": scenario})

    def do_DELETE(self):
        t = self._truck()
        if t not in self.server.valid:
            return self._send(404, {"error": f"unknown truck {t}"})
        self.server.faults[t] = "none"
        self._send(200, {"truck_id": t, "scenario": "none"})


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    cfg = {"host": os.getenv("MQTT_HOST", "mosquitto"), "port": int(os.getenv("MQTT_PORT", "8883")),
           "cert_dir": os.getenv("CERT_DIR", "/certs"), "interval": float(os.getenv("INTERVAL_S", "10"))}
    fleet = build_fleet(os.getenv("CONTRACTS_DIR", "/contracts"), journey_s=int(os.getenv("JOURNEY_S", "3600")))
    faults = mp.Manager().dict()
    procs = [mp.Process(target=truck_process, args=(t, faults, cfg), name=t.truck_id, daemon=True) for t in fleet.values()]
    for p in procs:
        p.start()
    log.info("started %d truck processes; fault API on port %s", len(procs), os.getenv("CONTROL_PORT", "8090"))
    ControlServer(("0.0.0.0", int(os.getenv("CONTROL_PORT", "8090"))), faults, fleet.keys()).serve_forever()


if __name__ == "__main__":
    main()
