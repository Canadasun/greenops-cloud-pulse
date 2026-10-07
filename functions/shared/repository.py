"""FleetRepository – the only code that talks to the database (Role 4 – Durmusali Unal; Part 2, Figures 5–6, Table 2).

Containers (all partitioned so one truck's data is stored together):
  telemetry  – TELEMETRY_READING, partition /truck_id, default time-to-live 7 days
  alerts     – ALERT and NOTIFICATION, partition /truck_id
  reference  – TRUCK state and the demo fault table, partition /doc_type
Two implementations share one interface: CosmosFleetRepository (Cosmos DB / emulator) and InMemoryFleetRepository (tests).
"""
from datetime import timedelta
from copy import deepcopy
from threading import RLock
import hashlib
import json
import time

from .models import OPEN_STATUSES, Alert, iso, parse

TELEMETRY_TTL_S = 7 * 24 * 3600


class TruckTransaction:
    """Side-effect-free unit of work; Cosmos may re-run its callback after contention."""
    def __init__(self, repo, truck_id, state):
        self.repo, self.truck_id, self.state = repo, truck_id, deepcopy(state)
        self.changed = {}
        self.open = {a.id: a for a in repo.open_alerts(truck_id)}

    def find_open(self, alert_type):
        return next((a for a in self.open.values() if a.type == alert_type and a.status in OPEN_STATUSES), None)

    def get_alert(self, alert_id):
        return self.changed.get(alert_id) or self.open.get(alert_id) or self.repo.get_alert(alert_id)

    def save_alert(self, alert):
        self.changed[alert.id] = alert
        self.open[alert.id] = alert


class InMemoryFleetRepository:
    def __init__(self):
        self._readings, self.alerts, self.state, self.notifications, self._faults = {}, {}, {}, [], {}
        self._lock = RLock()
        self.quarantine = {}

    def mutate_truck(self, truck_id, callback):
        with self._lock:
            tx = TruckTransaction(self, truck_id, self.get_state(truck_id))
            result = callback(tx)
            self.save_state(tx.state)
            for a in tx.changed.values():
                self.save_alert(a)
            return deepcopy(result)

    def quarantine_event(self, raw, reason, now):
        doc = quarantine_doc(raw, reason, now)
        self.quarantine[doc["id"]] = doc

    @property
    def readings(self):
        return list(self._readings.values())

    # --- immutable telemetry (create by id; retries preserve the first stored reading)
    def save_readings(self, msgs):
        saved = []
        for m in msgs:
            doc = {**m, "id": f"{m['truck_id']}-{m['timestamp']}"}
            self._readings.setdefault(doc["id"], deepcopy(doc))
            saved.append(deepcopy(self._readings[doc["id"]]))
        return saved

    def latest_readings(self):
        return [s["last_reading"] for s in self.state.values() if s.get("last_reading")]

    def history(self, truck_id, since):
        return sorted((r for r in self.readings if r["truck_id"] == truck_id and r["timestamp"] >= iso(since)), key=lambda r: r["timestamp"])

    def count_readings_since(self, since):
        return sum(1 for r in self.readings if r["timestamp"] >= iso(since))

    # --- alerts
    def find_open(self, truck_id, alert_type):
        for a in self.alerts.values():
            if a.truck_id == truck_id and a.type == alert_type and a.status in OPEN_STATUSES:
                return deepcopy(a)
        return None

    def open_alerts(self, truck_id=None):
        return deepcopy([a for a in self.alerts.values() if a.status in OPEN_STATUSES and (truck_id is None or a.truck_id == truck_id)])

    def save_alert(self, alert):
        self.alerts[alert.id] = deepcopy(alert)

    def get_alert(self, alert_id):
        return deepcopy(self.alerts.get(alert_id))

    def list_alerts(self, limit=50, status=None, before=None, truck_id=None):
        items = [a for a in self.alerts.values() if (status is None or a.status == status)
                 and (not truck_id or a.truck_id == truck_id)
                 and (not before or (a.started_at, a.id) < tuple(before))]
        return deepcopy(sorted(items, key=lambda a: (a.started_at, a.id), reverse=True)[:limit])

    def pending_notifications(self, now, limit=50):
        return deepcopy([a for a in self.alerts.values() if notification_due(a, now)][:limit])

    def alert_stats(self, since):
        return stats([a for a in self.alerts.values() if parse(a.started_at) >= since])

    def save_notification(self, n):
        self.notifications = [x for x in self.notifications if x["id"] != n["id"]] + [deepcopy(n)]

    # --- truck state (door-open start time, last seen)
    def get_state(self, truck_id):
        return deepcopy(self.state.get(truck_id, {"truck_id": truck_id}))

    def save_state(self, state):
        self.state[state["truck_id"]] = deepcopy(state)

    def all_states(self):
        return [dict(s) for s in self.state.values()]

    # --- demo fault table (Azure: chosen on the dashboard, read by the trucks)
    def get_faults(self):
        return dict(self._faults)

    def set_fault(self, truck_id, scenario):
        self._faults[truck_id] = scenario


class CosmosFleetRepository:
    def __init__(self, endpoint, key=None, database="greenops", connection_verify=True, credential=None):
        import azure.cosmos
        from azure.cosmos import PartitionKey
        if credential is not None:  # Azure: managed identity with data-only rights; Terraform created the containers
            self.client = azure.cosmos.CosmosClient(endpoint, credential)
            db = self.client.get_database_client(database)
            self.telemetry, self.alerts, self.reference = (db.get_container_client(c) for c in ("telemetry", "alerts", "reference"))
            return
        self.client = azure.cosmos.CosmosClient(endpoint, key, connection_verify=connection_verify)
        db = self.client.create_database_if_not_exists(database)
        self.telemetry = db.create_container_if_not_exists("telemetry", PartitionKey("/truck_id"), default_ttl=TELEMETRY_TTL_S)
        self.alerts = db.create_container_if_not_exists("alerts", PartitionKey("/truck_id"), indexing_policy={"indexingMode": "consistent", "includedPaths": [{"path": "/*"}], "excludedPaths": [], "compositeIndexes": [[{"path": "/started_at", "order": "descending"}, {"path": "/id", "order": "descending"}]]})
        properties = self.alerts.read()
        policy = properties.get("indexingPolicy", {})
        required = [{"path": "/started_at", "order": "descending"}, {"path": "/id", "order": "descending"}]
        if required not in policy.get("compositeIndexes", []):
            policy.setdefault("compositeIndexes", []).append(required)
            self.alerts = db.replace_container(self.alerts, PartitionKey("/truck_id"), indexing_policy=policy,
                                               default_ttl=properties.get("defaultTtl"),
                                               conflict_resolution_policy=properties.get("conflictResolutionPolicy"))
        self.reference = db.create_container_if_not_exists("reference", PartitionKey("/doc_type"), default_ttl=-1)
        properties = self.reference.read()
        if properties.get("defaultTtl") is None:
            # Enable per-item quarantine expiry without expiring reference/state documents.
            self.reference = db.replace_container(self.reference, PartitionKey("/doc_type"), default_ttl=-1,
                                                  indexing_policy=properties.get("indexingPolicy"),
                                                  conflict_resolution_policy=properties.get("conflictResolutionPolicy"))

    def mutate_truck(self, truck_id, callback):
        from azure.cosmos.exceptions import CosmosBatchOperationError, CosmosResourceNotFoundError
        state_id = f"state-{truck_id}"
        for attempt in range(12):
            try:
                existing = self.alerts.read_item(state_id, partition_key=truck_id)
            except CosmosResourceNotFoundError:
                existing = None
            tx = TruckTransaction(self, truck_id, existing or self.get_state(truck_id))
            result = callback(tx)
            state = {k: v for k, v in tx.state.items() if not k.startswith("_")}
            state.update(id=state_id, truck_id=truck_id, doc_type="truck_state")
            guard = ("replace", (state_id, state), {"if_match_etag": existing["_etag"]}) if existing else ("create", (state,))
            operations = [guard] + [("upsert", (a.to_doc(),)) for a in tx.changed.values()]
            try:
                self.alerts.execute_item_batch(operations, partition_key=truck_id)
                return result
            except CosmosBatchOperationError as e:
                if e.status_code not in (409, 412, 424) or not any(r.get("statusCode") in (409, 412) for r in e.operation_responses):
                    raise
                time.sleep(min(0.005 * 2 ** attempt, 0.2))
        raise RuntimeError("truck state contention; retry delivery")

    def quarantine_event(self, raw, reason, now):
        self.reference.upsert_item(quarantine_doc(raw, reason, now))

    def telemetry_ttl(self):
        return self.telemetry.read().get("defaultTtl")

    def save_readings(self, msgs):
        from azure.cosmos.exceptions import CosmosResourceExistsError
        saved = []
        for m in msgs:
            doc = {**m, "id": f"{m['truck_id']}-{m['timestamp']}"}
            try:
                stored = self.telemetry.create_item(doc)
            except CosmosResourceExistsError:
                stored = self.telemetry.read_item(doc["id"], partition_key=m["truck_id"])
            saved.append({k: v for k, v in stored.items() if not k.startswith("_")})
        return saved

    def latest_readings(self):
        out = []
        for s in self.all_states():
            if s.get("last_reading"):
                out.append(s["last_reading"])
        return out

    def history(self, truck_id, since):
        q = "SELECT * FROM c WHERE c.truck_id = @t AND c.timestamp >= @s ORDER BY c.timestamp"
        return list(self.telemetry.query_items(q, parameters=[{"name": "@t", "value": truck_id}, {"name": "@s", "value": iso(since)}], partition_key=truck_id))

    def count_readings_since(self, since):
        q = "SELECT VALUE COUNT(1) FROM c WHERE c.timestamp >= @s"
        return sum(self.telemetry.query_items(q, parameters=[{"name": "@s", "value": iso(since)}], enable_cross_partition_query=True))

    def _alert_query(self, where, params, **kw):
        q = f"SELECT * FROM c WHERE c.doc_type = 'alert' AND {where}"
        return [Alert.from_doc(d) for d in self.alerts.query_items(q, parameters=params, **kw)]

    def find_open(self, truck_id, alert_type):
        found = self._alert_query("c.type = @ty AND (c.status = 'ACTIVE' OR c.status = 'ACKNOWLEDGED')",
                                  [{"name": "@ty", "value": alert_type}], partition_key=truck_id)
        return found[0] if found else None

    def open_alerts(self, truck_id=None):
        where = "(c.status = 'ACTIVE' OR c.status = 'ACKNOWLEDGED')"
        if truck_id:
            return self._alert_query(where, [], partition_key=truck_id)
        return self._alert_query(where, [], enable_cross_partition_query=True)

    def save_alert(self, alert):
        self.alerts.upsert_item(alert.to_doc())

    def get_alert(self, alert_id):
        found = self._alert_query("c.id = @id", [{"name": "@id", "value": alert_id}], enable_cross_partition_query=True)
        return found[0] if found else None

    def list_alerts(self, limit=50, status=None, before=None, truck_id=None):
        where, params = ("c.status = @st", [{"name": "@st", "value": status}]) if status else ("true", [])
        if truck_id:
            where += " AND c.truck_id = @truck"
            params.append({"name": "@truck", "value": truck_id})
        if before:
            where += " AND (c.started_at < @before OR (c.started_at = @before AND c.id < @id))"
            params += [{"name": "@before", "value": before[0]}, {"name": "@id", "value": before[1]}]
        q = f"SELECT TOP {int(limit)} * FROM c WHERE c.doc_type = 'alert' AND {where} ORDER BY c.started_at DESC, c.id DESC"
        return [Alert.from_doc(d) for d in self.alerts.query_items(q, parameters=params, enable_cross_partition_query=True)]

    def pending_notifications(self, now, limit=50):
        q = f"SELECT TOP {int(limit)} * FROM c WHERE c.doc_type = 'alert' AND (NOT IS_DEFINED(c.email_sent_at) OR IS_NULL(c.email_sent_at)) AND (NOT IS_DEFINED(c.email_status) OR c.email_status IN ('pending', 'failed', 'sending')) AND (NOT IS_DEFINED(c.email_next_attempt) OR IS_NULL(c.email_next_attempt) OR c.email_next_attempt <= @now) AND (NOT IS_DEFINED(c.email_claim_until) OR IS_NULL(c.email_claim_until) OR c.email_claim_until <= @now)"
        return [Alert.from_doc(d) for d in self.alerts.query_items(q, parameters=[{"name": "@now", "value": iso(now)}], enable_cross_partition_query=True)]

    def alert_stats(self, since):
        # Aggregate in Cosmos; never download historical alert documents for health.
        params = [{"name": "@since", "value": iso(since)}]
        where = "c.doc_type = 'alert' AND c.started_at >= @since"
        def scalar(expr, condition=""):
            return sum(v or 0 for v in self.alerts.query_items(f"SELECT VALUE {expr} FROM c WHERE {where}{condition}", parameters=params, enable_cross_partition_query=True))
        sent = " AND IS_STRING(c.email_sent_at)"
        count, emails = scalar("COUNT(1)"), scalar("COUNT(1)", sent)
        seconds = scalar("SUM(c.email_seconds)", sent)
        return {"alerts_today": count, "emails_today": emails, "avg_email_seconds": round(seconds / max(emails, 1), 2)}

    def save_notification(self, n):
        self.alerts.upsert_item({**n, "doc_type": "notification"})

    def get_state(self, truck_id):
        from azure.cosmos.exceptions import CosmosResourceNotFoundError
        try:
            return self.alerts.read_item(f"state-{truck_id}", partition_key=truck_id)
        except CosmosResourceNotFoundError:
            # Read old deployments without destructive data migration. The next transaction moves this state.
            try:
                return self.reference.read_item(f"state-{truck_id}", partition_key="truck_state")
            except CosmosResourceNotFoundError:
                return {"truck_id": truck_id}

    def save_state(self, state):
        self.mutate_truck(state["truck_id"], lambda tx: tx.state.update(state))

    def all_states(self):
        old = {s["truck_id"]: s for s in self.reference.query_items("SELECT * FROM c", partition_key="truck_state")}
        for s in self.alerts.query_items("SELECT * FROM c WHERE c.doc_type = 'truck_state'", enable_cross_partition_query=True):
            old[s["truck_id"]] = s
        return list(old.values())

    def get_faults(self):
        from azure.cosmos.exceptions import CosmosResourceNotFoundError
        try:
            chosen = self.reference.read_item("faults", partition_key="faults")["trucks"]
        except CosmosResourceNotFoundError:
            chosen = {}
        for d in self.reference.query_items("SELECT * FROM c", partition_key="truck_fault"):
            chosen[d["truck_id"]] = d["scenario"]
        return chosen

    def set_fault(self, truck_id, scenario):
        self.reference.upsert_item({"id": truck_id, "doc_type": "truck_fault", "truck_id": truck_id, "scenario": scenario})


def notification_due(a, now):
    return not a.email_sent_at and a.email_status in ("pending", "failed", "sending") and (
        not a.email_next_attempt or parse(a.email_next_attempt) <= now) and (
        not a.email_claim_until or parse(a.email_claim_until) <= now)


def quarantine_doc(raw, reason, now):
    payload = raw.decode(errors="replace") if isinstance(raw, bytes) else json.dumps(raw, default=str)
    return {"id": hashlib.sha256(payload.encode()).hexdigest(), "doc_type": "quarantine",
            "payload": payload[:16384], "reason": reason, "received_at": iso(now), "ttl": TELEMETRY_TTL_S}


def stats(alerts):
    sent = [a for a in alerts if a.email_sent_at]
    return {"alerts_today": len(alerts), "emails_today": len(sent),
            "avg_email_seconds": round(sum(a.email_seconds or 0 for a in sent) / max(1, len(sent)), 2)}


def since_hours(now, hours):
    return now - timedelta(hours=hours)


__all__ = ["InMemoryFleetRepository", "CosmosFleetRepository", "TELEMETRY_TTL_S", "since_hours", "parse"]
