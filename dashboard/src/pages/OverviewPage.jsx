import { useContext } from 'react';
import { ClockContext, readingAge, prioritize, StatusBadge, Freshness } from '../components/UI';
import AlertHistory from '../components/AlertHistory';
import QueryState from '../components/QueryState';
import { temp } from '../status';
export default function OverviewPage({ trucks, open, change, inspect, acknowledge, identity }) {
  const now = useContext(ClockContext), list = trucks.data || [];
  const active = open.data ? prioritize(open.data.items.filter(a => a.status === 'ACTIVE')) : undefined;
  const reporting = list.filter(t => { const age = readingAge(t.last_seen, now); return age != null && age <= 90; }).length;
  const cards = [
    ['Trucks needing attention', trucks.data ? list.filter(t => t.status !== 'normal').length : '—', 'Breach, warning, offline or waiting', () => change({ view: 'fleet', status: 'attention' })],
    ['Needs acknowledgement', active?.length ?? '—', 'Open incidents needing action', () => change({ view: 'alerts', tab: 'active' })],
    ['Offline or waiting', trucks.data ? list.filter(t => ['offline', 'waiting'].includes(t.status)).length : '—', 'No current operating picture', () => change({ view: 'fleet', status: 'unavailable' })],
    ['Reporting trucks', trucks.data ? `${reporting} / ${list.length}` : '—', 'Reading received within 90 seconds', () => change({ view: 'fleet', status: null })],
  ];
  return <>
    <div className="metrics">{cards.map(([label, value, hint, action]) => <button key={label} onClick={action}><span>{label}</span><strong>{value}</strong><small>{hint}</small></button>)}</div>
    <QueryState query={trucks} label="Fleet" />
    <div className="overview-grid">
      <section className="card" aria-label="Priority incidents"><div className="section-heading"><div><p className="eyebrow">Act next</p><h2>Needs attention <span className="count">{active?.length ?? '—'}</span></h2></div><button onClick={() => change({ view: 'alerts', tab: 'active' })}>View all {open.data?.items.length ?? ''} incidents</button></div><QueryState query={open} label="Open incidents" />
        {!identity && <p className="small muted">Connect an operator key to acknowledge. Inspection is available to everyone.</p>}
        <AlertHistory compact alerts={active?.slice(0, 3)} onAcknowledge={acknowledge} canOperate={!!identity} onSelect={inspect} />
        <p className="small muted">Cargo breaches first, then offline, door and delay issues; oldest first within each group.</p>
      </section>
      <section className="card" aria-label="Fleet snapshot"><div className="section-heading"><h2>Fleet snapshot</h2><button onClick={() => change({ view: 'fleet' })}>Open fleet</button></div><div className="truck-list">{list.map(t => <button className="truck-row" key={t.truck_id} onClick={e => inspect(t.truck_id, null, e.currentTarget)}><span><strong>{t.truck_id}</strong><small>{t.origin} → {t.destination}</small><Freshness lastSeen={t.last_seen} /></span><span><StatusBadge status={t.status} /><small>{temp(t.temp_c)}</small></span></button>)}</div>{trucks.data && !list.length && <p>No trucks registered.</p>}</section>
    </div>
  </>;
}
