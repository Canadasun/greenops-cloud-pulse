"""GreenOps Cloud Pulse – Azure Functions app (Python v2 programming model).

Owners: alerting + fleet watcher – Shi Wang (Role 3); repository – Durmusali Unal (Role 4); Fleet API – Idowu Ayeni (Role 5).
TRIGGER_MODE=http (local): the router POSTs batches to /api/telemetry.
TRIGGER_MODE=iothub (Azure): the same process_batch() runs from the IoT Hub (Event Hub-compatible) trigger.
"""
import json
import logging
import os
from functools import lru_cache

import azure.functions as func

from shared import dashboard_api as api
from shared.alert_service import AlertService
from shared.alerting import process_batch
from shared.fleet_watcher import check_fleet
from shared.models import utcnow

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
log = logging.getLogger("greenops")


@lru_cache
def repo():
    if os.getenv("REPOSITORY", "cosmos") == "memory":
        from shared.repository import InMemoryFleetRepository
        return InMemoryFleetRepository()
    from shared.repository import CosmosFleetRepository
    return CosmosFleetRepository(os.environ["COSMOS_ENDPOINT"], os.environ["COSMOS_KEY"], os.getenv("COSMOS_DATABASE", "greenops"))


@lru_cache
def alert_service():
    from shared.notifier import LogicAppNotifier
    return AlertService(repo(), LogicAppNotifier())


def _json(body, status=200):
    return func.HttpResponse(json.dumps(body, default=str), status_code=status, mimetype="application/json")


# ---------- Alert Function (Role 3) ----------
if os.getenv("TRIGGER_MODE", "http") == "iothub":
    @app.event_hub_message_trigger(arg_name="events", event_hub_name="%IOTHUB_EVENTHUB_NAME%", connection="IOTHUB_EVENTS", cardinality="many")
    def alert_function(events: list[func.EventHubEvent]):
        created = process_batch([json.loads(e.get_body()) for e in events], repo(), alert_service(), utcnow())
        log.info("processed %d readings, %d new alerts", len(events), len(created))
else:
    @app.route(route="telemetry", methods=["POST"])
    def alert_function(req: func.HttpRequest) -> func.HttpResponse:
        try:
            batch = req.get_json()
            if not isinstance(batch, list):
                batch = [batch]
        except ValueError:
            return _json({"error": "body must be JSON"}, 400)
        created = process_batch(batch, repo(), alert_service(), utcnow())
        return _json({"processed": len(batch), "new_alerts": [a.id for a in created]})


# ---------- Fleet Watcher (Role 3) ----------
@app.timer_trigger(arg_name="timer", schedule="%FLEET_WATCHER_SCHEDULE%", run_on_startup=False, use_monitor=False)
def fleet_watcher(timer: func.TimerRequest):
    raised = check_fleet(repo(), alert_service(), utcnow())
    log.info("fleet watcher: %d new alerts", len(raised))


# ---------- Fleet API (Role 5) ----------
@app.route(route="trucks", methods=["GET"])
def get_trucks(req: func.HttpRequest) -> func.HttpResponse:
    return _json(api.trucks_view(repo(), utcnow()))


@app.route(route="routes", methods=["GET"])
def get_routes(req: func.HttpRequest) -> func.HttpResponse:
    return _json(api.routes_view())


@app.route(route="trucks/{truck_id}/history", methods=["GET"])
def get_history(req: func.HttpRequest) -> func.HttpResponse:
    hours = min(max(float(req.params.get("hours", "1")), 0.1), 24)
    return _json(api.history_view(repo(), req.route_params["truck_id"], hours, utcnow()))


@app.route(route="alerts", methods=["GET"])
def get_alerts(req: func.HttpRequest) -> func.HttpResponse:
    return _json(api.alerts_view(repo(), limit=int(req.params.get("limit", "50")), status=req.params.get("status")))


@app.route(route="alerts/{alert_id}/ack", methods=["POST"])
def ack_alert(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        body = {}
    code, out = api.acknowledge(alert_service(), req.route_params["alert_id"], body, utcnow())
    return _json(out, code)


@app.route(route="health", methods=["GET"])
def get_health(req: func.HttpRequest) -> func.HttpResponse:
    return _json(api.health_view(repo(), utcnow()))
