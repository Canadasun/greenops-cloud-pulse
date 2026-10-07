// Feature-by-feature check of the LIVE Azure deployment in Chromium (Part 1, Table 3: F1–F12). All roles.
// Usage: GREENOPS_URL=https://<static web app> GREENOPS_API=https://<function app>/api GREENOPS_OPERATOR_KEY=<key> \
//        node e2e/azure_live_check.cjs [screenshot-dir]
// Before running, use the demo faults: TRK-003 compressor, TRK-002 door, TRK-005 offline, TRK-004 delay (past its ETA).
// The check acknowledges the TRK-003 temperature alert and switches TRK-001 to "door" and back, so use a demo deployment.
// F5 (certificates) and F6 (archive) are checked from outside the browser by e2e/azure_live_backend.py.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '../dashboard/node_modules/playwright');
const assert = require('node:assert/strict');
const path = require('path'), fs = require('fs');

const url = process.env.GREENOPS_URL, api = process.env.GREENOPS_API, key = process.env.GREENOPS_OPERATOR_KEY;
const out = process.argv[2] || path.join(__dirname, 'live-screenshots');
const results = [];
const pass = (feature, what) => { results.push([feature, what]); console.log(`✓ ${feature.padEnd(4)} ${what}`); };
const getJson = async (p, opts = {}) => { const r = await fetch(api + p, opts); return { status: r.status, body: await r.json().catch(() => ({})) }; };
const openAlerts = async () => (await getJson('/alerts?status=OPEN')).body.items;

(async () => {
  assert(url && api && key, 'set GREENOPS_URL, GREENOPS_API and GREENOPS_OPERATOR_KEY');
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH || undefined });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }), errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  const truckCalls = [];
  page.on('request', (r) => { if (/\/api\/trucks$/.test(r.url())) truckCalls.push(Date.now()); });
  // The Alerts button shows a count, e.g. "Alerts (5)", so match the start of the name.
  const nav = (label) => page.getByRole('navigation', { name: 'Dashboard views' }).getByRole('button', { name: new RegExp('^' + label.replace(/[&()]/g, '\\$&')) }).click();
  try {
    // ---- F7 simulated fleet + F1 live map
    await page.goto(url);
    await page.locator('.connection').filter({ hasText: 'Fleet connected' }).waitFor({ timeout: 60000 });
    await page.locator('.truck-row').first().waitFor();
    assert.equal(await page.locator('.truck-row').count(), 6);
    const trucks = (await getJson('/trucks')).body;
    const live = trucks.filter((t) => t.seconds_ago !== undefined && t.seconds_ago <= 30).length;
    assert(live >= 5, `expected live trucks, got ${live}`);
    pass('F7', `6 simulated trucks listed; ${live} reported in the last 30 s through Azure IoT Hub`);
    await page.waitForFunction(() => [...document.querySelectorAll('img.leaflet-tile')].some((i) => i.complete && i.naturalWidth > 0), null, { timeout: 30000 });
    const status = Object.fromEntries(trucks.map((t) => [t.truck_id, t.status]));
    assert.equal(status['TRK-003'], 'breach'); assert.equal(status['TRK-002'], 'warning'); assert.equal(status['TRK-005'], 'offline');
    assert.equal(await page.locator('.leaflet-marker-icon').count() >= 5, true);
    pass('F1', 'live map with OpenStreetMap tiles and colour/letter markers: breach (TRK-003), warning (TRK-002), offline (TRK-005)');
    await page.screenshot({ path: path.join(out, 'overview.png'), fullPage: true });

    // ---- NFR-02 refresh at least every 5 s
    truckCalls.length = 0; await page.waitForTimeout(16000);
    assert(truckCalls.length >= 3, `only ${truckCalls.length} fleet refreshes in 16 s`);
    pass('NFR2', `fleet refreshed ${truckCalls.length} times in 16 s (every ~5 s)`);

    // ---- F4 detail + chart, F10 thresholds per cargo type
    await page.locator('.truck-row').filter({ hasText: 'TRK-003' }).click();
    await page.locator('.detail h3').filter({ hasText: 'TRK-003' }).waitFor();
    await page.locator('.chart').waitFor();
    assert((await page.locator('.breach-dot').count()) > 0, 'compressor fault should show readings outside the safe band');
    pass('F4', 'TRK-003 detail with one-hour chart; readings above the safe band are marked');
    await page.locator('.detail').screenshot({ path: path.join(out, 'detail.png') });
    const detailText = await page.locator('.detail').innerText();
    assert(/2\D{1,6}8\s*°C/.test(detailText), 'vaccine truck should show the 2–8 °C range');
    const frozen = trucks.find((t) => t.cargo_type === 'frozen_food');
    await page.locator('.truck-row').filter({ hasText: frozen.truck_id }).click();
    await page.locator('.detail h3').filter({ hasText: frozen.truck_id }).waitFor();
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
    pass('F3', `door-open alert after the 120 s limit; email sent in ${door.email_seconds} s`);
    pass('F8', `offline alert (TRK-005, email ${off.email_seconds} s) and delayed alert (TRK-004, email ${late.email_seconds} s)`);

    // ---- F12 (partial): write actions need an operator key
    await nav('Alerts');
    const ackName = 'Acknowledge TRK-003 TEMPERATURE';
    await page.getByRole('button', { name: ackName }).waitFor({ timeout: 30000 });
    assert.equal(await page.getByRole('button', { name: ackName }).isDisabled(), true, 'read-only viewers cannot acknowledge');
    const anon = await getJson('/sim/trucks/TRK-001/fault', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"scenario":"door"}' });
    assert.equal(anon.status, 401);
    await page.getByText('Read-only · Connect operator').click();
    await page.getByLabel('Operator access key').fill(key);
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    const who = (await page.getByText(/^Operator: /).first().innerText()).trim();
    pass('F12', `read-only without a key (button disabled, API 401); signed in as "${who.replace(/^Operator: /, '')}"`);
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
    await nav('System & demo');
    const fault = page.getByLabel('Fault scenario for TRK-001');
    await fault.waitFor();
    await fault.selectOption('door');
    await page.getByRole('status').filter({ hasText: 'scenario applied' }).waitFor();
    assert.equal((await getJson('/sim/trucks')).body['TRK-001'], 'door');
    const sysText = await page.locator('main').innerText();
    assert(/USD|\$/.test(sysText) && /message/i.test(sysText), 'health and cost panel should show messages and cost');
    await page.screenshot({ path: path.join(out, 'system.png'), fullPage: true });
    await fault.selectOption('none');
    await page.waitForFunction(async (a) => (await (await fetch(a + '/sim/trucks')).json())['TRK-001'] === 'none', api, { timeout: 20000 });
    pass('F7', 'fault panel switched TRK-001 to "door" and back to "none" through the Fleet API (FR-02)');
    pass('F11', 'system health and cost panel shows message counts and the cost assumption');

    // ---- responsive views, no browser errors
    await page.setViewportSize({ width: 390, height: 900 });
    for (const [label, view] of [['Overview', 'overview'], ['Fleet', 'fleet'], ['Map', 'map'], ['Alerts', 'alerts'], ['System & demo', 'system']]) {
      await nav(label); await page.waitForTimeout(500);
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
