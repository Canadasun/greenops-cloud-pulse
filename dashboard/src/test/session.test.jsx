import { render, screen, waitFor, act } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { request } from '../api';
import { forgetToken, getToken, SignedOutError } from '../session';
import SignInGate, { Account, SignInPage } from '../components/SignIn';

const json = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
const token = (minutes = 15, name = 'tok') => json({ token: name, expires_at: new Date(Date.now() + minutes * 60000).toISOString() });
let calls;
function server(routes) {
  calls = [];
  vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => { calls.push([url, options.headers?.Authorization]); const r = routes[url]; return typeof r === 'function' ? r(calls) : r; }));
}
beforeEach(forgetToken);
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

test('many panels asking at once share one token request', async () => {
  server({ '/api/token': token() });
  expect(await Promise.all([getToken(), getToken(), getToken()])).toEqual(['tok', 'tok', 'tok']);
  expect(calls).toHaveLength(1);
});
test('a token is renewed shortly before it expires', async () => {
  let n = 0;
  server({ '/api/token': () => token(n++ ? 15 : 1.5, `tok${n}`) });
  expect(await getToken()).toBe('tok1');
  expect(await getToken()).toBe('tok2'); // 90 s left is inside the two-minute renewal margin
  expect(await getToken()).toBe('tok2');
});
test('every API request carries the token; a refused one is renewed once', async () => {
  let n = 0;
  server({ '/api/token': () => token(15, `tok${++n}`), '/api/x': c => c.filter(([u]) => u === '/api/x').length === 1 ? json({}, 401) : json({ fine: true }) });
  expect(await request('/api/x')).toEqual({ fine: true });
  expect(calls.filter(([u]) => u === '/api/x').map(([, a]) => a)).toEqual(['Bearer tok1', 'Bearer tok2']);
});
test('a view-only refusal (403) is shown, not retried', async () => {
  server({ '/api/token': token(), '/api/x': json({ error: 'your account can view only; operators can act' }, 403) });
  await expect(request('/api/x')).rejects.toThrow('view only');
  expect(calls.filter(([u]) => u === '/api/x')).toHaveLength(1);
});
test('a signed-out token request fails as signed out', async () => {
  server({ '/api/token': json({}, 401) });
  await expect(getToken()).rejects.toBeInstanceOf(SignedOutError);
});
test('a visitor who is not signed in sees the sign-in page and no data request is made', async () => {
  server({ '/.auth/me': json({ clientPrincipal: null }) });
  render(<SignInGate>{() => <p>fleet data</p>}</SignInGate>);
  expect(await screen.findByRole('link', { name: 'Sign in with Microsoft' })).toHaveAttribute('href', expect.stringMatching(/^\/\.auth\/login\/aad/));
  expect(screen.queryByText('fleet data')).toBeNull();
  expect(calls.map(([u]) => u)).toEqual(['/.auth/me']);
});
test('a signed-in visitor sees the dashboard, and the sign-in page again when the session ends', async () => {
  let ended = false;
  server({ '/.auth/me': json({ clientPrincipal: { userDetails: 'v@outlook.com' } }), '/api/token': () => ended ? json({}, 401) : token(), '/api/session': json({ user: 'v@outlook.com', can_operate: false }) });
  render(<SignInGate>{s => <Account session={s} />}</SignInGate>);
  expect(await screen.findByText('View only')).toBeInTheDocument();
  ended = true;
  await act(async () => { await getToken({ renew: true }).catch(() => {}); });
  expect(await screen.findByText(/session has ended/)).toBeInTheDocument();
});
test('an unavailable sign-in service offers a retry', async () => {
  server({ '/.auth/me': json({}, 500) });
  render(<SignInGate>{() => null}</SignInGate>);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument());
});
test('the account shows operators and viewers in words', () => {
  const { rerender } = render(<Account session={{ user: 'Dispatcher', can_operate: true }} />);
  expect(screen.getByText('Operator')).toBeInTheDocument();
  rerender(<Account session={{ user: 'v@x.ca', can_operate: false }} />);
  expect(screen.getByText('View only')).toBeInTheDocument();
  rerender(<SignInPage />);
  expect(screen.getByText(/Only named dispatchers/)).toBeInTheDocument();
});
