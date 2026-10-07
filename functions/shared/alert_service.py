"""Atomic incident transitions and durable notification delivery.

The alert document is also its outbox entry. External I/O only occurs after commit.
A claim prevents concurrent senders; the same alert ID is the delivery idempotency key.
"""
import logging
import uuid
import time
from datetime import timedelta

from .models import Alert, AlertStatus, iso, parse, utcnow
from .repository import notification_due

log = logging.getLogger('alerts')


class AlertService:
    def __init__(self, repo, notifier):
        self.repo, self.notifier = repo, notifier

    @staticmethod
    def raise_in(tx, alert_type, details, now, event_at=None):
        alert = tx.find_open(alert_type)
        new = alert is None
        if new:
            alert = Alert(tx.truck_id, alert_type, details, iso(event_at or now), iso(now))
        else:
            alert.last_seen_at, alert.details = iso(now), details
        tx.save_alert(alert)
        return alert, new

    @staticmethod
    def resolve_in(tx, alert_type, now):
        # Repair legacy duplicates together; newly created incidents are serialized.
        found = [a for a in tx.open.values() if a.type == alert_type and a.status in ('ACTIVE', 'ACKNOWLEDGED')]
        for alert in found:
            alert.status, alert.resolved_at = AlertStatus.RESOLVED.value, iso(now)
            tx.save_alert(alert)
        return found[0] if found else None

    def raise_or_update(self, truck_id, alert_type, details, now):
        alert, new = self.repo.mutate_truck(truck_id, lambda tx: self.raise_in(tx, alert_type, details, now))
        self.deliver(alert.id, now)
        return self.repo.get_alert(alert.id), new

    def resolve(self, truck_id, alert_type, now):
        return self.repo.mutate_truck(truck_id, lambda tx: self.resolve_in(tx, alert_type, now))

    def acknowledge(self, alert_id, user, now):
        original = self.repo.get_alert(alert_id)
        if not original:
            return None
        def change(tx):
            alert = tx.get_alert(alert_id)
            if not alert or alert.status != AlertStatus.ACTIVE.value:
                return None
            alert.status, alert.acknowledged_by, alert.acknowledged_at = 'ACKNOWLEDGED', user, iso(now)
            tx.save_alert(alert)
            return alert
        return self.repo.mutate_truck(original.truck_id, change)

    def retry_notifications(self, now):
        for alert in self.repo.pending_notifications(now):
            self.deliver(alert.id, now)

    def deliver(self, alert_id, now):
        original = self.repo.get_alert(alert_id)
        if not original:
            return
        claim_id = uuid.uuid4().hex
        def claim(tx):
            alert = tx.get_alert(alert_id)
            if not notification_due(alert, now):
                return None
            alert.email_status = 'sending'
            alert.email_claim, alert.email_claim_until = claim_id, iso(now + timedelta(minutes=2))
            alert.email_attempts += 1
            tx.save_alert(alert)
            return alert
        alert = self.repo.mutate_truck(original.truck_id, claim)
        if not alert:
            return
        receipt, error = None, None
        started = time.monotonic()
        try:
            receipt = self.notifier.send(alert) or {}
        except Exception as e:
            error = str(e)[:500]
            log.warning('notification %s attempt %s failed: %s', alert.id, alert.email_attempts, error)
        completed_at = now + timedelta(seconds=time.monotonic() - started)
        def finish(tx):
            current = tx.get_alert(alert_id)
            if current.email_claim != claim_id or current.email_status != 'sending':
                return
            current.email_claim = current.email_claim_until = None
            current.email_error = error
            if error:
                current.email_status = 'failed'
                current.email_next_attempt = iso(now + timedelta(seconds=min(30 * 2 ** min(current.email_attempts - 1, 7), 3600)))
            else:
                current.email_status = receipt.get('status', 'sent')
                current.email_next_attempt = None
                if current.email_status == 'sent':
                    current.email_sent_at = iso(completed_at)
                    current.email_seconds = round(max(0, (completed_at - parse(current.started_at)).total_seconds()), 3)
                else:
                    current.email_accepted_at = iso(now)
            tx.save_alert(current)
        self.repo.mutate_truck(original.truck_id, finish)
        current = self.repo.get_alert(alert_id)
        if current.email_sent_at:
            self.repo.save_notification({'id': f'ntf-{alert.id}', 'alert_id': alert.id, 'truck_id': alert.truck_id,
                                         'channel': 'email', 'to': (receipt or {}).get('to'), 'sent_at': current.email_sent_at})

    def claim_workflow(self, alert_id, workflow_id):
        original = self.repo.get_alert(alert_id)
        if not original:
            return False
        def claim(tx):
            a = tx.get_alert(alert_id)
            if a.email_sent_at or (a.email_workflow_id and a.email_workflow_id != workflow_id):
                return False
            a.email_workflow_id = workflow_id
            tx.save_alert(a)
            return True
        return self.repo.mutate_truck(original.truck_id, claim)

    def delivery_result(self, alert_id, status, now, workflow_id=None):
        """Authenticated workflow callback: accepted is not a completed send."""
        original = self.repo.get_alert(alert_id)
        if not original:
            return None
        def change(tx):
            a = tx.get_alert(alert_id)
            if workflow_id is not None and a.email_workflow_id != workflow_id:
                return a  # a late callback cannot change a newer dispatch attempt
            if a.email_status == 'sent':
                return a
            a.email_status = status
            a.email_claim = a.email_claim_until = None
            if status == 'sent':
                a.email_sent_at = iso(now)
                a.email_seconds = round(max(0, (now - parse(a.started_at)).total_seconds()), 3)
            else:
                a.email_error = 'Email workflow failed'
                a.email_next_attempt = iso(now + timedelta(minutes=1))
                a.email_workflow_id = None
            tx.save_alert(a)
            return a
        return self.repo.mutate_truck(original.truck_id, change)
