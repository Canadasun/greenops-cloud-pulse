"""FleetRepository – the only code that talks to the database (Role 4 – Durmusali Unal; Part 2, Figures 5–6, Table 2).

Containers (all partitioned so one truck's data is stored together):
  telemetry  – TELEMETRY_READING, partition /truck_id, default time-to-live 7 days
  alerts     – ALERT and NOTIFICATION, partition /truck_id
  reference  – TRUCK state, partition /doc_type
Two implementations share one interface: CosmosFleetRepository (Cosmos DB / emulator) and InMemoryFleetRepository (tests).
"""
from datetime import timedelta

from .models import OPEN_STATUSES, Alert, iso, parse

TELEMETRY_TTL_S = 7 * 24 * 3600


class InMemoryFleetRepository:
    def __init__(self):
        self._readings, self.alerts, self.state, self.notifications = {}, {}, {}, []

    @property
    def readings(self):
        return list(self._readings.values())

    # --- telemetry (upsert by id, like Cosmos DB, so a retried delivery is not stored twice)
    def save_readings(self, msgs):
        for m in msgs:
            doc = {**m, "id": f"{m['truck_id']}-{m['timestamp']}"}
            self._readings[doc["id"]] = doc

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
                return a
        return None

    def open_alerts(self, truck_id=None):
        return [a for a in self.alerts.values() if a.status in OPEN_STATUSES and (truck_id is None or a.truck_id == truck_id)]

    def save_alert(self, alert):
        self.alerts[alert.id] = alert

    def get_alert(self, alert_id):
        return self.alerts.get(alert_id)

    def list_alerts(self, limit=50, status=None):
        items = [a for a in self.alerts.values() if status is None or a.status == status]
        return sorted(items, key=lambda a: a.started_at, reverse=True)[:limit]

    def save_notification(self, n):
        self.notifications.append(n)

    # --- truck state (door-open start time, last seen)
    def get_state(self, truck_id):
        return dict(self.state.get(truck_id, {"truck_id": truck_id}))

    def save_state(self, state):
        self.state[state["truck_id"]] = dict(state)

    def all_states(self):
        return [dict(s) for s in self.state.values()]


class CosmosFleetRepository:
    def __init__(self, endpoint, key, database="greenops", connection_verify=True):
        from azure.cosmos import CosmosClient, PartitionKey
        self.client = CosmosClient(endpoint, key, connection_verify=connection_verify)
        db = self.client.create_database_if_not_exists(database)
        self.telemetry = db.create_container_if_not_exists("telemetry", PartitionKey("/truck_id"), default_ttl=TELEMETRY_TTL_S)
        self.alerts = db.create_container_if_not_exists("alerts", PartitionKey("/truck_id"))
        self.reference = db.create_container_if_not_exists("reference", PartitionKey("/doc_type"))

    def telemetry_ttl(self):
        return self.telemetry.read().get("defaultTtl")

    def save_readings(self, msgs):
        for m in msgs:
            self.telemetry.upsert_item({**m, "id": f"{m['truck_id']}-{m['timestamp']}"})

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

    def list_alerts(self, limit=50, status=None):
        where, params = ("c.status = @st", [{"name": "@st", "value": status}]) if status else ("true", [])
        items = self._alert_query(where, params, enable_cross_partition_query=True)
        return sorted(items, key=lambda a: a.started_at, reverse=True)[:limit]

    def save_notification(self, n):
        self.alerts.upsert_item({**n, "doc_type": "notification"})

    def get_state(self, truck_id):
        try:
            return self.reference.read_item(f"state-{truck_id}", partition_key="truck_state")
        except Exception:  # noqa: BLE001 – not found yet
            return {"truck_id": truck_id}

    def save_state(self, state):
        self.reference.upsert_item({**state, "id": f"state-{state['truck_id']}", "doc_type": "truck_state"})

    def all_states(self):
        return list(self.reference.query_items("SELECT * FROM c", partition_key="truck_state"))


def since_hours(now, hours):
    return now - timedelta(hours=hours)


__all__ = ["InMemoryFleetRepository", "CosmosFleetRepository", "TELEMETRY_TTL_S", "since_hours", "parse"]
