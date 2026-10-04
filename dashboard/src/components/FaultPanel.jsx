// Demo operator panel: switch fault scenarios on the simulated trucks (FR-02).
import { useState } from 'react';

const OPTIONS = [['none', 'Normal'], ['compressor', 'Compressor failure'], ['door', 'Door left open'], ['delay', 'Traffic delay'], ['offline', 'Go offline']];

export default function FaultPanel({ faults, onChange }) {
  const [error, setError] = useState(null);
  if (!faults) return <p className="muted">Simulator fault API not reachable.</p>;
  const change = async (id, scenario) => {
    setError(null);
    try { await onChange(id, scenario); } catch (e) { setError(e.message); }
  };
  return (
    <div className="faults">
      {error && <p className="error" role="alert">{error}</p>}
      {Object.entries(faults).map(([id, scenario]) => (
        <label key={id}>{id}
          <select value={scenario} onChange={(e) => change(id, e.target.value)} aria-label={`Fault scenario for ${id}`}>
            {OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
      ))}
    </div>
  );
}
