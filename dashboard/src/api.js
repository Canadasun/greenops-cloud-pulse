// Small client for the read-only Fleet API (Azure Functions) and the simulator's fault API.
import { useEffect, useRef, useState } from 'react';

async function request(path, options = {}) {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
  return body;
}

export const api = {
  trucks: () => request('/api/trucks'),
  routes: () => request('/api/routes'),
  history: (id, hours = 1) => request(`/api/trucks/${id}/history?hours=${hours}`),
  alerts: () => request('/api/alerts?limit=50'),
  health: () => request('/api/health'),
  acknowledge: (id, user) => request(`/api/alerts/${id}/ack`, { method: 'POST', body: JSON.stringify({ user }) }),
  faults: () => request('/sim/trucks'),
  setFault: (id, scenario) =>
    scenario === 'none'
      ? request(`/sim/trucks/${id}/fault`, { method: 'DELETE' })
      : request(`/sim/trucks/${id}/fault`, { method: 'POST', body: JSON.stringify({ scenario }) }),
};

// Calls fn every `ms` milliseconds (NFR-02: refresh at least every 5 s) and keeps the last good result.
export function usePolling(fn, ms, deps = []) {
  const [state, setState] = useState({ data: null, error: null, updatedAt: null });
  const saved = useRef(fn);
  saved.current = fn;
  useEffect(() => {
    let alive = true;
    const run = async () => {
      try {
        const data = await saved.current();
        if (alive) setState({ data, error: null, updatedAt: Date.now() });
      } catch (e) {
        if (alive) setState((s) => ({ ...s, error: e.message }));
      }
    };
    run();
    const t = setInterval(run, ms);
    return () => { alive = false; clearInterval(t); };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  return state;
}
