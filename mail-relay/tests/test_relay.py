import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import relay  # noqa: E402

ALERT = {"to": "ops@greenops.local", "alert_id": "alt-1", "truck_id": "TRK-003", "type": "TEMPERATURE",
         "details": "9.1 °C outside 2–8 °C (vaccines)", "started_at": "2026-10-03T14:05:00Z"}


def test_email_has_a_clear_subject_and_all_details():
    m = relay.build_email(ALERT)
    assert m["Subject"] == "[GreenOps] Temperature breach – TRK-003" and m["To"] == "ops@greenops.local"
    body = m.get_content()
    assert "9.1 °C outside 2–8 °C" in body and "alt-1" in body


def test_missing_fields_are_rejected():
    with pytest.raises(ValueError):
        relay.build_email({**ALERT, "truck_id": ""})


def test_send_uses_smtp():
    with mock.patch("smtplib.SMTP") as smtp:
        relay.send(ALERT, host="mailpit", port=1025)
    smtp.assert_called_once_with("mailpit", 1025, timeout=10)
    smtp.return_value.__enter__.return_value.send_message.assert_called_once()
