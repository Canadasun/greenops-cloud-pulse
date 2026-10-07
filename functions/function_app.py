"""GreenOps Cloud Pulse – Azure Functions app (Python v2 programming model).

Owners: alerting + fleet watcher – Shi Wang (Role 3); repository – Durmusali Unal (Role 4); Fleet API – Idowu Ayeni (Role 5).
TRIGGER_MODE=http (local): the router POSTs batches to /api/telemetry.
TRIGGER_MODE=iothub (Azure): the same process_batch() runs from the IoT Hub (Event Hub-compatible) trigger.
"""
import json
import logging
import os
import math
from functools import lru_cache
from typing import List

import azure.functions as func

from shared import dashboard_api as api
from shared.alert_service import AlertService
from shared.alerting import process_batch
from shared.fleet_watcher import check_fleet
from shared.models import utcnow
from shared.auth import operator, service_authorized

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
log = logging.getLogger("greenops")
logging.getLogger("azure").setLevel(logging.WARNING)  # hide SDK request/response logs


@lru_cache
def repo():
    if os.getenv("REPOSITORY", "cosmos") == "memory":
        from shared.repository import InMemoryFleetRepository
        return InMemoryFleetRepository()
    from shared.repository import CosmosFleetRepository
    if os.getenv("COSMOS_KEY"):  # local emulator
        return CosmosFleetRepository(os.environ["COSMOS_ENDPOINT"], os.environ["COSMOS_KEY"], os.getenv("COSMOS_DATABASE", "greenops"))
    from azure.identity import DefaultAzureCredential  # Azure: the Function's managed identity, no key stored anywhere
    return CosmosFleetRepository(os.environ["COSMOS_ENDPOINT"], database=os.getenv("COSMOS_DATABASE", "greenops"), credential=DefaultAzureCredential())


@lru_cache
def alert_service():
    from shared.notifier import LogicAppNotifier
    return AlertService(repo(), LogicAppNotifier())


def _json(body, status=200):
    return func.HttpResponse(json.dumps(body, default=str), status_code=status, mimetype="application/json")


# ---------- Alert Function (Role 3) ----------
if os.getenv("TRIGGER_MODE", "http") == "iothub":
    @app.event_hub_message_trigger(arg_name="events", event_hub_name="%IOTHUB_EVENTHUB_NAME%", connection="IOTHUB_EVENTS", cardinality="many")
    def alert_function(events: List[func.EventHubEvent]):  # the Functions worker rejects the newer list[...] form
        created = process_batch([e.get_body() for e in events], repo(), alert_service(), utcnow())
        log.info("processed %d readings, %d new alerts", len(events), len(created))
else:
    @app.route(route="telemetry", methods=["POST"])
    def alert_function(req: func.HttpRequest) -> func.HttpResponse:
        if not service_authorized(req, "INGESTION_TOKEN"):
            return _json({"error": "router credential required"}, 401)
        if len(req.get_body()) > 1024 * 1024:
            return _json({"error": "batch exceeds 1 MiB"}, 413)
        try:
            batch = req.get_json()
            if not isinstance(batch, list):
                batch = [batch]
        except ValueError:
            return _json({"error": "body must be JSON"}, 400)
        if len(batch) > 100:
            return _json({"error": "maximum 100 readings per batch"}, 400)
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
    try:
        hours = float(req.params.get("hours", "1"))
        if not math.isfinite(hours) or not 0.1 <= hours <= 24:
            raise ValueError()
    except ValueError:
        return _json({"error": "hours must be a number from 0.1 to 24"}, 400)
    if req.route_params["truck_id"] not in api.truck_ids():
        return _json({"error": "unknown truck"}, 404)
    return _json(api.history_view(repo(), req.route_params["truck_id"], hours, utcnow()))


@app.route(route="alerts", methods=["GET"])
def get_alerts(req: func.HttpRequest) -> func.HttpResponse:
    try:
        limit = int(req.params.get("limit", "50"))
        if not 1 <= limit <= 100:
            raise ValueError()
        status = req.params.get("status")
        if status not in (None, "ACTIVE", "ACKNOWLEDGED", "RESOLVED", "OPEN"):
            raise ValueError()
        truck_id = req.params.get("truck_id")
        if truck_id and truck_id not in api.truck_ids():
            raise ValueError()
        return _json(api.alert_page(repo(), limit, status, truck_id, req.params.get("cursor")))
    except (ValueError, TypeError, KeyError):
        return _json({"error": "invalid alert filter, limit or cursor"}, 400)


@app.route(route="alerts/{alert_id}/ack", methods=["POST"])
def ack_alert(req: func.HttpRequest) -> func.HttpResponse:
    user = operator(req)
    if not user:
        return _json({"error": "operator credential required"}, 401)
    try:
        body = req.get_json()
    except ValueError:
        body = {}
    code, out = api.acknowledge(alert_service(), req.route_params["alert_id"], {"user": user}, utcnow())
    return _json(out, code)


@app.route(route="health", methods=["GET"])
def get_health(req: func.HttpRequest) -> func.HttpResponse:
    return _json(api.health_view(repo(), utcnow()))


# ---------- Demo fault panel on Azure (Role 1 + Role 5): the dashboard writes, the trucks poll ----------
@app.route(route="sim/trucks", methods=["GET"])
def get_faults(req: func.HttpRequest) -> func.HttpResponse:
    return _json(api.faults_view(repo()))


@app.route(route="sim/trucks/{truck_id}/fault", methods=["POST"])
def set_fault(req: func.HttpRequest) -> func.HttpResponse:
    if not operator(req):
        return _json({"error": "operator credential required"}, 401)
    try:
        body = req.get_json()
    except ValueError:
        body = {}
    code, out = api.set_fault(repo(), req.route_params["truck_id"], body)
    return _json(out, code)


@app.route(route="sim/trucks/{truck_id}/fault", methods=["DELETE"])
def clear_fault(req: func.HttpRequest) -> func.HttpResponse:
    if not operator(req):
        return _json({"error": "operator credential required"}, 401)
    code, out = api.set_fault(repo(), req.route_params["truck_id"], {"scenario": "none"})
    return _json(out, code)


@app.route(route="session", methods=["GET"])
def get_session(req: func.HttpRequest) -> func.HttpResponse:
    user = operator(req)
    return _json({"user": user, "can_operate": bool(user)})


@app.route(route="alerts/{alert_id}/delivery", methods=["POST"])
def delivery_result(req: func.HttpRequest) -> func.HttpResponse:
    if not service_authorized(req, "DELIVERY_CALLBACK_TOKEN"):
        return _json({"error": "workflow credential required"}, 401)
    try:
        body = req.get_json()
        if not isinstance(body, dict) or body.get("status") not in ("sent", "failed") or not isinstance(body.get("workflow_id"), str):
            raise ValueError()
    except ValueError:
        return _json({"error": "status must be sent or failed"}, 400)
    result = alert_service().delivery_result(req.route_params["alert_id"], body["status"], utcnow(), body["workflow_id"])
    return _json(result.to_doc() if result else {"error": "unknown alert"}, 200 if result else 404)


@app.route(route="alerts/{alert_id}/dispatch", methods=["POST"])
def claim_dispatch(req: func.HttpRequest) -> func.HttpResponse:
    if not service_authorized(req, "DELIVERY_CALLBACK_TOKEN"):
        return _json({"error": "workflow credential required"}, 401)
    try:
        body = req.get_json()
        run_id = body.get("workflow_id") if isinstance(body, dict) else None
        if not isinstance(run_id, str) or not 1 <= len(run_id) <= 200:
            raise ValueError()
    except ValueError:
        return _json({"error": "workflow_id is required"}, 400)
    claimed = alert_service().claim_workflow(req.route_params["alert_id"], run_id)
    return _json({"dispatch": claimed}, 200 if claimed else 409)
