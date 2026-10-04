// Alert history with the Acknowledge action (F9, FR-11).
import { useState } from 'react';
import { ALERT_TITLES, clock } from '../status';

export default function AlertHistory({ alerts, onAcknowledge, user }) {
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const ack = async (id) => {
    setBusy(id); setError(null);
    try { await onAcknowledge(id, user); } catch (e) { setError(e.message); } finally { setBusy(null); }
  };
  if (!alerts) return <p className="muted">Loading alerts…</p>;
  return (
    <>
      {error && <p className="error" role="alert">{error}</p>}
      {alerts.length === 0 ? <p className="muted">No alerts yet – the fleet is healthy.</p> : (
        <table className="alerts">
          <thead><tr><th>Started</th><th>Truck</th><th>Problem</th><th>Details</th><th>Email</th><th>Status</th><th /></tr></thead>
          <tbody>
            {alerts.map((a) => (
              <tr key={a.id} className={`row-${a.status.toLowerCase()}`}>
                <td>{clock(a.started_at)}</td>
                <td>{a.truck_id}</td>
                <td>{ALERT_TITLES[a.type] || a.type}</td>
                <td>{a.details}</td>
                <td>{a.email_sent_at ? `sent in ${a.email_seconds ?? '?'} s` : 'not sent'}</td>
                <td><span className={`pill pill-${a.status.toLowerCase()}`}>{a.status}</span>
                  {a.acknowledged_by && <div className="muted small">by {a.acknowledged_by} at {clock(a.acknowledged_at)}</div>}</td>
                <td>{a.status === 'ACTIVE' && (
                  <button onClick={() => ack(a.id)} disabled={busy === a.id} aria-label={`Acknowledge ${a.truck_id} ${a.type}`}>
                    {busy === a.id ? '…' : 'Acknowledge'}
                  </button>)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
