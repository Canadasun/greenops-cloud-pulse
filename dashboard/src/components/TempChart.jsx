import { useState } from 'react';
import { timestamp } from '../status';
const W = 420, H = 200, M = { l: 40, r: 12, t: 18, b: 30 };
export default function TempChart({ points, min, max, hours = 1 }) {
  const [focused, setFocused] = useState(null);
  if (!points?.length) return <p className="empty">No readings in this time window.</p>;
  if (points.length < 2) return <p className="empty">Collecting readings for the chart…</p>;
  if (!Number.isFinite(min) || !Number.isFinite(max)) return <p>Safe range unavailable.</p>;
  const temps = points.map(p => p.temp_c);
  const lo = Math.min(min, ...temps) - 1, hi = Math.max(max, ...temps) + 1;
  const t0 = new Date(points[0].timestamp).getTime(), t1 = new Date(points.at(-1).timestamp).getTime();
  const x = t => M.l + ((new Date(t).getTime() - t0) / Math.max(t1 - t0, 1)) * (W - M.l - M.r);
  const y = v => M.t + ((hi - v) / (hi - lo)) * (H - M.t - M.b);
  const groups = [[]];
  points.forEach((p, i) => {
    if (i && new Date(p.timestamp) - new Date(points[i - 1].timestamp) > 90000) groups.push([]);
    groups.at(-1).push(p);
  });
  const label = value => new Date(value).toLocaleTimeString('en-CA', { hour: '2-digit', minute: '2-digit' });
  return <div>
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label={`Temperature over ${hours} hour${hours === 1 ? '' : 's'}, safe range ${min} to ${max} °C`}
      onPointerMove={event => {
        const box = event.currentTarget.getBoundingClientRect();
        const at = t0 + (((event.clientX - box.left) / box.width * W - M.l) / (W - M.l - M.r)) * (t1 - t0);
        let nearest = 0;
        points.forEach((p, i) => { if (Math.abs(new Date(p.timestamp).getTime() - at) < Math.abs(new Date(points[nearest].timestamp).getTime() - at)) nearest = i; });
        setFocused(nearest);
      }}>
      <rect x={M.l} y={y(max)} width={W - M.l - M.r} height={y(min) - y(max)} className="safe-band" />
      <text x={M.l + 4} y={y(max) + 13} className="band-label">safe {min}–{max} °C</text>
      {[lo, (lo + hi) / 2, hi].map((v, i) => <g key={i}><line x1={M.l} x2={W - M.r} y1={y(v)} y2={y(v)} className="grid" /><text x={M.l - 6} y={y(v) + 4} textAnchor="end" className="tick">{v.toFixed(0)}°</text></g>)}
      {groups.map((group, i) => <polyline key={i} points={group.map(p => `${x(p.timestamp).toFixed(1)},${y(p.temp_c).toFixed(1)}`).join(' ')} className="temp-line" />)}
      {points.filter(p => p.temp_c < min || p.temp_c > max).map(p => <circle key={p.timestamp} cx={x(p.timestamp)} cy={y(p.temp_c)} r="4" className="breach-dot"><title>{`${timestamp(p.timestamp)} · ${p.temp_c.toFixed(1)} °C`}</title></circle>)}
      {focused != null && points[focused] && <circle cx={x(points[focused].timestamp)} cy={y(points[focused].temp_c)} r="5" fill="#172d29" />}
      <text x={M.l} y={H - 6} className="tick">{label(points[0].timestamp)}</text><text x={W - M.r} y={H - 6} textAnchor="end" className="tick">{label(points.at(-1).timestamp)}</text>
    </svg>
    {groups.length > 1 && <p className="small muted">Gaps show intervals longer than 90 seconds without readings.</p>}
    <label className="chart-inspector">Inspect reading <input type="range" min="0" max={points.length - 1} value={Math.min(focused ?? points.length - 1, points.length - 1)} onChange={e => setFocused(Number(e.target.value))} /></label>
    <p className="small" aria-live="polite">{(() => { const p = points[Math.min(focused ?? points.length - 1, points.length - 1)]; return `${timestamp(p.timestamp)} · ${p.temp_c.toFixed(1)} °C`; })()}</p>
    <details><summary>View readings as a table</summary><div className="table-scroll" tabIndex="0" role="region" aria-label="Temperature readings"><table><thead><tr><th>Time</th><th>Temperature</th><th>Humidity</th></tr></thead><tbody>{points.map(p => <tr key={p.timestamp}><td>{timestamp(p.timestamp)}</td><td>{p.temp_c.toFixed(1)} °C</td><td>{p.humidity_pct ?? '—'} %</td></tr>)}</tbody></table></div></details>
  </div>;
}
