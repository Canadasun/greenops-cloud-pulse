"""The Functions app registers every function from Part 2, Figure 5 (local HTTP mode)."""
import importlib
import os


def test_all_functions_are_registered():
    os.environ.setdefault("REPOSITORY", "memory")
    app = importlib.import_module("function_app").app
    names = {f.get_function_name() for f in app.get_functions()}
    assert names == {"alert_function", "fleet_watcher", "get_trucks", "get_routes", "get_history", "get_alerts", "ack_alert", "get_health"}
