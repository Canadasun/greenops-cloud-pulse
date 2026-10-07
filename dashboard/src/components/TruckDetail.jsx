import { useState } from 'react';
import { api, usePolling } from '../api';
import { CARGO, STATUS, ALERT_TITLES, ago, timestamp, inRange, temp } from '../status';
import TempChart from './TempChart';
import QueryState from './QueryState';
export default function TruckDetail({ truck }) {
  const [hours, setHours] = useState(1);
  const hist = usePolling(opts => api.history(truck.truck_id, hours, opts), 5000, [truck?.truck_id, hours], !!truck);
  if (!truck) return <p className="empty">Select a truck from the fleet to see its details.</p>;
  const s = STATUS[truck.status];
  const late = truck.scheduled_eta && Date.now() > new Date(truck.scheduled_eta).getTime();
  return <div className="detail">
    <div className="detail-head"><h3>{truck.truck_id}</h3><span className="pill" style={{ background: s.color, color: s.text }}>{s.letter} · {s.label}</span></div>
    <p className="muted">{CARGO[truck.cargo_type]} · {truck.origin} → {truck.destination}</p>
    {truck.status === 'waiting' && <p className="empty">Waiting for first telemetry.</p>}
    {truck.simulation_time_scale > 1 && <p className="small muted">Accelerated demo: map movement runs at {truck.simulation_time_scale.toFixed(1)}× physical speed.</p>}
    <dl className="readings">
      <dt>Temperature</dt><dd className={truck.temp_c != null && !inRange(truck) ? 'bad' : ''}>{temp(truck.temp_c)} <span className="muted small">safe {truck.temp_min_c} to {truck.temp_max_c} °C</span></dd>
      <dt>Humidity</dt><dd>{truck.humidity_pct != null ? `${truck.humidity_pct.toFixed(0)} %` : '—'}</dd>
      <dt>Door</dt><dd className={truck.door_open ? 'bad' : ''}>{truck.door_open == null ? '—' : truck.door_open ? 'Open' : 'Closed'}</dd>
      <dt>Speed</dt><dd>{truck.speed_kmh != null ? `${truck.speed_kmh.toFixed(0)} km/h` : '—'}</dd>
      <dt>Scheduled arrival</dt><dd>{timestamp(truck.scheduled_eta)}{late && <span className="small muted"> · Scheduled time passed</span>}</dd>
      <dt>Last message</dt><dd><time dateTime={truck.last_seen} title={timestamp(truck.last_seen)}>{ago(truck.seconds_ago == null ? null : Math.max(0, truck.seconds_ago))}</time>{!truck.last_seen && ' · awaiting telemetry'}</dd>
      <dt>Open alerts</dt><dd>{truck.open_alerts.length ? truck.open_alerts.map(a => ALERT_TITLES[a]).join(', ') : 'None reported'}</dd>
    </dl>
    <div className="section-heading"><h4>Temperature history</h4><label>Window <select value={hours} onChange={e => setHours(Number(e.target.value))}><option value="1">1 hour</option><option value="6">6 hours</option><option value="24">24 hours</option></select></label></div>
    <QueryState query={hist} label="Temperature history" />
    {hist.data && <TempChart key={`${truck.truck_id}-${hours}`} points={hist.data.points} min={hist.data.temp_min_c} max={hist.data.temp_max_c} hours={hours} />}
  </div>;
}
