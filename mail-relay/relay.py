"""Mail relay – local stand-in for the Azure Logic App that emails staff (Role 3 – Shi Wang).
POST / with {"to","alert_id","truck_id","type","details","started_at"} → one email via SMTP (Mailpit locally)."""
import json
import os
import smtplib
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TITLES = {"TEMPERATURE": "Temperature breach", "HUMIDITY": "Humidity breach", "DOOR_OPEN": "Cargo door left open",
          "OFFLINE": "Truck offline", "DELAYED": "Truck delayed"}
REQUIRED = ("to", "alert_id", "truck_id", "type", "details", "started_at")


def build_email(alert, sender="alerts@greenops.local"):
    missing = [k for k in REQUIRED if not alert.get(k)]
    if missing:
        raise ValueError(f"missing fields: {missing}")
    msg = EmailMessage()
    msg["From"], msg["To"] = sender, alert["to"]
    msg["Subject"] = f"[GreenOps] {TITLES.get(alert['type'], alert['type'])} – {alert['truck_id']}"
    msg.set_content(
        f"GreenOps Cloud Pulse alert\n\nTruck: {alert['truck_id']}\nProblem: {TITLES.get(alert['type'], alert['type'])}\n"
        f"Details: {alert['details']}\nStarted (UTC): {alert['started_at']}\nAlert ID: {alert['alert_id']}\n\n"
        "Open the dashboard to view the truck and acknowledge the alert.\n")
    return msg


def send(alert, host=None, port=None):
    with smtplib.SMTP(host or os.getenv("SMTP_HOST", "mailpit"), int(port or os.getenv("SMTP_PORT", "1025")), timeout=10) as s:
        s.send_message(build_email(alert))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._reply(200, {"status": "ok"})

    def do_POST(self):
        try:
            alert = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            send(alert)
        except ValueError as e:
            return self._reply(400, {"error": str(e)})
        except OSError as e:
            return self._reply(502, {"error": f"mail server unavailable: {e}"})
        self._reply(202, {"status": "sent", "alert_id": alert["alert_id"]})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "8070"))), Handler).serve_forever()
