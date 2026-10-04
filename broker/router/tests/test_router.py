"""Tests for the message router – local stand-in for IoT Hub message routing (Role 2 – Marcelbriaud Wafotchoupe)."""
import json
from datetime import datetime, timezone

from router import Router, archive_blob_name

MSG = {"truck_id": "TRK-001", "timestamp": "2026-10-03T14:05:00Z", "temp_c": 4.2}


class FakeAlertEndpoint:
    def __init__(self, fail_times=0):
        self.calls, self.fail_times = [], fail_times

    def __call__(self, messages):
        self.calls.append(messages)
        if len(self.calls) <= self.fail_times:
            raise ConnectionError("function not ready")


class FakeArchive:
    def __init__(self):
        self.blobs = {}

    def upload(self, name, data):
        self.blobs[name] = data


def make(fail_times=0, max_batch=50):
    alert, archive = FakeAlertEndpoint(fail_times), FakeArchive()
    return Router(alert, archive, max_batch=max_batch, sleep=lambda s: None), alert, archive


def test_every_message_is_sent_to_the_alert_function():
    r, alert, _ = make()
    r.on_message("devices/TRK-001/messages/events/", json.dumps(MSG).encode())
    r.flush_alerts()
    assert alert.calls == [[MSG]]


def test_messages_are_forwarded_in_batches():
    r, alert, _ = make(max_batch=3)
    for i in range(7):
        r.on_message("devices/TRK-001/messages/events/", json.dumps({**MSG, "n": i}).encode())
    r.flush_alerts()
    assert [len(b) for b in alert.calls] == [3, 3, 1]


def test_failed_delivery_is_retried():  # reliability: IoT Hub keeps the message and retries
    r, alert, _ = make(fail_times=2)
    r.on_message("devices/TRK-001/messages/events/", json.dumps(MSG).encode())
    r.flush_alerts()
    assert len(alert.calls) == 3 and r.stats["delivered"] == 1 and r.stats["dead_lettered"] == 0


def test_message_is_dead_lettered_after_too_many_failures():
    r, alert, archive = make(fail_times=99)
    r.on_message("devices/TRK-001/messages/events/", json.dumps(MSG).encode())
    r.flush_alerts()
    assert r.stats["dead_lettered"] == 1
    assert any(n.startswith("deadletter/") for n in archive.blobs)


def test_archive_batch_is_written_as_json_lines():  # FR-09
    r, _, archive = make()
    for i in range(3):
        r.on_message("devices/TRK-001/messages/events/", json.dumps({**MSG, "n": i}).encode())
    name = r.flush_archive(now=datetime(2026, 10, 3, 14, 5, tzinfo=timezone.utc))
    lines = archive.blobs[name].decode().splitlines()
    assert [json.loads(x)["n"] for x in lines] == [0, 1, 2]
    assert r.flush_archive() is None  # nothing new to write


def test_archive_names_follow_the_iot_hub_date_layout():
    name = archive_blob_name(datetime(2026, 10, 3, 14, 5, 7, tzinfo=timezone.utc), "abc")
    assert name == "telemetry/2026/10/03/14/05-abc.jsonl"


def test_invalid_json_is_counted_and_skipped():
    r, alert, _ = make()
    r.on_message("devices/TRK-001/messages/events/", b"not json")
    r.flush_alerts()
    assert alert.calls == [] and r.stats["invalid"] == 1


def test_device_id_in_payload_must_match_the_topic():  # defence in depth for FR-04
    r, alert, _ = make()
    r.on_message("devices/TRK-001/messages/events/", json.dumps({**MSG, "truck_id": "TRK-002"}).encode())
    r.flush_alerts()
    assert alert.calls == [] and r.stats["invalid"] == 1
