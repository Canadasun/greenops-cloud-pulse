import { useEffect, useMemo, useRef, useState } from 'react';
import { timestamp } from '../status';
import { api, usePolling } from '../api';
import QueryState from './QueryState';
const H = 270, M = { l: 48, r: 22, t: 24, b: 38 };
function RawReadings({ truckId, hours, end, points }) {
  const [page, setPage] = useState(0);
  const query = usePolling(opts => api.rawHistory(truckId, hours, end, page * 50, opts), 60000, [truckId, hours, end, page], !!truckId);
  const rows = truckId ? query.data?.points : points.slice(page * 50, (page + 1) * 50);
  const total = truckId ? query.data?.total_points : points.length;
  return <>{truckId && <QueryState query={query} label="Raw readings" />}<div className="table-scroll" tabIndex="0" role="region" aria-label="Temperature readings"><table><caption>Raw readings · {total ?? '—'} samples in this snapshot</caption><thead><tr><th scope="col">Time</th><th scope="col">Temperature</th><th scope="col">Humidity</th></tr></thead><tbody>{rows?.map(p => <tr key={p.timestamp}><td>{timestamp(p.timestamp)}</td><td>{p.temp_c.toFixed(1)} °C</td><td>{p.humidity_pct ?? '—'} %</td></tr>)}</tbody></table></div><div className="pagination"><button disabled={!page || query.loading && !!truckId} onClick={() => setPage(p => p - 1)}>Previous readings</button><span>Page {page + 1}</span><button disabled={!total || (page + 1) * 50 >= total || query.loading && !!truckId} onClick={() => setPage(p => p + 1)}>Next readings</button></div></>;
}
export default function TempChart({ points, min, max, hours = 1, start, end, total, truckId }) {
  const container = useRef(null), [W, setWidth] = useState(900);
  useEffect(() => {
    if (!container.current || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(260, entry.contentRect.width)));
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const [focused, setFocused] = useState(null), [table, setTable] = useState(false), [snapshot, setSnapshot] = useState(null);
  const times = useMemo(() => (points || []).map(p => Date.parse(p.timestamp)), [points]);
  if (!points?.length) return <p className="empty">No readings in this time window.</p>;
  if (points.length < 2) return <p className="empty">Collecting readings for the chart…</p>;
  if (!Number.isFinite(min) || !Number.isFinite(max)) return <p>Safe range unavailable.</p>;
  const lo = Math.min(min, ...points.map(p => p.temp_c)) - 1, hi = Math.max(max, ...points.map(p => p.temp_c)) + 1;
  const t1 = end ? Date.parse(end) : times.at(-1), t0 = start ? Date.parse(start) : t1 - hours * 3600000;
  const x = t => M.l + (t - t0) / Math.max(t1 - t0, 1) * (W - M.l - M.r);
  const y = v => M.t + (hi - v) / (hi - lo) * (H - M.t - M.b);
  const groups = [[]], gaps = [];
  if (times[0] - t0 > 90000) gaps.push([t0, times[0]]);
  points.forEach((p, i) => { if (i && (times[i] - times[i - 1] > 90000 && !p.contiguous)) { groups.push([]); gaps.push([times[i - 1], times[i]]); } groups.at(-1).push(p); });
  if (t1 - times.at(-1) > 90000) gaps.push([times.at(-1), t1]);
  const index = Math.min(focused ?? points.length - 1, points.length - 1), selected = points[index];
  const label = value => new Date(value).toLocaleTimeString('en-CA', { hour: '2-digit', minute: '2-digit' });
  return <div className="chart-container" ref={container}><svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label={`Temperature over ${hours} hour${hours === 1 ? '' : 's'}, safe range ${min} to ${max} °C`} onPointerMove={event => {
    const box = event.currentTarget.getBoundingClientRect(), at = t0 + ((event.clientX - box.left) / box.width * W - M.l) / (W - M.l - M.r) * (t1 - t0);
    let left = 0, right = times.length - 1;
    while (left < right) { const mid = Math.floor((left + right) / 2); if (times[mid] < at) left = mid + 1; else right = mid; }
    setFocused(left > 0 && Math.abs(times[left - 1] - at) < Math.abs(times[left] - at) ? left - 1 : left);
  }}>
    <rect x={M.l} y={y(max)} width={W - M.l - M.r} height={y(min) - y(max)} className="safe-band" /><text x={M.l + 6} y={y(max) + 16} className="band-label">safe {min}–{max} °C</text>
    {gaps.map(([a, b], i) => <rect key={i} x={x(a)} y={M.t} width={Math.max(0, x(b) - x(a))} height={H - M.t - M.b} className="missing-band" />)}
    {[lo, (lo + hi) / 2, hi].map((v, i) => <g key={i}><line x1={M.l} x2={W - M.r} y1={y(v)} y2={y(v)} className="grid" /><text x={M.l - 8} y={y(v) + 4} textAnchor="end" className="tick">{v.toFixed(0)}°</text></g>)}
    {groups.map((group, i) => <polyline key={i} points={group.map(p => `${x(Date.parse(p.timestamp)).toFixed(1)},${y(p.temp_c).toFixed(1)}`).join(' ')} className="temp-line" />)}
    {points.filter(p => p.temp_c < min || p.temp_c > max).map(p => <circle key={p.timestamp} cx={x(Date.parse(p.timestamp))} cy={y(p.temp_c)} r="3" className="breach-dot" />)}
    <circle cx={x(times[index])} cy={y(selected.temp_c)} r="5" fill="#172d29" />
    <text x={M.l} y={H - 8} className="tick">{label(t0)}</text><text x={W - M.r} y={H - 8} textAnchor="end" className="tick">{label(t1)}</text>
  </svg>
    {gaps.length > 0 && <p className="small muted">Shaded gaps indicate more than 90 seconds without readings, including the start or end of the window.</p>}
    {total > points.length && <p className="small muted">Chart uses {points.length} representative samples from {total} readings, retaining temperature extrema and outage boundaries. Raw readings are available below.</p>}
    <label className="chart-inspector">Inspect reading<input type="range" min="0" max={points.length - 1} value={index} aria-valuetext={`${timestamp(selected.timestamp)} · ${selected.temp_c.toFixed(1)} °C`} onChange={e => setFocused(Number(e.target.value))} /></label>
    <p className="small">{timestamp(selected.timestamp)} · {selected.temp_c.toFixed(1)} °C</p>
    <details onToggle={e => { setTable(e.currentTarget.open); if (e.currentTarget.open) setSnapshot(end || new Date(t1).toISOString()); }}><summary>View readings as a table</summary>{table && <RawReadings key={snapshot} truckId={truckId} hours={hours} end={snapshot} points={points} />}</details>
  </div>;
}
