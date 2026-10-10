import { useState } from 'react';
import { api, setOperatorKey } from '../api';
export default function OperatorAccess({ identity, onIdentity }) {
  const [key, setKey] = useState(''), [error, setError] = useState(null), [busy, setBusy] = useState(false);
  const connect = async e => {
    e.preventDefault(); setBusy(true); setError(null); setOperatorKey(key);
    try { const result = await api.session(); if (!result.can_operate) throw new Error('Operator key was not recognized.'); setKey(''); onIdentity(result.user); }
    catch (e) { setOperatorKey(''); setError(e.message); } finally { setBusy(false); }
  };
  if (identity) return <div className="operator"><span>Operator: {identity}</span><button onClick={() => { setOperatorKey(''); onIdentity(null); }}>Disconnect</button></div>;
  return <details className="operator-access"><summary>Read-only · Connect operator</summary><form onSubmit={connect}><label>Operator access key<input type="password" value={key} onChange={e => setKey(e.target.value)} autoComplete="off" required /></label><button disabled={busy}>{busy ? 'Connecting…' : 'Connect'}</button><p className="small muted">Your administrator supplies this key. It stays in this tab’s memory; reconnect after a reload.</p>{error && <p role="alert" className="error">{error}</p>}</form></details>;
}
