// Sign-in state of the dashboard (F12, Role 5 – Idowu Ayeni).
// Static Web Apps signs the person in (/.auth/…); /api/token then gives a 15-minute Fleet API token, kept only in memory.
const RENEW_BEFORE_MS = 2 * 60 * 1000;
export const LOGIN_URL = '/.auth/login/aad?post_login_redirect_uri=/';
export const LOGOUT_URL = '/.auth/logout?post_logout_redirect_uri=/';
export class SignedOutError extends Error { constructor() { super('Your session has ended. Please sign in again.'); this.name = 'SignedOutError'; } }

let current = null, pending = null;
const listeners = new Set();
export function onSignedOut(fn) { listeners.add(fn); return () => listeners.delete(fn); }
export function forgetToken() { current = null; pending = null; }

async function fetchToken() {
  const res = await fetch('/api/token', { cache: 'no-store' });
  if (res.status === 401 || res.status === 403) { current = null; listeners.forEach(fn => fn()); throw new SignedOutError(); }
  if (!res.ok) throw new Error('Sign-in is temporarily unavailable. Please retry.');
  const body = await res.json().catch(() => { throw new Error('The server returned an unreadable response.'); });
  if (typeof body.token !== 'string' || !Number.isFinite(Date.parse(body.expires_at))) throw new Error('The sign-in service returned unexpected data.');
  current = { token: body.token, expiresAt: Date.parse(body.expires_at) };
  return current.token;
}

/** A valid token. Many panels poll at once: they share one renewal. renew=true replaces a token the API refused. */
export function getToken({ renew = false } = {}) {
  if (!renew && current && current.expiresAt - Date.now() > RENEW_BEFORE_MS) return Promise.resolve(current.token);
  if (!pending) pending = fetchToken().finally(() => { pending = null; });
  return pending;
}

/** Is somebody signed in? Asked once when the page opens. */
export async function readPerson() {
  const res = await fetch('/.auth/me', { cache: 'no-store' });
  if (!res.ok) throw new Error('Sign-in is temporarily unavailable. Please retry.');
  const { clientPrincipal } = await res.json();
  return clientPrincipal?.userDetails || null;
}
