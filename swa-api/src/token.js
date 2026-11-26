// Session tokens for the Fleet API (F12, Role 5 – Idowu Ayeni). No dependencies, so it is easy to test and to read.
// Static Web Apps has already signed the person in with Microsoft and adds the x-ms-client-principal header itself;
// it removes that header from outside requests, so a visitor cannot invent one.
const { createHmac } = require('node:crypto');

const ISSUER = 'greenops-dashboard', AUDIENCE = 'greenops-fleet-api';
const LIFE_S = 15 * 60, MIN_KEY = 32;
const b64 = value => Buffer.from(value).toString('base64url');

/** The signed-in person from the platform header, or null. Only Microsoft accounts are accepted. */
function readPrincipal(header) {
  try {
    const p = JSON.parse(Buffer.from(header, 'base64').toString('utf8'));
    const email = typeof p.userDetails === 'string' ? p.userDetails.trim().toLowerCase() : '';
    const signedIn = Array.isArray(p.userRoles) && p.userRoles.includes('authenticated');
    return p.identityProvider === 'aad' && signedIn && email && email.length <= 254 ? { email } : null;
  } catch { return null; }
}

function issue(principal, key, nowS = Math.floor(Date.now() / 1000)) {
  if (!key || key.length < MIN_KEY) throw new Error('SESSION_SIGNING_KEY is missing or too short');
  const message = `${b64('{"alg":"HS256","typ":"JWT"}')}.${b64(JSON.stringify({ iss: ISSUER, aud: AUDIENCE, email: principal.email, iat: nowS, exp: nowS + LIFE_S }))}`;
  return { token: `${message}.${createHmac('sha256', key).update(message).digest('base64url')}`, expires_at: new Date((nowS + LIFE_S) * 1000).toISOString() };
}

/** The whole endpoint as a pure function: header and key in, HTTP answer out. */
function tokenResponse(header, key) {
  const headers = { 'Cache-Control': 'no-store' };
  const principal = readPrincipal(header);
  if (!principal) return { status: 401, headers, jsonBody: { error: 'sign in with a Microsoft account' } };
  try { return { status: 200, headers, jsonBody: issue(principal, key) }; }
  catch { return { status: 503, headers, jsonBody: { error: 'sign-in is not configured' } }; }
}
module.exports = { readPrincipal, issue, tokenResponse, LIFE_S };
