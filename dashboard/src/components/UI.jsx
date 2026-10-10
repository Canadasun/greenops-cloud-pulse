import { Component, createContext, useContext, useEffect, useState } from 'react';
import { STATUS, ago, timestamp } from '../status';
export const ClockContext = createContext(Date.now());
export function ClockProvider({ children }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  return <ClockContext.Provider value={now}>{children}</ClockContext.Provider>;
}
export function readingAge(lastSeen, now) {
  const time = Date.parse(lastSeen);
  return Number.isFinite(time) ? Math.max(0, Math.floor((now - time) / 1000)) : null;
}
export function Freshness({ lastSeen }) {
  const age = readingAge(lastSeen, useContext(ClockContext));
  return <span className={age == null || age > 90 ? 'freshness stale' : 'freshness'}><time dateTime={lastSeen || undefined} title={timestamp(lastSeen)}>{age == null ? 'Awaiting telemetry' : `${age > 90 ? 'Stale · ' : ''}${ago(age)}`}</time></span>;
}
export function StatusBadge({ status }) {
  const s = STATUS[status] || { label: 'Unknown condition', letter: '?', color: '#edf0ef', text: '#41413e' };
  return <span className="pill" style={{ background: s.color, color: s.text }}>{s.letter} · {s.label}</span>;
}
export class ErrorBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <main className="card recovery"><h1>This view could not be displayed</h1><p>Your fleet data has not been changed. Reload to reconnect.</p><button onClick={() => location.reload()}>Reload dashboard</button></main>;
    return this.props.children;
  }
}
export const priority = { TEMPERATURE: 0, HUMIDITY: 0, OFFLINE: 1, DOOR_OPEN: 2, DELAYED: 3 };
export function prioritize(items = []) {
  return [...items].sort((a, b) => (priority[a.type] ?? 4) - (priority[b.type] ?? 4) || Date.parse(a.started_at) - Date.parse(b.started_at) || a.id.localeCompare(b.id));
}
