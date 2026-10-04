// Detail view of the selected truck with its one-hour chart (F4, FR-10).
import { api, usePolling } from '../api';
import { CARGO, STATUS, ALERT_TITLES, ago, clock, inRange, temp } from '../status';
import TempChart from './TempChart';

export default function TruckDetail({ truck }) {
  const hist = usePolling(() => (truck ? api.history(truck.truck_id, 1) : Promise.resolve(null)), 5000, [truck?.truck_id]);
  if (!truck) return <p className="muted">Click a truck on the map to see its details.</p>;
  const s = STATUS[truck.status];
  return (
    <div className="detail">
      <div className="detail-head">
        <h3>{truck.truck_id} · {CARGO[truck.cargo_type]}</h3>
        <span className="pill" style={{ background: s.color, color: '#fff' }}>{s.letter} · {s.label}</span>
      </div>
      <p className="muted">{truck.origin} → {truck.destination} ({truck.route_id})</p>
      <dl className="readings">
        <dt>Temperature</dt><dd className={truck.temp_c != null && !inRange(truck) ? 'bad' : ''}>{temp(truck.temp_c)} <span className="muted">(safe {truck.temp_min_c} to {truck.temp_max_c})</span></dd>
        <dt>Humidity</dt><dd>{truck.humidity_pct != null ? `${truck.humidity_pct.toFixed(0)} %` : '—'}</dd>
        <dt>Door</dt><dd className={truck.door_open ? 'bad' : ''}>{truck.door_open == null ? '—' : truck.door_open ? 'OPEN' : 'closed'}</dd>
        <dt>Speed</dt><dd>{truck.speed_kmh != null ? `${truck.speed_kmh.toFixed(0)} km/h` : '—'}</dd>
        <dt>Scheduled arrival</dt><dd>{clock(truck.scheduled_eta)}</dd>
        <dt>Last message</dt><dd>{ago(truck.seconds_ago)}</dd>
        <dt>Open alerts</dt><dd>{truck.open_alerts.length ? truck.open_alerts.map((a) => ALERT_TITLES[a]).join(', ') : 'none'}</dd>
      </dl>
      <h4>Temperature – last hour</h4>
      <TempChart points={hist.data?.points} min={truck.temp_min_c} max={truck.temp_max_c} />
    </div>
  );
}
