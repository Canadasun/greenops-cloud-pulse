import { lazy, Suspense, useMemo, useState } from 'react';
import { api, usePolling } from '../api';
import { STATUS, CARGO, needsAttention, temp } from '../status';
import { StatusBadge, Freshness } from '../components/UI';
import QueryState from '../components/QueryState';
const FleetMap = lazy(() => import('../components/FleetMap'));
function MapWorkspace({ visible, selected, inspect }) {
  const routes = usePolling(api.routes, 600000);
  const [mapTruck, setMapTruck] = useState(selected || '');
  return <section className="card map-card" aria-label="Live fleet map"><h2>Fleet location</h2><QueryState query={routes} label="Routes" /><Suspense fallback={<p role="status">Loading map…</p>}><FleetMap trucks={visible} routes={routes.data} selected={mapTruck} onSelect={setMapTruck} /></Suspense>{visible.some(t => t.truck_id === mapTruck) && <button className="map-inspect" onClick={e => inspect(mapTruck, null, e.currentTarget)}>Inspect {mapTruck}</button>}<p className="small muted">Locations are the last received readings. Use the truck list when GPS is unavailable.</p></section>;
}
export default function FleetPage({ trucks, params, change, inspect }) {
  const list = trucks.data || [], status = params.get('status') || '', search = params.get('q') || '';
  const cargo = params.get('cargo') || '', route = params.get('route') || '', sort = params.get('sort') || 'id';
  const mode = params.get('view') === 'map' ? 'map' : params.get('mode') || 'list';
  const visible = useMemo(() => list.filter(t =>
    (!status || (status === 'attention' ? needsAttention(t) : status === 'unavailable' ? ['waiting', 'offline'].includes(t.status) : t.status === status)) &&
    (!cargo || t.cargo_type === cargo) && (!route || t.route_id === route) &&
    `${t.truck_id} ${t.origin} ${t.destination} ${CARGO[t.cargo_type] || t.cargo_type}`.toLowerCase().includes(search.toLowerCase())
  ).sort((a, b) => (sort === 'condition' ? (['breach', 'offline', 'warning', 'waiting', 'normal', 'parked'].indexOf(a.status) - ['breach', 'offline', 'warning', 'waiting', 'normal', 'parked'].indexOf(b.status)) : 0) || a.truck_id.localeCompare(b.truck_id)), [trucks.data, status, search, cargo, route, sort]);
  const filter = (values, options) => change({ ...values, truck: null, inspect: null }, options);
  return <>
    <div className="section-heading"><p className="muted">Select a truck to inspect its readings and incidents.</p><div className="segmented" role="group" aria-label="Fleet display"><button aria-pressed={mode !== 'map'} onClick={() => change({ view: 'fleet', mode: 'list' })}>List</button><button aria-pressed={mode === 'map'} onClick={() => change({ view: 'fleet', mode: 'map' })}>Map</button></div></div>
    <div className="filter-bar"><label className="search">Find a truck<input type="search" value={search} placeholder="Truck ID, route or cargo" onChange={e => filter({ q: e.target.value }, { replace: true })} /></label><label>Condition<select aria-label="Condition" value={status} onChange={e => filter({ status: e.target.value })}><option value="">All conditions</option><option value="attention">Needs attention</option><option value="unavailable">Offline or waiting</option>{Object.entries(STATUS).map(([key, s]) => <option key={key} value={key}>{s.label}</option>)}</select></label><label>Cargo<select aria-label="Cargo" value={cargo} onChange={e => filter({ cargo: e.target.value })}><option value="">All cargo</option>{Object.entries(CARGO).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label><label>Route<select aria-label="Route" value={route} onChange={e => filter({ route: e.target.value })}><option value="">All routes</option>{[...new Map(list.map(t => [t.route_id, t])).values()].map(t => <option key={t.route_id} value={t.route_id}>{t.origin} → {t.destination}</option>)}</select></label><label>Sort<select aria-label="Sort" value={sort} onChange={e => change({ sort: e.target.value })}><option value="id">Truck ID</option><option value="condition">Condition priority</option></select></label></div>
    {(status || search || cargo || route) && <div className="filter-chips"><span>Filters: {[status && (STATUS[status]?.label || status), search, CARGO[cargo], route].filter(Boolean).join(' · ')}</span><button onClick={() => filter({ status: null, q: null, cargo: null, route: null })}>Clear all filters</button></div>}
    <QueryState query={trucks} label="Fleet" /><p className="small muted" role="status">{trucks.data ? `${visible.length} trucks shown` : 'Loading fleet…'}</p>
    <div className={mode === 'map' ? 'fleet-map-layout' : ''}><section className="card fleet-list" aria-label="Fleet list"><h2>Trucks</h2><div className={`truck-list ${mode !== 'map' ? 'wide-list' : ''}`}>{visible.map(t => <button key={t.truck_id} className="truck-row" onClick={e => inspect(t.truck_id, null, e.currentTarget)}><span><strong>{t.truck_id}</strong><small>{CARGO[t.cargo_type] || t.cargo_type} · {t.origin} → {t.destination}</small><Freshness lastSeen={t.last_seen} parked={t.status === 'parked'} /></span><span><StatusBadge status={t.status} /><small className="truck-temp">{temp(t.temp_c)}</small><small>Safe {t.temp_min_c} to {t.temp_max_c} °C</small></span><span className="inspect-cue" aria-hidden="true">Inspect →</span></button>)}</div>{!visible.length && trucks.data && <p className="empty">No trucks match these filters. Clear filters to see the fleet.</p>}</section>
      {mode === 'map' && <MapWorkspace visible={visible} selected={params.get('truck')} inspect={inspect} />}
    </div>
  </>;
}
