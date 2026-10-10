import { useEffect, useRef, useState } from 'react';
import { api, usePolling } from './api';
import useLocation from './hooks/useLocation';
import OperatorAccess from './components/OperatorAccess';
import { ClockProvider, ErrorBoundary } from './components/UI';
import OverviewPage from './pages/OverviewPage';
import FleetPage from './pages/FleetPage';
import IncidentsPage from './pages/IncidentsPage';
import SystemPage from './pages/SystemPage';
import TruckDetail from './components/TruckDetail';
import QueryState from './components/QueryState';
const titles = { overview: 'Operations overview', fleet: 'Fleet workspace', alerts: 'Incident centre', system: 'System & simulation' };
function Dashboard() {
  const [params, change] = useLocation(), [identity, setIdentity] = useState(null);
  const raw = params.get('view'), view = raw === 'map' ? 'fleet' : titles[raw] ? raw : 'overview';
  const inspecting = params.get('inspect') === '1' || !!params.get('truck');
  const trucks = usePolling(api.trucks, 5000), open = usePolling(opts => api.alerts({ status: 'OPEN' }, opts), 5000);
  const selected = trucks.data?.find(t => t.truck_id === params.get('truck'));
  const heading = useRef(null), returnState = useRef(null), previousView = useRef(view), wasInspecting = useRef(false);
  const inspect = (id, incident, trigger) => {
    if (!inspecting) returnState.current = { url: new URLSearchParams(location.search), trigger: trigger || document.activeElement, scroll: window.scrollY, incident };
    change({ view: 'fleet', truck: id, inspect: '1', incident: incident?.id || null });
  };
  const back = () => {
    if (returnState.current) history.back();
    else change({ truck: null, inspect: null, incident: null }, { replace: true });
  };
  useEffect(() => {
    document.title = `${inspecting ? `${params.get('truck')} · Truck details` : titles[view]} · GreenOps`;
    if (inspecting || previousView.current !== view) heading.current?.focus();
    if (!inspecting && wasInspecting.current && returnState.current) {
      const saved = returnState.current;
      requestAnimationFrame(() => { saved.trigger?.focus({ preventScroll: true }); window.scrollTo(0, saved.scroll); });
      returnState.current = null;
    }
    previousView.current = view; wasInspecting.current = inspecting;
  }, [view, inspecting, params.get('truck')]);
  const navigate = key => { returnState.current = null; change({ view: key, truck: null, inspect: null, incident: null }); };
  const acknowledge = async id => {
    const updated = await api.acknowledge(id);
    open.update(data => data && ({ ...data, items: data.items.map(a => a.id === id ? updated : a) }));
    open.refresh(); trucks.refresh();
  };
  const shared = { trucks, open, params, change, inspect, acknowledge, identity };
  // Keep the originating workspace mounted while inspecting: its controls, scroll and focus survive return.
  const backgroundView = inspecting && returnState.current ? (returnState.current.url.get('view') || 'overview') : view;
  const backgroundParams = inspecting && returnState.current ? returnState.current.url : params;
  const pageProps = { ...shared, params: backgroundParams };
  const contextIncident = open.data?.items.find(a => a.id === params.get('incident')) || returnState.current?.incident;
  return <div className={`app view-${view}`}><a className="skip-link" href="#main">Skip to dashboard</a>
    <header><a className="brand" href="?view=overview" onClick={e => { if (!e.ctrlKey && !e.metaKey && !e.shiftKey && e.button === 0) { e.preventDefault(); navigate('overview'); } }}><span className="logo" aria-hidden="true">GO</span><span>GreenOps <span className="brand-light">Cloud Pulse</span><small>Fleet operations · Cold-chain monitoring</small></span></a><OperatorAccess identity={identity} onIdentity={setIdentity} /></header>
    <nav className="main-nav" aria-label="Dashboard views">{Object.entries(titles).map(([key]) => <a key={key} href={`?view=${key}`} aria-current={view === key ? 'page' : undefined} onClick={e => { if (!e.ctrlKey && !e.metaKey && !e.shiftKey && e.button === 0) { e.preventDefault(); navigate(key); } }}>{({ overview: 'Overview', fleet: 'Fleet', alerts: 'Incidents', system: 'System' })[key]}{key === 'alerts' && open.data && <span className="nav-count">{open.data.items.filter(a => a.status === 'ACTIVE').length}<span className="sr-only"> needing action</span></span>}</a>)}</nav>
    <main id="main" tabIndex="-1"><div className="page-heading"><div><p className="eyebrow">Live operations</p><h1 ref={heading} tabIndex="-1">{inspecting ? `${params.get('truck')} · Truck details` : titles[view]}</h1></div><span className={`connection ${trucks.error ? 'error' : ''}`}>{trucks.error ? 'Fleet API interrupted' : trucks.data ? 'Fleet API connected' : 'Connecting to fleet API…'}</span></div>
      <div hidden={inspecting}>{backgroundView === 'overview' ? <OverviewPage {...pageProps} /> : ['fleet', 'map'].includes(backgroundView) ? <FleetPage {...pageProps} /> : backgroundView === 'alerts' ? <IncidentsPage {...pageProps} /> : <SystemPage identity={identity} />}</div>
      {inspecting && <section className="card detail-card" aria-label="Truck details"><button className="back-button" onClick={back}>← Back to {returnState.current?.url.get('view') === 'alerts' ? 'incidents' : returnState.current?.url.get('view') === 'overview' || returnState.current && !returnState.current.url.get('view') ? 'overview' : 'fleet'}</button><QueryState query={trucks} label="Fleet" />{trucks.data && !selected ? <p role="status">This truck is not in the fleet. Return to the fleet to select an available truck.</p> : <TruckDetail truck={selected} incident={contextIncident} open={open} acknowledge={acknowledge} canOperate={!!identity} />}</section>}
    </main><footer>GreenOps Cloud Pulse · Fleet and incidents refresh every 5 seconds while this tab is visible. Times use your device’s timezone unless labelled UTC.</footer>
  </div>;
}
export default function App() { return <ErrorBoundary><ClockProvider><Dashboard /></ClockProvider></ErrorBoundary>; }
