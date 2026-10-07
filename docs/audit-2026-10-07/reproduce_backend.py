import sys, json
from datetime import timedelta
sys.path[:0] = ['/home/canadasun/greenops-cloud-pulse/functions', '/home/canadasun/greenops-cloud-pulse/functions/tests', '/home/canadasun/greenops-cloud-pulse/broker/router']
from test_alerting import reading, setup, T0
from shared.alerting import process_batch
from shared.alert_service import AlertService
from shared.fleet_watcher import check_fleet
from shared.repository import CosmosFleetRepository
from router import Router

repo, n, svc = setup()
process_batch([reading(t=T0+timedelta(seconds=10),temp=10)],repo,svc,T0)
process_batch([reading(t=T0,temp=4)],repo,svc,T0)
print('out_of_order',repo.latest_readings()[0]['timestamp'],[(a.type,a.status) for a in repo.alerts.values()])
repo,n,svc=setup()
batch=[reading(temp=10),reading(t=T0+timedelta(seconds=10),temp=4)]
process_batch(batch,repo,svc,T0); process_batch(batch,repo,svc,T0)
print('replay',len(repo.readings),'readings',len(repo.alerts),'alerts',len(n.sent),'emails')
class FailsOnce:
    calls=0
    def send(self,a):
        self.calls+=1
        if self.calls==1: raise ConnectionError('temporary outage')
        return {}
repo,_,_=setup(); n=FailsOnce(); svc=AlertService(repo,n)
for i in range(3): process_batch([reading(t=T0+timedelta(seconds=i*10),temp=10)],repo,svc,T0)
print('email_recovery',n.calls,'attempts',repo.list_alerts()[0].email_sent_at)
repo,n,svc=setup()
process_batch([reading(eta=T0-timedelta(seconds=1))],repo,svc,T0); check_fleet(repo,svc,T0)
process_batch([reading(t=T0+timedelta(seconds=20),eta=T0+timedelta(hours=1))],repo,svc,T0+timedelta(seconds=20))
check_fleet(repo,svc,T0+timedelta(seconds=20))
print('new_trip_delay',[(a.type,a.status) for a in repo.open_alerts()])
repo,n,svc=setup()
process_batch([reading(temp=20,lim=(-40,60))],repo,svc,T0)
print('spoofed_vaccine_limits',len(repo.alerts),'alerts at 20 C')
repo,n,svc=setup()
try: process_batch([reading(), {'truck_id':'TRK-002'}],repo,svc,T0)
except Exception as e: print('poison_batch',type(e).__name__,len(repo.readings),'stored')
class BadStorage:
    def upload(self,*args): raise ConnectionError('temporary storage outage')
r=Router(lambda _:None,BadStorage()); r.on_message('devices/TRK-001/messages/events/',json.dumps(reading()).encode())
try:r.flush_archive()
except Exception as e:print('archive_failure',type(e).__name__,'remaining',len(r.archive_buffer))
try:r.on_message('devices/TRK-001/messages/events/',b'[]')
except Exception as e:print('router_array',type(e).__name__)
class BadReference:
    def read_item(self,*args,**kwargs):raise ConnectionError('database unavailable')
r=object.__new__(CosmosFleetRepository);r.reference=BadReference()
print('db_outage_hidden',r.get_state('TRK-001'),r.get_faults())
import os
os.environ['REPOSITORY']='memory'
import function_app as app
import azure.functions as func
for fn,params,body in [(app.get_history,{'hours':'abc'},b''),(app.get_history,{'hours':'NaN'},b''),(app.get_alerts,{'limit':'abc'},b''),(app.set_fault,{},b'[1]')]:
    req=func.HttpRequest(method='GET',url='http://local',params=params,route_params={'truck_id':'TRK-001'},body=body)
    try: print('input_validation',fn(req).status_code)
    except Exception as e:print('input_validation',params,body,type(e).__name__)
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
repo,n,svc=setup(); original=repo.find_open; barrier=Barrier(2)
def race_find(*args):
    result=original(*args);barrier.wait();return result
repo.find_open=race_find
with ThreadPoolExecutor(2) as pool:
    list(pool.map(lambda _:svc.raise_or_update('TRK-001','TEMPERATURE','breach',T0),range(2)))
print('concurrent_alert',len(repo.alerts),'open alerts',len(n.sent),'emails')
