const { test } = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const { readPrincipal, issue, tokenResponse } = require('../src/token');
const KEY = 'k'.repeat(48);
const header = over => Buffer.from(JSON.stringify({ identityProvider: 'aad', userId: 'u1', userDetails: 'Visitor@Outlook.com', userRoles: ['anonymous', 'authenticated'], ...over })).toString('base64');

test('a Microsoft sign-in gives a token with the email in lower case', () => {
  const r = tokenResponse(header(), KEY);
  assert.equal(r.status, 200);
  assert.equal(r.headers['Cache-Control'], 'no-store');
  const claims = JSON.parse(Buffer.from(r.jsonBody.token.split('.')[1], 'base64url'));
  assert.equal(claims.email, 'visitor@outlook.com');
  assert.equal(claims.exp - claims.iat, 900);
});
for (const [name, value] of Object.entries({ missing: '', rubbish: '%%%', 'not JSON': Buffer.from('hi').toString('base64'), 'another provider': header({ identityProvider: 'github' }),
  'not signed in': header({ userRoles: ['anonymous'] }), 'no email': header({ userDetails: '' }), 'very long email': header({ userDetails: 'a'.repeat(300) }) })) {
  test(`no token when the sign-in header is: ${name}`, () => { assert.equal(readPrincipal(value), null); assert.equal(tokenResponse(value, KEY).status, 401); });
}
test('a missing or short key is a configuration error, never an unsigned token', () => {
  for (const key of [undefined, '', 'short']) assert.equal(tokenResponse(header(), key).status, 503);
});
// The contract between the two languages: what swa-api issues, the Python Fleet API accepts.
test('the Fleet API accepts this token and refuses a changed one', () => {
  const { token } = issue({ email: 'a@b.ca' }, KEY);
  const check = t => execFileSync(process.env.GREENOPS_PYTHON || 'python3', ['-c',
    'import sys; sys.path.insert(0, sys.argv[1]); from shared import session; print((session.verify(sys.argv[2], sys.argv[3]) or {}).get("email"))',
    path.resolve(__dirname, '../../functions'), t, KEY]).toString().trim();
  assert.equal(check(token), 'a@b.ca');
  assert.equal(check(token.replace('.', '.x')), 'None');
});
