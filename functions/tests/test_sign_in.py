"""Sign-in (F12, Part 4 – Role 5, Idowu Ayeni): nothing is shown without a valid session, and only named operators may act."""
import base64
import importlib
import json
from datetime import timedelta

import azure.functions as func
import pytest

from shared import auth, session
from shared.alert_service import AlertService
from shared.alerting import process_batch
from shared.repository import InMemoryFleetRepository
from shared.models import utcnow
from test_alerting import FakeNotifier, reading

KEY = "k" * 48


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("REPOSITORY", "memory")
    monkeypatch.setenv("SESSION_SIGNING_KEY", KEY)
    monkeypatch.setenv("OPERATOR_EMAILS", json.dumps({"Dispatcher@Example.ca": "Dispatcher (Role 5)"}))
    monkeypatch.setenv("FAULTS_READ_TOKEN", "f" * 40)
    monkeypatch.delenv("AUTH_MODE", raising=False)
    module = importlib.import_module("function_app")
    repo, now = InMemoryFleetRepository(), utcnow()
    svc = AlertService(repo, FakeNotifier())
    process_batch([reading(t=now, temp=12, eta=now + timedelta(hours=1))], repo, svc, now)
    monkeypatch.setattr(module, "repo", lambda: repo)
    monkeypatch.setattr(module, "alert_service", lambda: svc)
    return module


def call(fn, token=None, method="GET", body=b"{}", **route):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return fn(func.HttpRequest(method, "http://x/api", headers=headers, params={}, route_params=route, body=body))


def token(email="someone@outlook.com", name=None, **kw):
    return session.issue(email, KEY, **kw)


VIEWS = ["get_trucks", "get_routes", "get_alerts", "get_health", "get_faults", "get_session"]


@pytest.mark.parametrize("view", VIEWS)
def test_every_view_needs_a_session(app, view):
    assert call(getattr(app, view)).status_code == 401
    assert call(getattr(app, view), "rubbish").status_code == 401
    assert call(getattr(app, view), token()).status_code == 200


def test_history_needs_a_session(app):
    assert call(app.get_history, truck_id="TRK-001").status_code == 401
    assert call(app.get_history, token(), truck_id="TRK-001").status_code == 200


def test_any_signed_in_person_can_view_but_not_act(app):
    t = token("visitor@outlook.com")
    assert json.loads(call(app.get_session, t).get_body()) == {"user": "visitor@outlook.com", "can_operate": False}
    alert_id = json.loads(call(app.get_alerts, t).get_body())["items"][0]["id"]
    assert call(app.ack_alert, t, "POST", alert_id=alert_id).status_code == 403
    assert call(app.set_fault, t, "POST", b'{"scenario":"door"}', truck_id="TRK-001").status_code == 403
    assert call(app.clear_fault, t, "DELETE", truck_id="TRK-001").status_code == 403


def test_a_named_operator_can_act_and_the_server_records_who(app):
    t = token("dispatcher@example.ca")  # email case does not matter
    assert json.loads(call(app.get_session, t).get_body()) == {"user": "Dispatcher (Role 5)", "can_operate": True}
    alert_id = json.loads(call(app.get_alerts, t).get_body())["items"][0]["id"]
    done = call(app.ack_alert, t, "POST", b'{"user":"Someone else"}', alert_id=alert_id)
    assert done.status_code == 200 and json.loads(done.get_body())["acknowledged_by"] == "Dispatcher (Role 5)"


def test_trucks_read_their_faults_with_their_own_credential(app):
    assert call(app.get_faults, "f" * 40).status_code == 200
    assert call(app.get_trucks, "f" * 40).status_code == 401  # and it opens nothing else


# --- the session token itself
def test_round_trip_and_expiry():
    now = utcnow()
    t = session.issue("a@b.ca", KEY, now=now, ttl_s=900)
    assert session.verify(t, KEY, now + timedelta(seconds=899))["email"] == "a@b.ca"
    assert session.verify(t, KEY, now + timedelta(seconds=901)) is None


def test_tampering_wrong_key_and_wrong_shape_are_refused():
    t = token()
    head, body, sig = t.split(".")
    forged = base64.urlsafe_b64encode(json.dumps({"email": "dispatcher@example.ca", "iss": session.ISSUER, "aud": session.AUDIENCE, "iat": 0, "exp": 9e9}).encode()).decode().rstrip("=")
    none_alg = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    for bad in (f"{head}.{forged}.{sig}", f"{none_alg}.{body}.", f"{head}.{body}", "", "a.b.c", "é.b.c", t + "x", None):
        assert session.verify(bad, KEY) is None
    assert session.verify(t, "other" * 10) is None


def test_a_token_for_another_audience_or_with_a_very_long_life_is_refused():
    assert session.verify(session.issue("a@b.ca", KEY, audience="someone-else"), KEY) is None
    assert session.verify(session.issue("a@b.ca", KEY, ttl_s=session.MAX_LIFE_S + 1), KEY) is None
    assert session.verify(session.issue("a@b.ca", KEY, now=utcnow() + timedelta(minutes=10)), KEY) is None  # issued in the future


@pytest.mark.parametrize("key", ["", "short"])
def test_a_missing_or_short_signing_key_locks_everyone_out(app, monkeypatch, key):
    monkeypatch.setenv("SESSION_SIGNING_KEY", key)
    assert call(app.get_trucks, session.issue("a@b.ca", key or "x")).status_code == 401


def test_bad_operator_list_gives_view_only_access(app, monkeypatch):
    monkeypatch.setenv("OPERATOR_EMAILS", "not json")
    assert json.loads(call(app.get_session, token("dispatcher@example.ca")).get_body())["can_operate"] is False


def test_open_mode_is_only_for_isolated_tests(app, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "open")
    assert call(app.get_trucks).status_code == 200
    assert call(app.set_fault, None, "POST", b'{"scenario":"door"}', truck_id="TRK-001").status_code == 401  # never opens writes
    assert auth.operator(func.HttpRequest("GET", "http://x", headers={}, body=b"")) is None
