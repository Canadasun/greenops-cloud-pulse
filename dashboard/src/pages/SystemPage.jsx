import { api, usePolling } from '../api';
import QueryState from '../components/QueryState';
import HealthPanel from '../components/HealthPanel';
import FaultPanel from '../components/FaultPanel';
export default function SystemPage({ identity }) {
  const health = usePolling(api.health, 30000), faults = usePolling(api.faults, 5000);
  const setFault = async (id, scenario) => { await api.setFault(id, scenario); faults.update(data => ({ ...data, [id]: scenario })); faults.refresh(); };
  return <div className="system-layout"><section className="card" aria-label="Usage and capacity"><p className="eyebrow">Platform</p><h2>Usage & capacity</h2><p className="muted">Message usage and alert delivery aggregates. These are not individual service health checks.</p><QueryState query={health} label="System usage" /><HealthPanel health={health.data} /></section><section className="card" aria-label="Demo fault scenarios"><p className="eyebrow">Simulation only</p><h2>Demo fault scenarios</h2><QueryState query={faults} label="Fault controls" /><FaultPanel faults={faults.data} onChange={setFault} canOperate={!!identity} /></section></div>;
}
