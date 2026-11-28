// Shared drawing helpers for the two UML use case diagrams (SVG).
const NS = 'http://www.w3.org/2000/svg';
const svg = document.getElementById('svg');
function el(tag, attrs, text, parent = svg) { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (text != null) e.textContent = text; parent.appendChild(e); return e; }
function txt(x, y, s, cls = 't', anchor = 'middle', extra = {}) { return el('text', { x, y, class: cls, 'text-anchor': anchor, ...extra }, s); }
el('defs', {}).innerHTML = `
 <marker id="open" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="10" markerHeight="10" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10" fill="none" stroke="#1a1a19" stroke-width="1.6"/></marker>
 <marker id="tri" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="14" markerHeight="14" orient="auto-start-reverse"><path d="M0,0 L12,6 L0,12 Z" fill="#fff" stroke="#1a1a19" stroke-width="1.4"/></marker>`;
const INK = '#1a1a19';
function person(x, y, name, sub) {
  el('circle', { cx: x, cy: y - 46, r: 14, fill: '#fff', stroke: INK, 'stroke-width': 2.4 });
  el('line', { x1: x, y1: y - 32, x2: x, y2: y + 6, stroke: INK, 'stroke-width': 2.4 });
  el('line', { x1: x - 22, y1: y - 20, x2: x + 22, y2: y - 20, stroke: INK, 'stroke-width': 2.4 });
  el('line', { x1: x, y1: y + 6, x2: x - 18, y2: y + 34, stroke: INK, 'stroke-width': 2.4 });
  el('line', { x1: x, y1: y + 6, x2: x + 18, y2: y + 34, stroke: INK, 'stroke-width': 2.4 });
  txt(x, y + 60, name, 'b'); if (sub) txt(x, y + 81, sub, 's');
  return { x, y, top: y - 62, bottom: y + 36, hand: [x, y - 20] };
}
function systemActor(x, y, name, sub, kind) {
  el('rect', { x: x - 42, y: y - 54, width: 84, height: 84, rx: 8, fill: '#fff', stroke: INK, 'stroke-width': 2.4 });
  txt(x, y - 30, '«' + kind + '»', 's');
  const g = el('g', { transform: `translate(${x},${y})`, fill: 'none', stroke: INK, 'stroke-width': 2 });
  if (kind === 'device') { el('rect', { x: -24, y: -14, width: 30, height: 20 }, null, g); el('path', { d: 'M6,-6 h10 l8,8 v6 h-18 z' }, null, g); el('circle', { cx: -14, cy: 10, r: 4 }, null, g); el('circle', { cx: 14, cy: 10, r: 4 }, null, g); }
  if (kind === 'timer') { el('circle', { cx: 0, cy: -2, r: 15 }, null, g); el('path', { d: 'M0,-2 V-12 M0,-2 H9' }, null, g); }
  if (kind === 'service') { el('rect', { x: -20, y: -14, width: 40, height: 26 }, null, g); el('path', { d: 'M-20,-14 L0,2 L20,-14' }, null, g); }
  txt(x, y + 58, name, 'b'); if (sub) txt(x, y + 79, sub, 's');
  return { x, y, hand: [x, y - 12] };
}
function uc(cx, cy, name, ids, prio, rx = 190) {
  const could = prio === 'Could';
  el('ellipse', { cx, cy, rx, ry: 44, fill: could ? '#ffffff' : '#e8f0fb', stroke: '#2E5496', 'stroke-width': 2.2, 'stroke-dasharray': could ? '8 6' : 'none' });
  txt(cx, cy - 3, name); txt(cx, cy + 21, `${ids} · ${prio}`, 's');
  return { cx, cy, rx, ry: 44 };
}
function edge(u, tx, ty) { const dx = tx - u.cx, dy = ty - u.cy; const t = 1 / Math.sqrt((dx * dx) / (u.rx * u.rx) + (dy * dy) / (u.ry * u.ry)); return [u.cx + dx * t, u.cy + dy * t]; }
function assoc(a, u, side = 1) { const [ax, ay] = [a.hand[0] + side * 30, a.hand[1]]; const [ex, ey] = edge(u, ax, ay); el('line', { x1: ax, y1: ay, x2: ex, y2: ey, stroke: '#55554f', 'stroke-width': 1.9 }); }
function dep(u1, u2, label, dx = 0, dy = 0) {
  const [x1, y1] = edge(u1, u2.cx, u2.cy); const [x2, y2] = edge(u2, u1.cx, u1.cy);
  el('line', { x1, y1, x2, y2, stroke: INK, 'stroke-width': 1.8, 'stroke-dasharray': '7 5', 'marker-end': 'url(#open)' });
  const mx = (x1 + x2) / 2 + dx, my = (y1 + y2) / 2 + dy;
  el('rect', { x: mx - 46, y: my - 15, width: 92, height: 24, fill: '#f6f8fc' });
  txt(mx, my + 3, label, 's', 'middle', { 'font-style': 'italic', fill: INK });
}
function boundary(x, y, w, h, title) { el('rect', { x, y, width: w, height: h, rx: 14, fill: '#f6f8fc', stroke: '#1F3864', 'stroke-width': 2.6 }); txt(x + w / 2, y + 38, title, 'b'); }
function legend(x, y, w, lines) {
  const h = 46 + lines.length * 27;
  el('rect', { x, y, width: w, height: h, rx: 10, fill: '#fff', stroke: '#A6A6A6' });
  txt(x + 18, y + 30, 'How to read this diagram', 'b', 'start');
  lines.forEach((s, i) => txt(x + 18, y + 58 + i * 27, '• ' + s, 's', 'start'));
}
