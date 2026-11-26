"""SMS alerts (F13, Part 4 – Role 3, Shi Wang): one short text for a cargo emergency, never a flood, never at the cost of the email."""
from datetime import timedelta
import json
import urllib.request

import pytest

from shared.alert_service import AlertService
from shared.alerting import process_batch
from shared.notifier import SmsNotifier, sms_text
from test_alerting import T0, FakeNotifier, reading
from test_reliability import store  # noqa: F401


class FakeSms:
    def __init__(self, fail=0):
        self.sent, self.fail = [], fail

    def send(self, alert):
        if self.fail:
            self.fail -= 1
            raise ConnectionError("sms provider down")
        self.sent.append(alert)
        return {"channel": "sms", "status": "requested"}


def breach(store, svc, at=T0, **kw):
    process_batch([reading(t=at, **(kw or {"temp": 12}))], store, svc, at)


def test_temperature_breach_sends_one_text_and_one_email(store):  # noqa: F811
    email, sms = FakeNotifier(), FakeSms()
    svc = AlertService(store, email, sms)
    for i in range(5):  # five breaching readings, still one problem
        breach(store, svc, T0 + timedelta(seconds=10 * i))
    assert len(sms.sent) == 1 and len(email.sent) == 1
    a = store.list_alerts()[0]
    assert a.sms_status == "requested" and a.sms_requested_at


def test_humidity_breach_is_texted_too(store):  # noqa: F811
    sms = FakeSms(); svc = AlertService(store, FakeNotifier(), sms)
    breach(store, svc, hum=90)
    assert [a.type for a in sms.sent] == ["HUMIDITY"]


def test_less_urgent_alerts_are_emailed_but_not_texted(store):  # noqa: F811
    email, sms = FakeNotifier(), FakeSms(); svc = AlertService(store, email, sms)
    svc.raise_or_update("TRK-001", "DELAYED", "5 min past scheduled arrival", T0)
    assert len(email.sent) == 1 and sms.sent == []
    assert store.list_alerts()[0].sms_status is None


def test_without_an_sms_channel_nothing_changes(store):  # noqa: F811
    svc = AlertService(store, FakeNotifier()); breach(store, svc)
    assert store.list_alerts()[0].sms_status is None


def test_a_failed_text_is_retried_a_few_times_then_stopped_and_never_blocks_the_email(store):  # noqa: F811
    email, sms = FakeNotifier(), FakeSms(fail=99); svc = AlertService(store, email, sms)
    breach(store, svc)
    assert len(email.sent) == 1 and store.list_alerts()[0].sms_status == "failed"
    for m in range(1, 30):
        svc.retry_notifications(T0 + timedelta(minutes=m))
    a = store.list_alerts()[0]
    assert a.sms_status == "abandoned" and a.sms_attempts == AlertService.MAX_SMS_ATTEMPTS and len(email.sent) == 1


def test_a_text_that_failed_once_is_delivered_on_the_retry(store):  # noqa: F811
    sms = FakeSms(fail=1); svc = AlertService(store, FakeNotifier(), sms); breach(store, svc)
    svc.retry_notifications(T0 + timedelta(seconds=5))  # too early
    assert sms.sent == []
    svc.retry_notifications(T0 + timedelta(minutes=2))
    assert len(sms.sent) == 1 and store.list_alerts()[0].sms_status == "requested"


def test_a_problem_that_ended_before_the_retry_is_not_texted(store):  # noqa: F811
    sms = FakeSms(fail=1); svc = AlertService(store, FakeNotifier(), sms); breach(store, svc)
    process_batch([reading(t=T0 + timedelta(seconds=10), temp=4)], store, svc, T0 + timedelta(seconds=10))
    svc.retry_notifications(T0 + timedelta(minutes=2))
    assert sms.sent == [] and store.list_alerts()[0].sms_status == "cancelled"


def test_two_workers_cannot_text_the_same_alert_twice(store):  # noqa: F811
    sms = FakeSms(); svc = AlertService(store, FakeNotifier(), sms)
    breach(store, svc)
    svc.deliver_sms(store.list_alerts()[0].id, T0)
    assert len(sms.sent) == 1


def test_text_fits_one_sms_and_uses_plain_characters():
    from shared.models import Alert, iso
    text = sms_text(Alert("TRK-003", "TEMPERATURE", "12.0 °C outside 2–8 °C (vaccines)" + "x" * 300, iso(T0), iso(T0)))
    assert len(text) <= 160 and text.isascii() and text.startswith("GreenOps TRK-003 TEMPERATURE: 12.0 C outside 2-8 C (vaccines)")


def test_notifier_posts_the_text_with_the_service_credential(monkeypatch):
    from shared.models import Alert, iso
    seen = {}

    class Reply:
        status = 202
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake(req, timeout):
        seen.update(url=req.full_url, body=json.loads(req.data), auth=req.headers.get("Authorization"))
        return Reply()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setenv("MAIL_RELAY_TOKEN", "t" * 32)
    out = SmsNotifier("https://example.test/sms").send(Alert("TRK-003", "HUMIDITY", "humidity 90 % above 75 %", iso(T0), iso(T0), id="alt-1"))
    assert out["status"] == "requested" and seen["body"]["alert_id"] == "alt-1" and seen["auth"] == "Bearer " + "t" * 32
    assert "phone" not in json.dumps(seen["body"]) and "to" not in seen["body"]  # numbers live in Azure Monitor only


def test_sms_channel_is_off_unless_configured(monkeypatch):
    monkeypatch.delenv("SMS_URL", raising=False)
    assert SmsNotifier.from_env() is None
    monkeypatch.setenv("SMS_URL", "https://example.test/sms")
    assert isinstance(SmsNotifier.from_env(), SmsNotifier)
