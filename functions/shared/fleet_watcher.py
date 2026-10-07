"""Fleet checks and notification recovery, serialized with each truck's ingestion."""
import os
from .models import iso, parse
from .reference import destination, fleet, km_between

ARRIVED_WITHIN_KM = 1.0


def check_fleet(repo, alerts, now, offline_after_s=None):
    offline_after_s = int(os.getenv('OFFLINE_AFTER_S', '300')) if offline_after_s is None else offline_after_s
    raised = []
    for truck in fleet()['trucks']:
        def check(tx):
            state = tx.state
            state.setdefault('activated_at', iso(now))
            last = state.get('last_reading')
            silent_s = (now - parse(state.get('last_seen') or state['activated_at'])).total_seconds()
            found = []
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
        raised.extend(repo.mutate_truck(truck['truck_id'], check))
    alerts.retry_notifications(now)
    return raised
