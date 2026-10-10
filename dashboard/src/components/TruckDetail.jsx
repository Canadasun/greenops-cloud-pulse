import { useContext, useState } from 'react';
import { api, usePolling } from '../api';
import { CARGO, timestamp, temp } from '../status';
import { ClockContext, StatusBadge, Freshness } from './UI';
import TempChart from './TempChart';
import QueryState from './QueryState';
import AlertHistory from './AlertHistory';
export default function TruckDetail({ truck, incident, open, acknowledge, canOperate }) {
  const [hours, setHours] = useState(1), now = useContext(ClockContext);
  const hist = usePolling(opts => api.history(truck.truck_id, hours, opts), hours >= 6 ? 30000 : 5000, [truck?.truck_id, hours], !!truck);
  if (!truck) return <p className="empty">Loading truck details…</p>;
  const excursion = truck.temp_c == null ? null : truck.temp_c > truck.temp_max_c ? `${(truck.temp_c - truck.temp_max_c).toFixed(1)} °C above safe range` : truck.temp_c < truck.temp_min_c ? `${(truck.temp_min_c - truck.temp_c).toFixed(1)} °C below safe range` : 'Within safe range';
  return <div className="detail"><div className="detail-head"><div><h2>{truck.truck_id}</h2><p className="muted">{CARGO[truck.cargo_type] || truck.cargo_type} · {truck.origin} → {truck.destination}</p></div><StatusBadge status={truck.status} /></div>
    <div className="reading-hero"><div><span className="eyebrow">Last temperature</span><strong>{temp(truck.temp_c)}</strong><span>Safe {truck.temp_min_c} to {truck.temp_max_c} °C</span><span className={excursion && excursion !== 'Within safe range' ? 'bad' : 'muted'}>{excursion || 'Waiting for first telemetry'}</span></div><div><span className="eyebrow">Last reading</span><Freshness lastSeen={truck.last_seen} parked={truck.status === 'parked'} /><span className="small muted">{timestamp(truck.last_seen)}</span></div><div><span className="eyebrow">Door</span><strong className="door-reading">{truck.door_open == null ? '—' : truck.door_open ? 'Open' : 'Closed'}</strong><span>{truck.humidity_pct == null ? 'Humidity unavailable' : `Humidity ${truck.humidity_pct.toFixed(0)} %`}</span></div></div>
    {incident && <p className="incident-context">Inspecting {incident.details} · Incident started {timestamp(incident.started_at)}. The chart shows the selected recent window; older incidents may fall outside it.</p>}
    <div className="section-heading"><h3>Temperature history</h3><label>Window<select aria-label="Window" value={hours} onChange={e => setHours(Number(e.target.value))}><option value="1">1 hour</option><option value="6">6 hours</option><option value="24">24 hours</option></select></label></div><QueryState query={hist} label="Temperature history" />
    {hist.data && <TempChart key={`${truck.truck_id}-${hours}`} points={hist.data.points} min={hist.data.temp_min_c} max={hist.data.temp_max_c} hours={hours} start={hist.data.window_start} end={hist.data.window_end} total={hist.data.total_points} truckId={truck.truck_id} />}
    <div className="detail-support"><section><h3>Journey & readings</h3><dl className="readings"><dt>Speed</dt><dd>{truck.speed_kmh != null ? `${truck.speed_kmh.toFixed(0)} km/h` : '—'}</dd><dt>Scheduled arrival</dt><dd>{timestamp(truck.scheduled_eta)}{truck.scheduled_eta && now > Date.parse(truck.scheduled_eta) && <span className="small muted">Scheduled time passed; arrival is not confirmed.</span>}</dd></dl>{truck.status === 'parked' && <p className="small muted">Parked: the last demo run ended on schedule, so no offline or delay alerts are raised until the truck sends again.</p>}{truck.simulation_time_scale > 1 && <p className="small muted">Accelerated demo: map movement runs at {truck.simulation_time_scale.toFixed(1)}× physical speed.</p>}</section><section><h3>Open incidents for this truck</h3>{open && <QueryState query={open} label="Open incidents" />}<AlertHistory alerts={open?.data?.items.filter(a => a.truck_id === truck.truck_id)} onAcknowledge={acknowledge} canOperate={canOperate} /></section></div>
  </div>;
}
