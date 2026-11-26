// Local stand-in for Static Web Apps sign-in (Role 5 – Idowu Ayeni). It speaks the same /.auth addresses and runs the real
// swa-api token code. Two sample people are offered instead of Microsoft accounts; it must never be exposed to a network.
const http = require('node:http');
const { tokenResponse } = require('../swa-api/src/token');
const PEOPLE = { 'dispatcher@greenops.local': 'Local dispatcher (may act)', 'visitor@greenops.local': 'Local visitor (may view)' };
const COOKIE = 'StaticWebAppsAuthCookie';
const principal = email => ({ identityProvider: 'aad', userId: email, userDetails: email, userRoles: ['anonymous', 'authenticated'] });
const person = req => { const m = (req.headers.cookie || '').match(new RegExp(`${COOKIE}=([^;]+)`)); const email = m && decodeURIComponent(m[1]); return email && PEOPLE[email] ? email : null; };
const safePath = value => (typeof value === 'string' && /^\/(?![/\\])/.test(value) ? value : '/');

function handle(req, res) {
  const url = new URL(req.url, 'http://local'), email = person(req);
  const send = (status, type, body, headers = {}) => { res.writeHead(status, { 'Content-Type': type, 'Cache-Control': 'no-store', ...headers }); res.end(body); };
  if (url.pathname === '/.auth/me') return send(200, 'application/json', JSON.stringify({ clientPrincipal: email ? principal(email) : null }));
  if (url.pathname === '/.auth/logout') return send(302, 'text/plain', '', { Location: safePath(url.searchParams.get('post_logout_redirect_uri')), 'Set-Cookie': `${COOKIE}=; Path=/; Max-Age=0` });
  if (url.pathname === '/.auth/login/aad') {
    const chosen = url.searchParams.get('as'), next = safePath(url.searchParams.get('post_login_redirect_uri'));
    if (chosen && PEOPLE[chosen]) return send(302, 'text/plain', '', { Location: next, 'Set-Cookie': `${COOKIE}=${encodeURIComponent(chosen)}; Path=/; HttpOnly; SameSite=Lax` });
    const links = Object.entries(PEOPLE).map(([e, label]) => `<li><a href="?as=${encodeURIComponent(e)}&post_login_redirect_uri=${encodeURIComponent(next)}">${label}</a></li>`).join('');
    return send(200, 'text/html; charset=utf-8', `<!doctype html><html lang="en"><title>Local sign-in</title><body style="font-family:system-ui;max-width:32rem;margin:3rem auto"><h1>Local sign-in</h1><p>On Azure this is the Microsoft sign-in page. Choose a sample person:</p><ul>${links}</ul></body></html>`);
  }
  if (url.pathname === '/api/token') {
    const r = tokenResponse(email ? Buffer.from(JSON.stringify(principal(email))).toString('base64') : '', process.env.SESSION_SIGNING_KEY);
    return send(r.status, 'application/json', JSON.stringify(r.jsonBody), r.headers);
  }
  send(404, 'text/plain', 'not found');
}
module.exports = { handle };
if (require.main === module) http.createServer(handle).listen(Number(process.env.PORT || 8060));
