import { useContext, useRef, useState } from 'react';
import { ALERT_TITLES, timestamp } from '../status';
import { ClockContext, readingAge } from './UI';
export default function AlertHistory({ alerts, onAcknowledge, onSelect, canOperate = true, user, compact = false }) {
  const [busy, setBusy] = useState(new Set()), [notice, setNotice] = useState(null);
  const now = useContext(ClockContext), feedback = useRef(null);
  const ack = async id => {
    setBusy(s => new Set(s).add(id)); setNotice(null);
    try { await onAcknowledge(id, user); setNotice({ text: 'Alert acknowledged. Monitoring continues.', error: false }); }
    catch (e) { setNotice({ text: e.message, error: true }); }
    finally { setBusy(s => { const next = new Set(s); next.delete(id); return next; }); requestAnimationFrame(() => feedback.current?.focus()); }
  };
  return <>
    <div ref={feedback} tabIndex="-1" className="action-feedback" role={notice?.error ? 'alert' : 'status'}>{notice && <p className={notice.error ? 'error' : 'success'}>{notice.text}</p>}</div>
    {alerts && (!alerts.length ? <p className="empty">No incidents reported in this view.</p> : <div className={`incident-list ${compact ? 'compact' : ''}`}>
      {alerts.map(a => <article key={a.id} className={`incident incident-${a.status.toLowerCase()}`} aria-label={`${a.truck_id} ${ALERT_TITLES[a.type] || a.type}`}>
        <div className="incident-main"><div className="incident-title"><h3>{a.truck_id} · {ALERT_TITLES[a.type] || a.type}</h3><span className={`pill pill-${a.status.toLowerCase()}`}>{a.status === 'ACTIVE' ? 'Needs action' : a.status === 'ACKNOWLEDGED' ? 'Monitoring' : 'Resolved'}</span></div><p>{a.details}</p>
        <p className="small muted">{a.status === 'RESOLVED' ? `Resolved ${timestamp(a.resolved_at)}` : `Open for ${Math.floor((readingAge(a.started_at, now) ?? 0) / 60)} min`} · Started <time dateTime={a.started_at}>{timestamp(a.started_at)}</time></p>
        <details><summary>Incident activity</summary><div className="incident-meta"><span>Email: {a.email_sent_at ? 'sent' : a.email_status === 'accepted' ? 'queued with provider' : a.email_status === 'failed' ? 'failed · retry scheduled' : a.email_status === 'abandoned' ? 'not delivered · retries stopped' : 'queued'}</span>{a.acknowledged_by && <span>Acknowledged by {a.acknowledged_by} · {timestamp(a.acknowledged_at)}</span>}{a.resolved_at && <span>Recovered · {timestamp(a.resolved_at)}</span>}</div></details></div>
        <div className="incident-actions">{onSelect && <button onClick={e => onSelect(a.truck_id, a, e.currentTarget)} aria-label={`Inspect truck ${a.truck_id} ${ALERT_TITLES[a.type] || a.type}`}>Inspect truck</button>}{a.status === 'ACTIVE' && onAcknowledge && <button className="primary" onClick={() => ack(a.id)} disabled={!canOperate || busy.has(a.id)} aria-label={`Acknowledge ${a.truck_id} ${a.type}`}>{busy.has(a.id) ? 'Acknowledging…' : 'Acknowledge'}</button>}</div>
      </article>)}
    </div>)}
  </>;
}
