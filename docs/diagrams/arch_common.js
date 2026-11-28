// Shared drawing helpers for the two architecture diagrams (Azure and local), same layout as Part 2, Figure 7.
// Colour = owner role; dashed boxes are outside the platform; a ★ in a title marks a Part 4 change.
const NS = 'http://www.w3.org/2000/svg', svg = document.getElementById('svg');
function el(tag, a, t) { const e = document.createElementNS(NS, tag); for (const k in a) e.setAttribute(k, a[k]); if (t != null) e.textContent = t; svg.appendChild(e); return e; }
el('defs', {}).innerHTML = `<marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#3a3a36"/></marker>`;
const INK = '#1a1a19', STAR = '#c0392b';
const R = { 1: ['#e3eefb', '#2a78d6'], 2: ['#fbe6ee', '#b3366b'], 3: ['#fde7dd', '#c25a00'], 4: ['#ddf3ea', '#138a5e'], 5: ['#fdf1d6', '#a87200'], x: ['#ffffff', '#6b6b64'], ops: ['#eef0f4', '#55607a'] };
// A line that starts with ★ is drawn in red, so the Part 4 changes stand out.
function line(x, y, s, size, weight) {
  const star = s.startsWith('★');
  el('text', { x, y, 'text-anchor': 'middle', 'font-size': size, 'font-weight': weight, fill: star ? STAR : (weight === 700 ? INK : '#2f2f2b') }, s);
}
function card(cx, cy, w, h, title, lines, r, dashed = false) {
  el('rect', { x: cx - w / 2, y: cy - h / 2, width: w, height: h, rx: 12, fill: R[r][0], stroke: R[r][1], 'stroke-width': 2.4, ...(dashed ? { 'stroke-dasharray': '7 5' } : {}) });
  const n = lines.length, y0 = cy - (n * 20) / 2 + 2;
  line(cx, y0, title, 18, 700);
  lines.forEach((s, i) => line(cx, y0 + 23 + i * 20, s, 15));
  return { cx, cy, l: cx - w / 2, r: cx + w / 2, t: cy - h / 2, b: cy + h / 2 };
}
function arrow(pts, n, at, label, dashed = false) {
  el('polyline', { points: pts.map((p) => p.join(',')).join(' '), fill: 'none', stroke: '#3a3a36', 'stroke-width': 2.2, 'marker-end': 'url(#ar)', ...(dashed ? { 'stroke-dasharray': '7 5' } : {}) });
  if (n) {
    const star = n.startsWith('★'), num = n.replace('★', '');
    el('circle', { cx: at[0], cy: at[1], r: 13, fill: star ? STAR : '#1F3864' });
    el('text', { x: at[0], y: at[1] + 5, 'text-anchor': 'middle', 'font-size': 15, 'font-weight': 700, fill: '#fff' }, num);
  }
  if (label) { const [t, x, y] = label; const w = t.length * 7.6 + 10; el('rect', { x: x - w / 2, y: y - 13, width: w, height: 19, fill: '#fff', opacity: 0.92 }); el('text', { x, y: y + 2, 'text-anchor': 'middle', 'font-size': 14, 'font-style': 'italic', fill: INK }, t); }
}
function colHead(cx, l1, l2, r) { el('text', { x: cx, y: 98, 'text-anchor': 'middle', 'font-size': 17, 'font-weight': 700, fill: R[r][1] }, l1); el('text', { x: cx, y: 118, 'text-anchor': 'middle', 'font-size': 15, fill: R[r][1] }, l2); }
function heads() {
  el('text', { x: 110, y: 98, 'text-anchor': 'middle', 'font-size': 17, 'font-weight': 700, fill: R[1][1] }, 'Edge');
  el('text', { x: 110, y: 118, 'text-anchor': 'middle', 'font-size': 15, fill: R[1][1] }, 'Role 1 · Ying');
  colHead(335, 'Ingestion', 'Role 2 · Marcelbriaud', 2);
  colHead(560, 'Business logic', 'Role 3 · Shi', 3);
  colHead(820, 'Data', 'Role 4 · Durmusali', 4);
  colHead(1065, 'Presentation', 'Role 5 · Idowu', 5);
}
// Numbered steps in two columns; a step that starts with ★ is a Part 4 addition.
function legend(title, steps, top) {
  const rows = Math.ceil(steps.length / 2);
  el('rect', { x: 10, y: top, width: 1380, height: 52 + rows * 27, rx: 10, fill: '#fff', stroke: '#A6A6A6' });
  el('text', { x: 24, y: top + 26, 'font-size': 18, 'font-weight': 700, fill: INK }, title);
  steps.forEach((s, i) => el('text', { x: 24 + (i >= rows ? 690 : 0), y: top + 54 + (i % rows) * 27, 'font-size': 15, fill: s.startsWith('★') ? STAR : '#2f2f2b' }, s));
}
