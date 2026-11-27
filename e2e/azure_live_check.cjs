// Feature-by-feature check of the LIVE Azure deployment in Chromium (Part 1, Table 3: F1–F12). All roles.
// Usage (add GREENOPS_SMS=off while no sms_phones are set): GREENOPS_URL=https://<static web app> GREENOPS_API=https://<function app>/api GREENOPS_OPERATOR_EMAIL=<operator> \
//        SESSION_SIGNING_KEY=$(terraform -chdir=infra/terraform output -raw session_signing_key) \
//        node e2e/azure_live_check.cjs [screenshot-dir]
// Before running, use the demo faults: TRK-001 humidity, TRK-003 compressor, TRK-002 door, TRK-005 offline, TRK-004 delay (past its ETA).
// The check acknowledges the TRK-003 temperature alert and switches TRK-006 to "door" and back, so use a demo deployment.
// F5 (certificates) and F6 (archive) are checked from outside the browser by e2e/azure_live_backend.py.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '../dashboard/node_modules/playwright');
const assert = require('node:assert/strict');
const path = require('path'), fs = require('fs');

const url = process.env.GREENOPS_URL, api = process.env.GREENOPS_API, email = process.env.GREENOPS_OPERATOR_EMAIL, key = process.env.SESSION_SIGNING_KEY;
const { issue } = require('../swa-api/src/token');
const sessionFor = who => issue({ email: who }, key);
const out = process.argv[2] || path.join(__dirname, 'live-screenshots');
const results = [];
const pass = (feature, what) => { results.push([feature, what]); console.log(`✓ ${feature.padEnd(4)} ${what}`); };
const getJson = async (p, opts = {}) => { const r = await fetch(api + p, { ...opts, headers: { Authorization: `Bearer ${sessionFor(email).token}`, ...opts.headers } }); return { status: r.status, body: await r.json().catch(() => ({})) }; };
const openAlerts = async () => (await getJson('/alerts?status=OPEN')).body.items;

(async () => {
  assert(url && api && email && key, 'set GREENOPS_URL, GREENOPS_API, GREENOPS_OPERATOR_EMAIL and SESSION_SIGNING_KEY');
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH || undefined });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }), errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  const truckCalls = [];
  page.on('request', (r) => { if (/\/api\/trucks$/.test(r.url())) truckCalls.push(Date.now()); });
  // Incident navigation includes an action count; match the start of the link name.
  const nav = (label) => page.getByRole('navigation', { name: 'Dashboard views' }).getByRole('link', { name: new RegExp('^' + label.replace(/[&()]/g, '\\$&')) }).click();
  try {
    // ---- F7 simulated fleet + F1 live map
    // ---- F12 sign-in: the real site shows only the sign-in page and gives no token; the API refuses everyone without one
    await page.goto(url);
    await page.getByRole('link', { name: 'Sign in with Microsoft' }).waitFor({ timeout: 60000 });
    await page.screenshot({ path: path.join(out, 'sign_in.png') });
    for (const p of ['/trucks', '/alerts', '/health', '/routes', '/sim/trucks', '/session']) assert.equal((await fetch(api + p)).status, 401, p);
    assert([401, 302].includes((await fetch(url + '/api/token', { redirect: 'manual' })).status), 'token without a Microsoft sign-in');
    assert.match((await fetch(url + '/.auth/login/aad', { redirect: 'manual' })).headers.get('location') || '', /login\.(microsoftonline|live)\.com|identity/);
    pass('F12', 'without a Microsoft sign-in: sign-in page only, no token, every API view answers 401');
    // From here the two sign-in answers are supplied by this script (a person cannot type a Microsoft password in a test).
    let current = 'viewer@example.com';
    await page.route('**/.auth/me', r => r.fulfill({ json: { clientPrincipal: { identityProvider: 'aad', userDetails: current, userRoles: ['authenticated'] } } }));
    await page.route(new URL('/api/token', url).href, r => r.fulfill({ json: sessionFor(current) }));
    await page.goto(url);
    await page.locator('.connection').filter({ hasText: 'Fleet API connected' }).waitFor({ timeout: 60000 });
    await page.locator('.truck-row').first().waitFor();
    assert.equal(await page.locator('.truck-row').count(), 6);
    const trucks = (await getJson('/trucks')).body;
    const live = trucks.filter((t) => t.seconds_ago !== undefined && t.seconds_ago <= 30).length;
    assert(live >= 5, `expected live trucks, got ${live}`);
    pass('F7', `6 simulated trucks listed; ${live} reported in the last 30 s through Azure IoT Hub`);
    await page.screenshot({ path: path.join(out, 'overview.png'), fullPage: true });
    await nav('Fleet');
    await page.getByRole('button', { name: 'Map', exact: true }).click();
    await page.waitForFunction(() => [...document.querySelectorAll('img.leaflet-tile')].some((i) => i.complete && i.naturalWidth > 0), null, { timeout: 30000 });
    const status = Object.fromEntries(trucks.map((t) => [t.truck_id, t.status]));
    assert.equal(status['TRK-003'], 'breach'); assert.equal(status['TRK-002'], 'warning'); assert.equal(status['TRK-005'], 'offline');
    assert.equal(await page.locator('.leaflet-marker-icon').count() >= 5, true);
    pass('F1', 'live map with OpenStreetMap tiles and colour/letter markers: breach (TRK-003), warning (TRK-002), offline (TRK-005)');
    await page.screenshot({ path: path.join(out, 'map.png'), fullPage: true });

    // ---- NFR-02 refresh at least every 5 s
    truckCalls.length = 0; await page.waitForTimeout(16000);
    assert(truckCalls.length >= 3, `only ${truckCalls.length} fleet refreshes in 16 s`);
    pass('NFR2', `fleet refreshed ${truckCalls.length} times in 16 s (every ~5 s)`);

    // ---- F4 detail + chart, F10 thresholds per cargo type
    await page.locator('.truck-row').filter({ hasText: 'TRK-003' }).click();
    await page.locator('.detail h2').filter({ hasText: 'TRK-003' }).waitFor();
    await page.locator('.chart').waitFor();
    assert((await page.locator('.breach-dot').count()) > 0, 'compressor fault should show readings outside the safe band');
    pass('F4', 'TRK-003 detail with one-hour chart; readings above the safe band are marked');
    await page.locator('.detail').screenshot({ path: path.join(out, 'detail.png') });
    const detailText = await page.locator('.detail').innerText();
    assert(/2\D{1,6}8\s*°C/.test(detailText), 'vaccine truck should show the 2–8 °C range');
    const frozen = trucks.find((t) => t.cargo_type === 'frozen_food');
    await page.getByRole('button', { name: /Back to fleet/ }).click();
    await page.locator('.truck-row').filter({ hasText: frozen.truck_id }).click();
    await page.locator('.detail h2').filter({ hasText: frozen.truck_id }).waitFor();
    assert(/−?-?25\D{1,6}−?-?15\s*°C/.test(await page.locator('.detail').innerText()), 'frozen truck should show −25 to −15 °C');
    pass('F10', `cargo limits per type: vaccines 2–8 °C (TRK-003), frozen food −25 to −15 °C (${frozen.truck_id})`);

    // ---- F2, F3, F8: alerts raised and emails sent by the Logic App (Azure Communication Services)
    const alerts = await openAlerts();
    const find = (truck, type) => alerts.find((a) => a.truck_id === truck && a.type === type);
    const temp = find('TRK-003', 'TEMPERATURE'), door = find('TRK-002', 'DOOR_OPEN'), off = find('TRK-005', 'OFFLINE'), late = find('TRK-004', 'DELAYED');
    for (const [a, name] of [[temp, 'TRK-003 TEMPERATURE'], [door, 'TRK-002 DOOR_OPEN'], [off, 'TRK-005 OFFLINE'], [late, 'TRK-004 DELAYED']]) {
      assert(a, `no open ${name} alert`); assert.equal(a.email_status, 'sent', `${name} email not confirmed sent`);
    }
    assert(temp.email_seconds < 30, 'NFR-01: email within 30 s');
    pass('F2', `temperature breach alert; email confirmed sent by the Logic App in ${temp.email_seconds} s (NFR-01: < 30 s)`);
    const damp = find('TRK-001', 'HUMIDITY');
    assert(damp && damp.email_status === 'sent', 'no emailed TRK-001 HUMIDITY alert');
    pass('F2', `humidity breach alert; email sent in ${damp.email_seconds} s`);
    if (process.env.GREENOPS_SMS === 'off') {  // no sms_phones in Terraform yet: the channel must stay silent
      assert([temp, damp, door, off, late].every((a) => !a.sms_status || a.sms_status === 'off'), 'SMS is off, so nothing may be texted');
      pass('F13', 'SMS channel not configured on this deployment (no phone numbers); no text messages were requested');
    } else {
      for (const a of [temp, damp]) assert.equal(a.sms_status, 'requested', `${a.truck_id} text message`);
      assert([door, off, late].every((a) => !a.sms_status), 'only cargo emergencies are texted');
      pass('F13', 'text messages requested from Azure Monitor for the two cargo emergencies, and for nothing else');
    }
    pass('F3', `door-open alert after the 120 s limit; email sent in ${door.email_seconds} s`);
    pass('F8', `offline alert (TRK-005, email ${off.email_seconds} s) and delayed alert (TRK-004, email ${late.email_seconds} s)`);

    // ---- F12 roles: a viewer cannot act, a named operator can
    await nav('Incidents');
    const ackName = 'Acknowledge TRK-003 TEMPERATURE';
    await page.getByRole('button', { name: ackName }).waitFor({ timeout: 30000 });
    assert.equal(await page.getByRole('button', { name: ackName }).isDisabled(), true, 'read-only viewers cannot acknowledge');
    const viewer = await getJson('/sim/trucks/TRK-006/fault', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${sessionFor('viewer@example.com').token}` }, body: '{"scenario":"door"}' });
    assert.equal(viewer.status, 403);
    current = email;
    await page.goto(url + '/?view=alerts');
    await page.getByText('Operator', { exact: true }).waitFor({ timeout: 30000 });
    const who = (await getJson('/session')).body.user;
    pass('F12', `a viewer cannot act (button disabled, API 403); operator signed in as "${who}"`);
    await page.screenshot({ path: path.join(out, 'alerts_before.png'), fullPage: true });

    // ---- F9 alert history + acknowledge
    await page.getByRole('button', { name: ackName }).click();
    await page.getByRole('status').filter({ hasText: 'acknowledged' }).waitFor();
    const acked = (await openAlerts()).find((a) => a.id === temp.id);
    assert.equal(acked.status, 'ACKNOWLEDGED'); assert(acked.acknowledged_by);
    pass('F9', `dispatcher acknowledged the TRK-003 alert; stored as ACKNOWLEDGED by "${acked.acknowledged_by}"`);
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(out, 'alerts_after.png'), fullPage: true });

    // ---- F7 faults on demand from the dashboard, F11 health and cost panel
    await nav('System');
    const fault = page.getByLabel('Fault scenario for TRK-006');
    await fault.waitFor();
    await fault.selectOption('door');
    await page.getByRole('status').filter({ hasText: 'scenario applied' }).waitFor();
    assert.equal((await getJson('/sim/trucks')).body['TRK-006'], 'door');
    const sysText = await page.locator('main').innerText();
    assert(/USD|\$/.test(sysText) && /message/i.test(sysText), 'health and cost panel should show messages and cost');
    await page.screenshot({ path: path.join(out, 'system.png'), fullPage: true });
    await fault.selectOption('none');
    let cleared = false;
    for (let i = 0; i < 10 && !cleared; i++) { cleared = (await getJson('/sim/trucks')).body['TRK-006'] === 'none'; if (!cleared) await page.waitForTimeout(1500); }
    assert(cleared, 'fault was not cleared');
    pass('F7', 'fault panel switched TRK-006 to "door" and back to "none" through the Fleet API (FR-02)');
    pass('F11', 'system health and cost panel shows message counts and the cost assumption');

    // ---- responsive views, no browser errors
    await page.setViewportSize({ width: 390, height: 900 });
    for (const [label, view] of [['Overview', 'overview'], ['Fleet', 'fleet'], ['Fleet', 'map'], ['Incidents', 'alerts'], ['System', 'system']]) {
      await nav(label);
      if (view === 'map') await page.getByRole('button', { name: 'Map', exact: true }).click();
      if (view === 'fleet') await page.getByRole('button', { name: 'List', exact: true }).click();
      await page.waitForTimeout(500);
      const scroll = await page.evaluate(() => document.documentElement.scrollWidth);
      assert(scroll <= 391, `${view} overflows 390px (${scroll}px)`);
      if (view === 'overview') await page.screenshot({ path: path.join(out, 'mobile.png'), fullPage: true });
    }
    pass('UI', 'all five views fit a 390 px phone screen');
    assert.deepEqual(errors, []);
    pass('UI', 'no JavaScript errors in the browser');
    fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 1));
    console.log(`Live Azure check passed: ${results.length} checks.`);
  } finally { await browser.close(); }
})().catch((e) => { console.error(e); process.exitCode = 1; });
