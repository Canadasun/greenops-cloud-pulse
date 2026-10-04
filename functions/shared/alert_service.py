"""AlertService – raise, update, resolve and acknowledge alerts (Role 3 – Shi Wang; Part 2, Figure 4 part C).

One problem = one alert = one email: while an alert of the same type is open (ACTIVE or ACKNOWLEDGED) for a truck,
new evidence only updates last_seen_at.
"""
import logging
import time
import uuid

from .models import Alert, AlertStatus, iso

log = logging.getLogger("alerts")


class AlertService:
    def __init__(self, repo, notifier):
        self.repo, self.notifier = repo, notifier

    def raise_or_update(self, truck_id, alert_type, details, now):
        alert = self.repo.find_open(truck_id, alert_type)
        if alert:
            alert.last_seen_at, alert.details = iso(now), details
            self.repo.save_alert(alert)
            return alert, False
        alert = Alert(truck_id=truck_id, type=alert_type, details=details, started_at=iso(now), last_seen_at=iso(now))
        self.repo.save_alert(alert)
        self._notify(alert, now)
        return alert, True

    def _notify(self, alert, now):
        started = time.monotonic()
        try:
            receipt = self.notifier.send(alert)
        except Exception as e:  # noqa: BLE001 – the alert is kept even if email fails
            log.error("email for %s failed: %s", alert.id, e)
            return
        alert.email_seconds = round(time.monotonic() - started, 3)
        alert.email_sent_at = iso(now)
        self.repo.save_alert(alert)
        self.repo.save_notification({"id": "ntf-" + uuid.uuid4().hex[:12], "alert_id": alert.id, "truck_id": alert.truck_id,
                                     "channel": (receipt or {}).get("channel", "email"), "to": (receipt or {}).get("to"), "sent_at": iso(now)})

    def resolve(self, truck_id, alert_type, now):
        alert = self.repo.find_open(truck_id, alert_type)
        if alert:
            alert.status, alert.resolved_at = AlertStatus.RESOLVED.value, iso(now)
            self.repo.save_alert(alert)
        return alert

    def acknowledge(self, alert_id, user, now):
        alert = self.repo.get_alert(alert_id)
        if not alert or alert.status != AlertStatus.ACTIVE.value:
            return None
        alert.status, alert.acknowledged_by, alert.acknowledged_at = AlertStatus.ACKNOWLEDGED.value, user, iso(now)
        self.repo.save_alert(alert)
        return alert
