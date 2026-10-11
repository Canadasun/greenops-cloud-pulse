from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import os
import uuid
import pytest
import azure.functions as func
from shared.alert_service import AlertService
from shared.alerting import process_batch
from shared.fleet_watcher import check_fleet
from shared.repository import InMemoryFleetRepository, CosmosFleetRepository
from shared.models import Alert, iso, parse
from shared import dashboard_api as api
from test_alerting import reading, T0, FakeNotifier


@pytest.fixture(params=['memory'] + (['cosmos'] if os.getenv('COSMOS_ENDPOINT') else []))
def store(request):
    if request.param == 'memory':
        yield InMemoryFleetRepository()
    else:
        from test_repository_contract import EMULATOR_KEY
        name = 'test-audit-' + uuid.uuid4().hex[:8]
        repo = CosmosFleetRepository(os.environ['COSMOS_ENDPOINT'], os.getenv('COSMOS_KEY', EMULATOR_KEY), database=name)
        try:
            yield repo
        finally:
            repo.client.delete_database(name)


def test_late_and_replayed_readings_do_not_change_current_incident(store):
    notifier = FakeNotifier(); svc = AlertService(store, notifier)
    process_batch([reading(t=T0 + timedelta(seconds=10), temp=10)], store, svc, T0 + timedelta(seconds=10))
    process_batch([reading(temp=4)], store, svc, T0 + timedelta(seconds=11))
    assert store.latest_readings()[0]['temp_c'] == 10
    assert len(store.open_alerts()) == 1
    batch = [reading(t=T0 + timedelta(seconds=20), temp=4), reading(t=T0 + timedelta(seconds=30), temp=10)]
    process_batch(batch, store, svc, T0 + timedelta(seconds=30))
    process_batch(batch, store, svc, T0 + timedelta(seconds=31))
    assert len(store.list_alerts()) == 2 and len(notifier.sent) == 2


def test_malformed_event_is_quarantined_without_losing_valid_event(store):
    svc = AlertService(store, FakeNotifier())
    for bad in [[], None, {'truck_id':'TRK-001'}, b'not json', reading(temp=float('nan')), reading(route='unknown')]:
        process_batch([bad, reading()], store, svc, T0)
    assert store.count_readings_since(T0) == 1
    assert store.latest_readings()[0]['truck_id'] == 'TRK-001'


def test_server_limits_override_device_limits(store):
    process_batch([reading(temp=20, lim=(-40,60))], store, AlertService(store, FakeNotifier()), T0)
    assert store.open_alerts()[0].type == 'TEMPERATURE'
    assert store.latest_readings()[0]['temp_max_c'] == 8


def test_failed_notification_retries_even_after_incident_resolves(store):
    class Once:
        calls = 0
        def send(self, alert):
            self.calls += 1
            if self.calls == 1: raise ConnectionError('temporary')
            return {'status':'sent'}
    n=Once();svc=AlertService(store,n)
    process_batch([reading(temp=10)],store,svc,T0)
    process_batch([reading(t=T0+timedelta(seconds=10),temp=4)],store,svc,T0+timedelta(seconds=10))
    svc.retry_notifications(T0+timedelta(seconds=31))
    a=store.list_alerts()[0]
    assert a.status == 'RESOLVED' and a.email_status == 'sent' and n.calls == 2
    svc.retry_notifications(T0+timedelta(seconds=60));assert n.calls == 2


def test_concurrent_creation_and_delivery_is_one_incident(store):
    n=FakeNotifier();svc=AlertService(store,n)
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda _:svc.raise_or_update('TRK-001','TEMPERATURE','hot',T0),range(4)))
    assert len(store.open_alerts()) == 1 and len(n.sent) == 1


def test_resolving_and_acknowledging_cannot_reopen_incident(store):
    svc=AlertService(store,FakeNotifier());a,_=svc.raise_or_update('TRK-001','TEMPERATURE','hot',T0)
    with ThreadPoolExecutor(2) as pool:
        calls=[pool.submit(svc.resolve,'TRK-001','TEMPERATURE',T0),pool.submit(svc.acknowledge,a.id,'operator',T0)]
        for call in calls:call.result()
    assert store.get_alert(a.id).status == 'RESOLVED'


def test_new_trip_closes_previous_delay(store):
    svc=AlertService(store,FakeNotifier())
    process_batch([reading(eta=T0-timedelta(seconds=1))],store,svc,T0);check_fleet(store,svc,T0)
    process_batch([reading(t=T0+timedelta(seconds=10),eta=T0+timedelta(hours=1))],store,svc,T0+timedelta(seconds=10))
    assert not [a for a in store.open_alerts() if a.type=='DELAYED']


def test_open_incident_not_hidden_by_resolved_history_and_stable_cursor(store):
    for i in range(55):
        store.save_alert(Alert('TRK-001','TEMPERATURE','x',iso(T0+timedelta(seconds=i)),iso(T0),id=f'alert-{i:03}',status='ACTIVE' if i==0 else 'RESOLVED'))
    assert len(api.alert_page(store,status='OPEN')['items']) == 1
    first=api.alert_page(store,limit=20,status='RESOLVED')
    second=api.alert_page(store,limit=20,status='RESOLVED',cursor=first['next_cursor'])
    assert len(first['items'])==20 and len(second['items'])==20
    assert not {a['id'] for a in first['items']} & {a['id'] for a in second['items']}


def test_fault_edits_do_not_replace_other_trucks(store):
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda t:store.set_fault(t,'door'),['TRK-001','TRK-002']))
    assert store.get_faults()=={'TRK-001':'door','TRK-002':'door'}


def test_never_reporting_truck_alerts_after_grace():
    repo=InMemoryFleetRepository();svc=AlertService(repo,FakeNotifier())
    check_fleet(repo,svc,T0);assert not repo.open_alerts()
    check_fleet(repo,svc,T0+timedelta(seconds=301))
    assert len(repo.open_alerts())==6


def test_accepted_notification_is_not_reported_sent():
    repo=InMemoryFleetRepository()
    class Accepted:
        def send(self,a):return {'status':'accepted'}
    svc=AlertService(repo,Accepted());a,_=svc.raise_or_update('TRK-001','TEMPERATURE','hot',T0)
    assert a.email_sent_at is None and a.email_status=='accepted'
    svc.delivery_result(a.id,'sent',T0+timedelta(seconds=8))
    assert repo.get_alert(a.id).email_seconds==8


def test_database_error_is_not_empty_state():
    class Broken:
        def read_item(self,*args,**kw):raise ConnectionError('offline')
    repo=object.__new__(CosmosFleetRepository);repo.alerts=repo.reference=Broken()
    with pytest.raises(ConnectionError):repo.get_state('TRK-001')
    with pytest.raises(ConnectionError):repo.get_faults()


def request(body=b'{}',params=None,token=''):
    return func.HttpRequest('POST','http://localhost',headers={'Authorization':'Bearer '+token},params=params or {},route_params={'truck_id':'TRK-001','alert_id':'missing'},body=body)


def test_http_validation_and_authentication(monkeypatch):
    import function_app as app
    monkeypatch.setenv('OPERATOR_TOKENS',json.dumps({'valid-key':'Actual operator'}))
    monkeypatch.setenv('REPOSITORY','memory');app.repo.cache_clear()
    for handler in [app.ack_alert,app.set_fault,app.clear_fault,app.alert_function,app.delivery_result]:
        assert handler(request()).status_code==401
    for val in ['NaN','abc','-1','25']:
        assert app.get_history(request(params={'hours':val})).status_code==400
    for val in ['abc','0','101','-5']:
        assert app.get_alerts(request(params={'limit':val})).status_code==400
    assert app.set_fault(request(body=b'[1]',token='valid-key')).status_code==400
    assert json.loads(app.get_session(request(token='valid-key')).get_body())['user']=='Actual operator'
    class Svc:
        def acknowledge(self,alert_id,user,now):
            assert user=='Actual operator'
            return None
    monkeypatch.setattr(app,'alert_service',lambda:Svc())
    assert app.ack_alert(request(body=b'{"user":"spoof"}',token='valid-key')).status_code==409


def test_repeated_cloud_trigger_has_one_workflow_dispatch(store):
    svc=AlertService(store,FakeNotifier())
    alert=Alert('TRK-001','TEMPERATURE','hot',iso(T0),iso(T0))
    store.save_alert(alert)
    assert svc.claim_workflow(alert.id,'run-one')
    assert svc.claim_workflow(alert.id,'run-one')  # response lost, same workflow retries
    assert not svc.claim_workflow(alert.id,'duplicate-run')
    svc.delivery_result(alert.id,'failed',T0,'run-one')
    assert svc.claim_workflow(alert.id,'retry-run')
    svc.delivery_result(alert.id,'sent',T0,'run-one')  # late old callback must be ignored
    assert store.get_alert(alert.id).email_sent_at is None
    svc.delivery_result(alert.id,'sent',T0,'retry-run')
    assert not svc.claim_workflow(alert.id,'third-run')


def test_replayed_payload_cannot_rewrite_original_history(store):
    svc=AlertService(store,FakeNotifier())
    process_batch([reading(temp=10)],store,svc,T0)
    process_batch([reading(temp=4)],store,svc,T0)
    assert store.history('TRK-001',T0)[0]['temp_c']==10
    assert store.latest_readings()[0]['temp_c']==10


def test_cosmos_health_aggregates_match_saved_incidents(store):
    svc=AlertService(store,FakeNotifier())
    process_batch([reading(temp=10)],store,svc,T0)
    stats=store.alert_stats(T0)
    assert stats['alerts_today']==1 and stats['emails_today']==1


def test_failed_workflow_callbacks_back_off_and_then_stop(store):
    """A provider that keeps refusing (e.g. email throttling) must not be retried every minute forever."""
    class Accepted:
        calls = 0
        def send(self, a):
            self.calls += 1
            return {'status': 'accepted'}
    n = Accepted(); svc = AlertService(store, n)
    a, _ = svc.raise_or_update('TRK-001', 'DELAYED', 'late', T0)
    now = T0
    waits = []
    for _ in range(20):
        svc.claim_workflow(a.id, f'run-{n.calls}')
        svc.delivery_result(a.id, 'failed', now, f'run-{n.calls}')
        current = store.get_alert(a.id)
        if current.email_status == 'abandoned':
            break
        waits.append((parse(current.email_next_attempt) - now).total_seconds())
        now = parse(current.email_next_attempt)
        svc.retry_notifications(now)
    assert store.get_alert(a.id).email_status == 'abandoned'
    assert n.calls == AlertService.MAX_EMAIL_ATTEMPTS
    assert waits == sorted(waits) and waits[-1] > waits[0]  # exponential, not a fixed minute
    svc.retry_notifications(now + timedelta(days=1))
    assert n.calls == AlertService.MAX_EMAIL_ATTEMPTS


def test_direct_send_failures_stop_after_the_attempt_limit(store):
    class Down:
        calls = 0
        def send(self, a):
            self.calls += 1
            raise ConnectionError('HTTP 429')
    n = Down(); svc = AlertService(store, n)
    a, _ = svc.raise_or_update('TRK-001', 'TEMPERATURE', 'hot', T0)
    for minute in range(1, 24 * 60, 5):
        svc.retry_notifications(T0 + timedelta(minutes=minute))
    assert n.calls == AlertService.MAX_EMAIL_ATTEMPTS
    assert store.get_alert(a.id).email_status == 'abandoned'


def test_legacy_alert_past_the_limit_is_abandoned_without_sending(store):
    n = FakeNotifier(); svc = AlertService(store, n)
    alert = Alert('TRK-001', 'DELAYED', 'late', iso(T0), iso(T0), email_status='failed', email_attempts=400)
    store.save_alert(alert)
    svc.retry_notifications(T0)
    assert not n.sent and store.get_alert(alert.id).email_status == 'abandoned'


def test_idle_fleet_check_does_not_rewrite_unchanged_state(store):
    svc = AlertService(store, FakeNotifier())
    process_batch([reading()], store, svc, T0)
    check_fleet(store, svc, T0 + timedelta(seconds=30))
    writes = []
    original = store.save_state if isinstance(store, InMemoryFleetRepository) else None
    if isinstance(store, InMemoryFleetRepository):
        store.save_state = lambda s: (writes.append(s), original(s))
    else:
        batch = store.alerts.execute_item_batch
        store.alerts.execute_item_batch = lambda *a, **k: (writes.append(a), batch(*a, **k))[1]
    check_fleet(store, svc, T0 + timedelta(seconds=60))
    assert writes == []


def test_accepted_email_without_a_callback_is_retried_later_but_not_duplicated(store):
    class Accepted:
        calls = 0
        def send(self, a):
            self.calls += 1
            return {'status': 'accepted'}
    n = Accepted(); svc = AlertService(store, n)
    a, _ = svc.raise_or_update('TRK-001', 'TEMPERATURE', 'hot', T0)
    assert svc.claim_workflow(a.id, 'run-lost')  # that run dies before it reports a result
    svc.retry_notifications(T0 + timedelta(minutes=5))
    assert n.calls == 1  # still waiting for the provider
    svc.retry_notifications(T0 + timedelta(minutes=16))
    assert n.calls == 2
    assert not svc.claim_workflow(a.id, 'run-two')  # the lost run may have sent it: never a second email
