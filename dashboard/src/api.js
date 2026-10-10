import { parseTrucks, parseHistory, parseAlerts, parseRoutes } from './contracts';
import { useCallback, useEffect, useRef, useState } from 'react';

export function endpoints(apiBase = '') {
  const base = apiBase.replace(/\/$/, '');
  return { api: `${base}/api`, sim: `${base}/api/sim` };
}
const { api: API, sim: SIM } = endpoints(import.meta.env.VITE_API_BASE || '');
let operatorKey = '';
export function setOperatorKey(key) { operatorKey = key; }

export async function request(path, options = {}) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  options.signal?.addEventListener('abort', abort, { once: true });
  if (options.signal?.aborted) controller.abort();
  const timer = setTimeout(abort, 12000);
  try {
    const res = await fetch(path, { ...options, signal: controller.signal, headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(operatorKey ? { Authorization: `Bearer ${operatorKey}` } : {}), ...options.headers,
    } });
    const body = await res.json().catch(() => { throw new Error('The server returned an unreadable response.'); });
    if (!res.ok) throw new Error(body.error || `Request failed (${res.status})`);
    return body;
  } catch (error) {
    if (error.name === 'AbortError' && !options.signal?.aborted) throw new Error('Request timed out. Please retry.');
    throw error;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort', abort);
  }
}
const query = (values) => new URLSearchParams(Object.entries(values).filter(([, v]) => v != null && v !== '')).toString();
export const api = {
  trucks: (opts) => request(`${API}/trucks`, opts).then(parseTrucks),
  routes: (opts) => request(`${API}/routes`, opts).then(parseRoutes),
  history: (id, hours = 1, opts) => request(`${API}/trucks/${encodeURIComponent(id)}/history?hours=${hours}&max_points=1000`, opts).then(parseHistory),
  rawHistory: (id, hours, end, offset, opts) => request(`${API}/trucks/${encodeURIComponent(id)}/history?${query({ hours, end, offset, limit: 50 })}`, opts).then(parseHistory),
  alerts: (filters = {}, opts) => request(`${API}/alerts?${query({ limit: 20, ...filters })}`, opts).then(parseAlerts),
  health: (opts) => request(`${API}/health`, opts),
  session: (opts) => request(`${API}/session`, opts),
  acknowledge: (id) => request(`${API}/alerts/${encodeURIComponent(id)}/ack`, { method: 'POST', body: '{}' }),
  faults: (opts) => request(`${SIM}/trucks`, opts),
  setFault: (id, scenario) => request(`${SIM}/trucks/${encodeURIComponent(id)}/fault`, {
    method: scenario === 'none' ? 'DELETE' : 'POST',
    ...(scenario !== 'none' ? { body: JSON.stringify({ scenario }) } : {}),
  }),
};

// A single in-flight request per query. Identity changes hide old data during render,
// before effects run. Cleanup aborts obsolete requests; a late result cannot overwrite.
export function usePolling(fn, ms, deps = [], enabled = true) {
  const key = JSON.stringify(deps);
  const [state, setState] = useState({ key, data: null, error: null, updatedAt: null, loading: enabled });
  const [revision, setRevision] = useState(0);
  const saved = useRef(fn);
  saved.current = fn;
  const refresh = useCallback(() => setRevision(n => n + 1), []);
  useEffect(() => {
    if (!enabled) return;
    let alive = true, timer, failures = 0;
    const controller = new AbortController();
    const run = async () => {
      if (document.hidden) { timer = setTimeout(run, ms); return; }
      const started = Date.now();
      setState(s => ({ ...(s.key === key ? s : { data: null, error: null, updatedAt: null }), key, loading: true }));
      try {
        const data = await saved.current({ signal: controller.signal });
        failures = 0;
        if (alive) setState({ key, data, error: null, updatedAt: Date.now(), loading: false });
      } catch (e) {
        failures++;
        if (alive) setState(s => ({ ...s, key, error: e.message, loading: false }));
      } finally {
        if (alive) timer = setTimeout(run, Math.max(0, Math.min(60000, ms * 2 ** Math.min(failures, 4)) - (Date.now() - started))); // NFR-02: every ms, start to start
      }
    };
    const resume = () => { if (!document.hidden) refresh(); };
    document.addEventListener('visibilitychange', resume);
    run();
    return () => { alive = false; controller.abort(); clearTimeout(timer); document.removeEventListener('visibilitychange', resume); };
  }, [key, ms, revision, enabled]);
  const update = useCallback(transform => setState(s => s.key === key ? { ...s, data: transform(s.data) } : s), [key]);
  return { ...(state.key === key ? state : { data: null, error: null, updatedAt: null, loading: enabled }), refresh, update };
}
