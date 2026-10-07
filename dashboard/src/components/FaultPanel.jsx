import { useState } from 'react';
const OPTIONS = [['none', 'Normal'], ['compressor', 'Compressor failure'], ['door', 'Door left open'], ['delay', 'Traffic delay'], ['offline', 'Go offline']];
export default function FaultPanel({ faults, onChange, canOperate = false }) {
  const [pending, setPending] = useState({});
  const [notice, setNotice] = useState(null);
  const change = async (id, scenario) => {
    setPending(s => ({ ...s, [id]: scenario })); setNotice(null);
    try { await onChange(id, scenario); setNotice({ text: `${id}: scenario applied.`, error: false }); }
    catch (e) { setNotice({ text: e.message, error: true }); }
    finally { setPending(s => { const copy = { ...s }; delete copy[id]; return copy; }); }
  };
  if (!faults) return null;
  return <>
    <p className="muted">Demo controls change simulated truck conditions. Sensors update on the next reading.</p>
    {!canOperate && <p>Connect an operator key to change scenarios.</p>}
    {notice && <p role={notice.error ? 'alert' : 'status'} className={notice.error ? 'error' : 'success'}>{notice.text}</p>}
    <div className="faults">{Object.entries(faults).map(([id, scenario]) => <label key={id}>
      <span>{id}{pending[id] != null && <span className="small"> · Applying…</span>}</span>
      <select value={pending[id] ?? scenario} disabled={!canOperate || pending[id] != null} onChange={e => change(id, e.target.value)} aria-label={`Fault scenario for ${id}`}>
        {OPTIONS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
      </select>
    </label>)}</div>
  </>;
}
