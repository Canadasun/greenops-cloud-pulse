import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { LOGIN_URL, LOGOUT_URL, SignedOutError, onSignedOut, readPerson } from '../session';

export function SignInPage({ ended }) {
  return <div className="sign-in"><main className="card" id="main">
    <span className="logo" aria-hidden="true">GO</span>
    <h1>GreenOps Cloud Pulse</h1>
    <p>Live cold-chain monitoring: where every refrigerated truck is, and whether its cargo is safe.</p>
    {ended && <p role="status" className="error">Your session has ended. Sign in again to continue.</p>}
    <a className="button primary" href={LOGIN_URL}>Sign in with Microsoft</a>
    <p className="small muted">Any Microsoft account can view the fleet. Only named dispatchers can acknowledge alerts or start demo faults.</p>
  </main></div>;
}

export function Account({ session }) {
  return <div className="operator"><span>{session.user} <span className="pill">{session.can_operate ? 'Operator' : 'View only'}</span></span><a className="button" href={LOGOUT_URL}>Sign out</a></div>;
}

/** Shows its children only to a signed-in person; children receive { user, can_operate }. */
export default function SignInGate({ children }) {
  const [state, setState] = useState({ phase: 'loading' });
  const load = useCallback(async () => {
    setState({ phase: 'loading' });
    try {
      if (!(await readPerson())) return setState({ phase: 'signed-out' });
      setState({ phase: 'signed-in', session: await api.session() });
    } catch (e) { setState(e instanceof SignedOutError ? { phase: 'signed-out' } : { phase: 'error', message: e.message }); }
  }, []);
  useEffect(() => { load(); return onSignedOut(() => setState(s => s.phase === 'signed-in' ? { phase: 'signed-out', ended: true } : s)); }, [load]);
  if (state.phase === 'loading') return <div className="sign-in"><p role="status">Checking your sign-in…</p></div>;
  if (state.phase === 'error') return <div className="sign-in"><main className="card" id="main"><h1>GreenOps Cloud Pulse</h1><p role="alert" className="error">{state.message}</p><button className="primary" onClick={load}>Try again</button></main></div>;
  if (state.phase === 'signed-out') return <SignInPage ended={state.ended} />;
  return children(state.session);
}
