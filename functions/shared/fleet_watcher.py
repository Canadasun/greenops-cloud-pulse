"""Fleet Watcher – offline and delayed trucks, and notification recovery (Role 3 – Shi Wang; FR-08).

Runs every minute. It reads the whole fleet in one query, decides on that copy, and only opens a transaction for a truck whose
state or alerts must change. A quiet or parked fleet therefore costs one query a minute, whatever its size.
"""
import os
from copy import deepcopy

from .models import OPEN_STATUSES, iso, parse
from .reference import destination, fleet, km_between

ARRIVED_WITHIN_KM = 1.0


def is_parked(state):
    return bool(state.get('parked_at')) and state.get('last_seen') == state['parked_at']


class _DryRun:
    """Stands in for a TruckTransaction: the same check runs on a snapshot copy and nothing is stored."""
    def __init__(self, truck_id, state, open_alerts):
        self.truck_id, self.state = truck_id, deepcopy(state)
        self.open, self.changed = {a.id: deepcopy(a) for a in open_alerts}, {}

    def find_open(self, alert_type):
        return next((a for a in self.open.values() if a.type == alert_type and a.status in OPEN_STATUSES), None)

    def save_alert(self, alert):
        self.changed[alert.id] = self.open[alert.id] = alert


def check_truck(tx, alerts, now, offline_after_s):
    """Raise, update or resolve this truck's OFFLINE and DELAYED alerts; returns the alerts that are new."""
    state = tx.state
    state.setdefault('activated_at', iso(now))
    last = state.get('last_reading')
    silent_s = (now - parse(state.get('last_seen') or state['activated_at'])).total_seconds()
    found = []
    if is_parked(state):  # planned end of a demo run: no offline or delayed alerts until it sends again
        alerts.resolve_in(tx, 'OFFLINE', now)
        alerts.resolve_in(tx, 'DELAYED', now)
        return found
    if silent_s > offline_after_s:
        a, new = alerts.raise_in(tx, 'OFFLINE', f'no data for {int(silent_s // 60)} min {int(silent_s % 60)} s', now)
        if new:
            found.append(a)
    elif last:
        alerts.resolve_in(tx, 'OFFLINE', now)
    if last:
        arrived = km_between((last['lat'], last['lon']), destination(last['route_id'])) <= ARRIVED_WITHIN_KM
        if arrived or now <= parse(last['scheduled_eta']):
            alerts.resolve_in(tx, 'DELAYED', now)
        else:
            late = int((now - parse(last['scheduled_eta'])).total_seconds() // 60)
            a, new = alerts.raise_in(tx, 'DELAYED', f'{late} min past scheduled arrival', now)
            if new:
                found.append(a)
    return found


def check_fleet(repo, alerts, now, offline_after_s=None):
    offline_after_s = int(os.getenv('OFFLINE_AFTER_S', '300')) if offline_after_s is None else offline_after_s
    snapshot = repo.fleet_snapshot()
    open_by_truck = {}
    for a in snapshot.open_alerts:
        open_by_truck.setdefault(a.truck_id, []).append(a)
    raised = []
    for truck in fleet()['trucks']:
        truck_id = truck['truck_id']
        state = snapshot.states.get(truck_id, {'truck_id': truck_id})
        trial = _DryRun(truck_id, state, open_by_truck.get(truck_id, []))
        check_truck(trial, alerts, now, offline_after_s)
        if trial.changed or trial.state != state:
            # The real decision is made again inside the transaction, on current data.
            raised.extend(repo.mutate_truck(truck_id, lambda tx: check_truck(tx, alerts, now, offline_after_s)))
    alerts.retry_notifications(now)
    return raised
