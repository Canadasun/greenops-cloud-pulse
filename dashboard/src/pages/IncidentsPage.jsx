import { api, usePolling } from '../api';
import AlertHistory from '../components/AlertHistory';
import QueryState from '../components/QueryState';
import { prioritize } from '../components/UI';
export default function IncidentsPage({ open, trucks, params, change, inspect, acknowledge, identity }) {
  const tab = ['active', 'monitoring', 'resolved'].includes(params.get('tab')) ? params.get('tab') : 'active';
  const truckId = params.get('historyTruck') || '', cursor = params.get('cursor') || '';
  const previous = (params.get('pages') || '').split(',').filter(Boolean);
  const resolved = usePolling(opts => api.alerts({ status: 'RESOLVED', truck_id: truckId, cursor }, opts), 15000, [truckId, cursor], tab === 'resolved');
  const query = tab === 'resolved' ? resolved : open;
  const items = tab === 'resolved' ? resolved.data?.items : open.data ? prioritize(open.data.items.filter(a => a.status === (tab === 'active' ? 'ACTIVE' : 'ACKNOWLEDGED') && (!truckId || a.truck_id === truckId))) : undefined;
  return <section className="card" aria-label="Incident queue">
    <div className="section-heading"><div><h2>Incident queue</h2><p className="muted">Acknowledgement records that an issue was seen. Monitoring continues until recovery.</p></div><label>Incident truck<select aria-label="Incident truck" value={truckId} onChange={e => change({ historyTruck: e.target.value, cursor: null, pages: null })}><option value="">All trucks</option>{(trucks.data || []).map(t => <option key={t.truck_id}>{t.truck_id}</option>)}</select></label></div>
    <div className="segmented incident-tabs" aria-label="Incident state">{[['active', 'Needs action'], ['monitoring', 'Monitoring'], ['resolved', 'Resolved']].map(([key, label]) => <button key={key} aria-pressed={key === tab} onClick={() => change({ tab: key, cursor: null, pages: null })}>{label}{key !== 'resolved' && open.data ? ` (${open.data.items.filter(a => a.status === (key === 'active' ? 'ACTIVE' : 'ACKNOWLEDGED')).length})` : ''}</button>)}</div>
    {tab !== 'resolved' && <p className="small muted">Priority: cargo breaches, offline, door, then delay. Oldest first within each group.</p>}
    {!identity && tab === 'active' && <p className="small muted">Connect an operator key to acknowledge incidents.</p>}
    <QueryState query={query} label={tab === 'resolved' ? 'Resolved history' : 'Open incidents'} />
    <AlertHistory alerts={items} onAcknowledge={acknowledge} canOperate={!!identity} onSelect={inspect} />
    {tab === 'resolved' && <div className="pagination"><button disabled={!previous.length || resolved.loading} onClick={() => change({ cursor: previous.at(-1) === '_' ? null : previous.at(-1), pages: previous.slice(0, -1).join(',') })}>Previous</button><span role="status">Page {previous.length + 1}</span><button disabled={!resolved.data?.next_cursor || resolved.loading} onClick={() => change({ cursor: resolved.data.next_cursor, pages: [...previous, cursor || '_'].join(',') })}>Next</button></div>}
  </section>;
}
