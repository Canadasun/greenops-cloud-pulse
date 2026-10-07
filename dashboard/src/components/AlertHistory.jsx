import { useState } from 'react';
import { ALERT_TITLES, timestamp } from '../status';

export default function AlertHistory({ alerts, onAcknowledge, onSelect, canOperate = true, user }) {
  const [busy, setBusy] = useState(new Set());
  const [notice, setNotice] = useState(null);
  const ack = async (id) => {
    setBusy(s => new Set(s).add(id)); setNotice(null);
    try {
      await onAcknowledge(id, user);
      setNotice({ text: 'Alert acknowledged. Monitoring continues.', error: false });
    } catch (e) { setNotice({ text: e.message, error: true }); }
    finally { setBusy(s => { const next = new Set(s); next.delete(id); return next; }); }
  };
  if (!alerts) return null;
  return <>
    {notice && <p className={notice.error ? 'error' : 'success'} role={notice.error ? 'alert' : 'status'}>{notice.text}</p>}
    {!alerts.length ? <p className="empty">No incidents reported in this view.</p> : <div className="incident-list">
      {alerts.map(a => <article key={a.id} className={`incident incident-${a.status.toLowerCase()}`} aria-label={`${a.truck_id} ${ALERT_TITLES[a.type] || a.type}`}>
        <div className="incident-title"><div>
          {onSelect ? <button className="text-button" onClick={() => onSelect(a.truck_id)}>{a.truck_id}</button> : <strong>{a.truck_id}</strong>}
          <h3>{ALERT_TITLES[a.type] || a.type}</h3>
        </div><span className={`pill pill-${a.status.toLowerCase()}`}>{a.status.toLowerCase()}</span></div>
        <p>{a.details}</p>
        <div className="incident-meta"><time dateTime={a.started_at}>{timestamp(a.started_at)}</time>
          <span>Email: {a.email_sent_at ? 'sent' : a.email_status === 'accepted' ? 'queued with provider' : a.email_status === 'failed' ? 'failed · retry scheduled' : 'queued'}</span>
        </div>
        {a.acknowledged_by && <p className="small muted">Acknowledged by {a.acknowledged_by} · {timestamp(a.acknowledged_at)}</p>}
        {a.status === 'ACTIVE' && <button onClick={() => ack(a.id)} disabled={!canOperate || busy.has(a.id)} aria-label={`Acknowledge ${a.truck_id} ${a.type}`}>
          {busy.has(a.id) ? 'Acknowledging…' : 'Acknowledge'}
        </button>}
      </article>)}
    </div>}
  </>;
}
