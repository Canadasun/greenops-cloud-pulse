// GreenOps Cloud Pulse dashboard (Role 5 – Idowu Ayeni). Layout follows the Part 2 wireframe (Figure 8).
import { useState } from 'react';
import { api, usePolling } from './api';
import { STATUS, countByStatus } from './status';
import FleetMap from './components/FleetMap';
import TruckDetail from './components/TruckDetail';
import AlertHistory from './components/AlertHistory';
import HealthPanel from './components/HealthPanel';
import FaultPanel from './components/FaultPanel';

const REFRESH_MS = 5000; // NFR-02
const USER = 'Dispatcher (demo)';

export default function App() {
  const trucks = usePolling(api.trucks, REFRESH_MS);
  const alerts = usePolling(api.alerts, REFRESH_MS);
  const health = usePolling(api.health, 15000);
  const routes = usePolling(api.routes, 600000);
  const faults = usePolling(api.faults, REFRESH_MS);
  const [selected, setSelected] = useState('TRK-001');
  const [, force] = useState(0);
  const list = trucks.data || [];
  const counts = countByStatus(list);
  const truck = list.find((t) => t.truck_id === selected);
  const updated = trucks.updatedAt ? Math.round((Date.now() - trucks.updatedAt) / 1000) : null;

  return (
    <div className="app">
      <header>
        <div className="brand"><span className="logo">GO</span> GreenOps Cloud Pulse <span className="muted">Smart Fleet &amp; Cold-Chain Tracker</span></div>
        <div className="chips" aria-label="Fleet status summary">
          <span className="chip">{list.length} trucks</span>
          {['normal', 'warning', 'breach', 'offline'].map((k) => (
            <span key={k} className="chip"><i style={{ background: STATUS[k].color }}>{STATUS[k].letter}</i>{counts[k]} {STATUS[k].label.toLowerCase()}</span>
          ))}
        </div>
        <div className="updated">{trucks.error ? <span className="error">API unreachable – retrying</span> : `Updated ${updated ?? '…'} s ago`} · Signed in: {USER}</div>
      </header>
      <main>
        <section className="card map-card" aria-label="Live fleet map">
          <h2>Live fleet map <span className="tag">F1 · FR-10 · refresh 5 s</span></h2>
          <FleetMap trucks={list} routes={routes.data} selected={selected} onSelect={setSelected} />
          <div className="legend">{Object.entries(STATUS).slice(0, 4).map(([k, s]) => (
            <span key={k}><i style={{ background: s.color }}>{s.letter}</i>{s.label}</span>))} · click a truck for details</div>
        </section>
        <section className="card" aria-label="Truck details"><h2>Truck details <span className="tag">F4</span></h2><TruckDetail truck={truck} /></section>
        <section className="card wide" aria-label="Alert history">
          <h2>Alert history <span className="tag">F9 · FR-11</span></h2>
          <AlertHistory alerts={alerts.data} user={USER} onAcknowledge={async (id, user) => { await api.acknowledge(id, user); force((n) => n + 1); }} />
        </section>
        <section className="card" aria-label="System health and cost"><h2>System health &amp; cost <span className="tag">F11</span></h2><HealthPanel health={health.data} /></section>
        <section className="card" aria-label="Demo fault scenarios"><h2>Demo: fault scenarios <span className="tag">FR-02</span></h2>
          <FaultPanel faults={faults.data} onChange={api.setFault} /></section>
      </main>
      <footer className="muted">CST8922 Group 3 · local build · data refreshes every 5 seconds</footer>
    </div>
  );
}
