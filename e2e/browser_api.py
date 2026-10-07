"""Isolated HTTP adapter for the actual Functions handlers, seeded with deterministic data.

Used by browser_regressions.cjs; it never connects to Azure or the shared local fleet.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl
from datetime import timedelta
import json
import os
import sys
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'functions'))
os.environ['OPERATOR_TOKENS'] = json.dumps({'browser-test-key': 'Browser operator'})
import azure.functions as func
import function_app as app
from shared.repository import InMemoryFleetRepository
from shared.alert_service import AlertService
from shared.alerting import process_batch
from shared.models import utcnow, iso, Alert
from shared.reference import fleet, cargo_profiles
repo = InMemoryFleetRepository()
class Notifier:
    def send(self, alert): return {'status':'sent'}
svc = AlertService(repo, Notifier())
app.repo = lambda: repo
app.alert_service = lambda: svc
now=utcnow()
for truck in fleet()['trucks']:
    if truck['truck_id'] not in ('TRK-001','TRK-004'):continue
    profile=cargo_profiles()[truck['cargo_type']]
    route=fleet()['routes'][truck['route_id']]
    for seconds in [20,10]:
        msg={**truck,'timestamp':iso(now-timedelta(seconds=seconds)),'lat':route['waypoints'][0][0],'lon':route['waypoints'][0][1],
             'temp_c':10 if truck['truck_id']=='TRK-001' else -20,'temp_min_c':profile['temp_min_c'],'temp_max_c':profile['temp_max_c'],
             'humidity_pct':60,'speed_kmh':80,'door_open':False,'scheduled_eta':iso(now+timedelta(hours=1))}
        process_batch([msg],repo,svc,now)
for i in range(25):
    repo.save_alert(Alert('TRK-001','DELAYED','Recovered',iso(now-timedelta(minutes=30+i)),iso(now),status='RESOLVED'))
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):self.dispatch()
    def do_POST(self):self.dispatch()
    def do_DELETE(self):self.dispatch()
    def dispatch(self):
        path=urlsplit(self.path);parts=path.path.strip('/').split('/');routes={}
        handler=None
        if len(parts)==2:
            handler={'trucks':app.get_trucks,'routes':app.get_routes,'alerts':app.get_alerts,'health':app.get_health,'session':app.get_session}.get(parts[1])
        elif len(parts)==4 and parts[1]=='trucks':
            handler=app.get_history;routes={'truck_id':parts[2]}
        elif len(parts)==4 and parts[1]=='alerts':
            handler=app.ack_alert;routes={'alert_id':parts[2]}
        elif path.path=='/api/sim/trucks':handler=app.get_faults
        elif len(parts)==5 and parts[1]=='sim':
            handler=app.clear_fault if self.command=='DELETE' else app.set_fault;routes={'truck_id':parts[3]}
        if not handler:self.send_error(404);return
        req=func.HttpRequest(self.command,'http://local'+self.path,headers=dict(self.headers),params=dict(parse_qsl(path.query)),route_params=routes,body=self.rfile.read(int(self.headers.get('Content-Length',0))))
        try:response=handler(req)
        except Exception:
            import traceback;traceback.print_exc();self.send_error(500);return
        self.send_response(response.status_code);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(response.get_body())
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
print(server.server_port,flush=True)
server.serve_forever()
