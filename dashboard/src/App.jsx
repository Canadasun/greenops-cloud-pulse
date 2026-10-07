import { useEffect, useState } from 'react';
import { api, setOperatorKey, usePolling } from './api';
import { STATUS, countByStatus, temp } from './status';
import FleetMap from './components/FleetMap';
import TruckDetail from './components/TruckDetail';
import AlertHistory from './components/AlertHistory';
import HealthPanel from './components/HealthPanel';
import FaultPanel from './components/FaultPanel';
import QueryState from './components/QueryState';

function useLocation() {
  const [params, setParams] = useState(() => new URLSearchParams(location.search));
  useEffect(() => { const pop = () => setParams(new URLSearchParams(location.search)); addEventListener('popstate', pop); return () => removeEventListener('popstate', pop); }, []);
  const change = values => {
    const next = new URLSearchParams(location.search);
    Object.entries(values).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key));
    history.pushState(null, '', `${location.pathname}?${next}`); setParams(next);
  };
  return [params, change];
}
function OperatorAccess({ identity, onIdentity }) {
  const [key, setKey] = useState(''), [error, setError] = useState(null), [busy, setBusy] = useState(false);
  const connect = async e => {
    e.preventDefault(); setBusy(true); setError(null); setOperatorKey(key);
    try { const result = await api.session(); if (!result.can_operate) throw new Error('Operator key was not recognized.'); setKey(''); onIdentity(result.user); }
    catch (e) { setOperatorKey(''); setError(e.message); } finally { setBusy(false); }
  };
  if (identity) return <div className="operator"><span>Operator: {identity}</span><button onClick={() => { setOperatorKey(''); onIdentity(null); }}>Disconnect</button></div>;
  return <details className="operator-access"><summary>Read-only · Connect operator</summary><form onSubmit={connect}><label>Operator access key<input type="password" value={key} onChange={e => setKey(e.target.value)} autoComplete="off" required /></label><button disabled={busy}>{busy ? 'Connecting…' : 'Connect'}</button><p className="small muted">Keys are supplied by your administrator and kept only in this tab's memory.</p>{error && <p role="alert" className="error">{error}</p>}</form></details>;
}
export default function App() {
  const [params, change] = useLocation();
  const rawView = params.get('view') || 'overview', view = ['overview', 'fleet', 'map', 'alerts', 'system'].includes(rawView) ? rawView : 'overview';
  const selected = params.get('truck') || 'TRK-001', filter = params.get('status') || '', search = params.get('q') || '';
  const [identity, setIdentity] = useState(null), [cursor, setCursor] = useState(null), [previous, setPrevious] = useState([]);
  const trucks = usePolling(api.trucks, 5000), open = usePolling(opts => api.alerts({ status: 'OPEN' }, opts), 5000), routes = usePolling(api.routes, 600000);
  const health = usePolling(api.health, 30000, [], view === 'system'), faults = usePolling(api.faults, 5000, [], view === 'system');
  const historyQuery = usePolling(opts => api.alerts({ status: 'RESOLVED', truck_id: params.get('historyTruck'), cursor }, opts), 15000, [cursor, params.get('historyTruck')], view === 'alerts');
  const list = trucks.data || [], counts = countByStatus(list), truck = list.find(t => t.truck_id === selected);
  const visible = list.filter(t => (!filter || t.status === filter) && `${t.truck_id} ${t.origin} ${t.destination} ${t.cargo_type}`.toLowerCase().includes(search.toLowerCase()));
  const visibleIds = new Set(visible.map(t => t.truck_id));
  const incidents = open.data?.items.filter(a => (!filter && !search) || visibleIds.has(a.truck_id));
  const select = id => change({ truck: id });
  const acknowledge = async id => { const updated = await api.acknowledge(id); open.update(data => data && ({ ...data, items: data.items.map(a => a.id === id ? updated : a) })); open.refresh(); trucks.refresh(); };
  const setFault = async (id, scenario) => { await api.setFault(id, scenario); faults.update(data => ({ ...data, [id]: scenario })); faults.refresh(); };
  return <div className={`app view-${view}`}>
    <a className="skip-link" href="#main">Skip to fleet dashboard</a>
    <header><a className="brand" href="?view=overview"><span className="logo">GO</span><span>GreenOps <span className="brand-light">Cloud Pulse</span><small>Smart Fleet &amp; Cold-Chain Telemetry Tracker</small></span></a><OperatorAccess identity={identity} onIdentity={setIdentity} /></header>
    <nav className="main-nav" aria-label="Dashboard views">{[['overview', 'Overview'], ['fleet', 'Fleet'], ['map', 'Map'], ['alerts', 'Alerts'], ['system', 'System & demo']].map(([key, label]) => <button key={key} aria-current={view === key ? 'page' : undefined} onClick={() => change({ view: key })}>{label}{key === 'alerts' && open.data?.items.length ? ` (${open.data.items.length})` : ''}</button>)}</nav>
    <main id="main"><div className="page-heading"><div><p className="eyebrow">Live operations</p><h1>{view === 'system' ? 'System & demo' : view === 'alerts' ? 'Incident centre' : 'Fleet overview'}</h1></div><span className={`connection ${trucks.error ? 'error' : ''}`}>{trucks.error ? 'Fleet connection interrupted' : trucks.data ? 'Fleet connected' : 'Connecting to fleet…'}</span></div>
      {view !== 'system' && <><div className="status-summary" aria-label="Filter fleet by status"><button className={!filter ? 'selected' : ''} aria-pressed={!filter} onClick={() => change({ status: null })}><strong>{list.length}</strong>All trucks</button>{Object.entries(STATUS).map(([key, s]) => <button key={key} className={filter === key ? 'selected' : ''} aria-pressed={filter === key} onClick={() => change({ status: filter === key ? null : key })}><strong style={{ background: s.color, color: s.text }}>{counts[key]}</strong>{s.label}</button>)}</div><QueryState query={trucks} label="Fleet" /><label className="search">Find a truck<input type="search" value={search} placeholder="Truck ID, route or cargo" onChange={e => change({ q: e.target.value })} /></label></>}
      {['overview', 'alerts'].includes(view) && <section className="card attention" aria-label="Open incidents"><div className="section-heading"><div><p className="eyebrow">Attention needed</p><h2>Open incidents <span className="count">{incidents?.length ?? '—'}</span></h2></div>{!identity && <span className="muted small">Connect an operator key to acknowledge</span>}</div><QueryState query={open} label="Open incidents" /><AlertHistory alerts={incidents} onAcknowledge={acknowledge} canOperate={!!identity} onSelect={id => change({ truck: id, view: 'fleet' })} /></section>}
      {['overview', 'fleet', 'map'].includes(view) && <div className="fleet-layout"><section className="card fleet-list" aria-label="Fleet list"><h2>Trucks <span className="count">{visible.length}</span></h2>{!visible.length && trucks.data && <p className="empty">No trucks match these filters.</p>}<div className="truck-list">{visible.map(t => <button key={t.truck_id} aria-pressed={selected === t.truck_id} className={`truck-row ${selected === t.truck_id ? 'selected' : ''}`} onClick={() => select(t.truck_id)}><span><strong>{t.truck_id}</strong><small>{t.origin} → {t.destination}</small></span><span><span className="pill" style={{ background: STATUS[t.status].color, color: STATUS[t.status].text }}>{STATUS[t.status].label}</span><small>{temp(t.temp_c)}</small></span></button>)}</div></section>
        <section className="card map-card" aria-label="Live fleet map"><h2>Fleet location</h2><QueryState query={routes} label="Routes" /><FleetMap trucks={visible} routes={routes.data} selected={selected} onSelect={select} /><p className="muted small">Select a marker or use the fleet list. Locations show the last received reading.</p></section>
        <section className="card detail-card" aria-label="Truck details"><h2>Selected truck</h2><TruckDetail truck={truck} /></section></div>}
      {view === 'alerts' && <section className="card" aria-label="Resolved history"><div className="section-heading"><h2>Resolved history</h2><label>Truck<select value={params.get('historyTruck') || ''} onChange={e => { setCursor(null); setPrevious([]); change({ historyTruck: e.target.value }); }}><option value="">All trucks</option>{list.map(t => <option key={t.truck_id}>{t.truck_id}</option>)}</select></label></div><QueryState query={historyQuery} label="Resolved history" /><AlertHistory alerts={historyQuery.data?.items} onSelect={id => change({ truck: id, view: 'fleet' })} /><div className="pagination"><button disabled={!previous.length || historyQuery.loading} onClick={() => { setCursor(previous.at(-1)); setPrevious(s => s.slice(0, -1)); }}>Previous</button><span>Page {previous.length + 1}</span><button disabled={!historyQuery.data?.next_cursor || historyQuery.loading} onClick={() => { setPrevious(s => [...s, cursor]); setCursor(historyQuery.data.next_cursor); }}>Next</button></div></section>}
      {view === 'system' && <div className="system-layout"><section className="card" aria-label="System health and cost"><h2>System health & capacity</h2><QueryState query={health} label="System health" /><HealthPanel health={health.data} /></section><section className="card" aria-label="Demo fault scenarios"><h2>Demo fault scenarios</h2><QueryState query={faults} label="Fault controls" /><FaultPanel faults={faults.data} onChange={setFault} canOperate={!!identity} /></section></div>}
    </main><footer>GreenOps Cloud Pulse · CST8922 Group 3 · Fleet and incidents refresh every 5 seconds. Times use your device's timezone unless labelled UTC.</footer>
  </div>;
}
