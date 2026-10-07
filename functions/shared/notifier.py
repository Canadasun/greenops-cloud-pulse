"""Notifier – sends an alert email through the Logic App (Role 3 – Shi Wang).
Locally the Logic App is replaced by the mail-relay service, which accepts the same JSON and sends the email to Mailpit."""
import json
import os
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
