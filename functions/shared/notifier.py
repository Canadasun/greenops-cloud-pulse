"""Notifiers – alert email through the Logic App, and SMS through Azure Monitor (Role 3 – Shi Wang).
Locally both are replaced by the mail-relay service, which accepts the same JSON and delivers to the Mailpit inbox."""
import json
import os
import unicodedata
import urllib.request


class LogicAppNotifier:
    def __init__(self, url=None, to=None):
        self.url = url or os.environ["LOGIC_APP_URL"]
        self.to = to or os.getenv("ALERT_EMAIL_TO", "cold-chain-ops@greenops.local")

    def send(self, alert):
        body = {"to": self.to, "alert_id": alert.id, "truck_id": alert.truck_id, "type": alert.type,
                "details": alert.details, "started_at": alert.started_at}
        headers = {"Content-Type": "application/json", "Idempotency-Key": alert.id}
        if os.getenv("MAIL_RELAY_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["MAIL_RELAY_TOKEN"]
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status >= 300:
                raise ConnectionError(f"logic app returned HTTP {r.status}")
            # Logic Apps returns 202 before the email action executes. Its authenticated callback completes this.
            status = "accepted" if r.status == 202 else "sent"
        return {"channel": "email", "to": self.to, "status": status}


SMS_LIMIT = 160  # one text message


def sms_text(alert):
    """Plain characters only: one accented or special character would double the cost of a text message."""
    text = f"GreenOps {alert.truck_id} {alert.type}: {alert.details}".replace("–", "-").replace("−", "-").replace("°", "").replace("  ", " ")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()[:SMS_LIMIT]


class SmsNotifier:
    """Requests a text message (F13). On Azure the request starts a small Logic App, and an Azure Monitor rule on that workflow
    texts the on-call phones of its action group: the phone numbers exist only in Azure, never in the code or the database."""

    def __init__(self, url):
        self.url = url

    @classmethod
    def from_env(cls):
        return cls(os.environ["SMS_URL"]) if os.getenv("SMS_URL") else None

    def send(self, alert):
        body = {"alert_id": alert.id, "truck_id": alert.truck_id, "type": alert.type, "text": sms_text(alert)}
        headers = {"Content-Type": "application/json", "Idempotency-Key": alert.id}
        if os.getenv("MAIL_RELAY_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["MAIL_RELAY_TOKEN"]
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status >= 300:
                raise ConnectionError(f"sms workflow returned HTTP {r.status}")
        return {"channel": "sms", "status": "requested"}  # the provider gives no delivery receipt, so never claim "sent"
