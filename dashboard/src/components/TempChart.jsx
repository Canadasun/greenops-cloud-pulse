// One-hour temperature chart for the selected truck (F4). Green band = safe range for the cargo.
const W = 360, H = 170, M = { l: 38, r: 10, t: 12, b: 26 };

export default function TempChart({ points, min, max }) {
  if (!points || points.length < 2) return <p className="muted">Collecting readings for the chart…</p>;
  const temps = points.map((p) => p.temp_c);
  const lo = Math.min(min, ...temps) - 1, hi = Math.max(max, ...temps) + 1;
  const t0 = new Date(points[0].timestamp).getTime(), t1 = new Date(points.at(-1).timestamp).getTime();
  const x = (t) => M.l + ((new Date(t).getTime() - t0) / Math.max(t1 - t0, 1)) * (W - M.l - M.r);
  const y = (v) => M.t + ((hi - v) / (hi - lo)) * (H - M.t - M.b);
  const ticks = [lo, (lo + hi) / 2, hi].map((v) => Math.round(v));
  const line = points.map((p) => `${x(p.timestamp).toFixed(1)},${y(p.temp_c).toFixed(1)}`).join(' ');
  const outside = points.filter((p) => p.temp_c < min || p.temp_c > max);
  const label = (iso) => new Date(iso).toLocaleTimeString('en-CA', { hour: '2-digit', minute: '2-digit', hour12: false });
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label={`Temperature over the last hour, safe range ${min} to ${max} °C`}>
      <rect x={M.l} y={y(max)} width={W - M.l - M.r} height={y(min) - y(max)} className="safe-band" />
      <text x={M.l + 4} y={y(max) + 13} className="band-label">safe {min}–{max} °C</text>
      {ticks.map((v) => (
        <g key={v}>
          <line x1={M.l} x2={W - M.r} y1={y(v)} y2={y(v)} className="grid" />
          <text x={M.l - 6} y={y(v) + 4} textAnchor="end" className="tick">{v}°</text>
        </g>
      ))}
      <polyline points={line} className="temp-line" />
      {outside.map((p) => (
        <circle key={p.timestamp} cx={x(p.timestamp)} cy={y(p.temp_c)} r="4" className="breach-dot">
          <title>{`${label(p.timestamp)} · ${p.temp_c.toFixed(1)} °C`}</title>
        </circle>
      ))}
      <text x={M.l} y={H - 6} className="tick">{label(points[0].timestamp)}</text>
      <text x={W - M.r} y={H - 6} textAnchor="end" className="tick">{label(points.at(-1).timestamp)}</text>
    </svg>
  );
}
