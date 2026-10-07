"""The Functions app registers every function from Part 2, Figure 5 (local HTTP mode)."""
import importlib
import os


def test_all_functions_are_registered():
    os.environ.setdefault("REPOSITORY", "memory")
    app = importlib.import_module("function_app").app
    names = {f.get_function_name() for f in app.get_functions()}
    assert names == {"alert_function", "fleet_watcher", "get_trucks", "get_routes", "get_history", "get_alerts", "ack_alert", "get_health", "get_faults", "set_fault", "clear_fault", "get_session", "delivery_result", "claim_dispatch"}


def test_cosmos_uses_managed_identity_and_skips_creating_containers(monkeypatch):
    """On Azure there is no database key: the Function signs in with its managed identity, and the containers
    already exist (Terraform), because an identity with data-only rights cannot create them."""
    import azure.cosmos
    from shared.repository import CosmosFleetRepository
    calls = []

    class FakeClient:
        def __init__(self, url, credential, **kw):
            calls.append(("client", credential))

        def create_database_if_not_exists(self, name):
            calls.append("create")

        def get_database_client(self, name):
            calls.append("get-db")
            return type("Db", (), {"get_container_client": lambda self, c: c})()

    monkeypatch.setattr(azure.cosmos, "CosmosClient", FakeClient)
    repo = CosmosFleetRepository("https://x.documents.azure.com", credential="identity-token")
    assert "create" not in calls and "get-db" in calls and repo.alerts == "alerts"
