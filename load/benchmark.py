"""Hot-path benchmark (Part 4): database requests and time per operation, against a real Cosmos DB endpoint or the emulator.

    COSMOS_ENDPOINT=http://localhost:8081 CONTRACTS_DIR=load/contracts-100 python load/benchmark.py [path to a functions folder]
Run it on two versions of the code to compare them; it only uses functions both versions have."""
import json
import os
import statistics
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "functions"))
from azure.core.pipeline.transport import RequestsTransport  # noqa: E402

requests_sent = 0
LATENCY_S = float(os.getenv("ADD_LATENCY_MS", "0")) / 1000   # the emulator has no network; Azure has
_send = RequestsTransport.send


def counted(self, request, **kw):
    global requests_sent
    requests_sent += 1
    time.sleep(LATENCY_S)
    return _send(self, request, **kw)


RequestsTransport.send = counted
from shared import dashboard_api as api  # noqa: E402
from shared.alert_service import AlertService  # noqa: E402
from shared.alerting import process_batch  # noqa: E402
from shared.fleet_watcher import check_fleet  # noqa: E402
from shared.models import iso  # noqa: E402
from shared.reference import cargo_profiles, fleet  # noqa: E402
from shared.repository import CosmosFleetRepository  # noqa: E402

KEY = "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="


class NoEmail:
    def send(self, alert):
        return {"channel": "email", "to": "none"}


def reading(truck, t, parked=False):
    c = cargo_profiles()[truck["cargo_type"]]
    r = {"truck_id": truck["truck_id"], "route_id": truck["route_id"], "timestamp": iso(t), "lat": 45.4, "lon": -75.7, "speed_kmh": 80,
         "temp_c": (c["temp_min_c"] + c["temp_max_c"]) / 2, "humidity_pct": 50, "door_open": False, "cargo_type": truck["cargo_type"],
         "temp_min_c": c["temp_min_c"], "temp_max_c": c["temp_max_c"], "scheduled_eta": iso(t + timedelta(hours=4))}
    return {**r, "parked": True} if parked else r


def measure(name, runs, fn):
    global requests_sent
    times, before = [], requests_sent
    for i in range(runs):
        a = time.perf_counter(); fn(i); times.append(time.perf_counter() - a)
    out = {"operation": name, "db_requests": round((requests_sent - before) / runs, 1), "median_ms": round(statistics.median(times) * 1000)}
    print(json.dumps(out), flush=True)


def main():
    db = f"bench-{uuid.uuid4().hex[:8]}"
    repo = CosmosFleetRepository(os.environ["COSMOS_ENDPOINT"], os.getenv("COSMOS_KEY", KEY), database=db)
    svc, trucks = AlertService(repo, NoEmail()), fleet()["trucks"]
    t0 = datetime.now(timezone.utc) - timedelta(minutes=30)
    try:
        process_batch([reading(t, t0) for t in trucks], repo, svc, t0)
        measure(f"ingest: 1 reading x {len(trucks)} trucks", 5, lambda i: process_batch(
            [reading(t, t0 + timedelta(seconds=10 * (i + 1))) for t in trucks], repo, svc, t0 + timedelta(seconds=10 * (i + 1))))
        measure("ingest: 10 readings x 10 trucks", 5, lambda i: process_batch(
            [reading(t, t0 + timedelta(seconds=100 + 100 * i + 10 * k)) for t in trucks[:10] for k in range(10)], repo, svc, t0 + timedelta(seconds=200 + 100 * i)))
        measure(f"dashboard: fleet view of {len(trucks)} trucks", 15, lambda i: api.trucks_view(repo, t0))
        measure("dashboard: health panel", 15, lambda i: api.health_view(repo, datetime.now(timezone.utc)))
        now = t0 + timedelta(minutes=20)
        process_batch([reading(t, now, parked=True) for t in trucks], repo, svc, now)
        check_fleet(repo, svc, now + timedelta(minutes=1))
        measure(f"fleet watcher: {len(trucks)} parked trucks", 5, lambda i: check_fleet(repo, svc, now + timedelta(minutes=2 + i)))
    finally:
        repo.client.delete_database(db)


if __name__ == "__main__":
    main()
