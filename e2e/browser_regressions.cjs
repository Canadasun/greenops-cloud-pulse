const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '../dashboard/node_modules/playwright');
const { default: AxeBuilder } = require('../dashboard/node_modules/@axe-core/playwright');
const { startApi } = require('./browser_server.cjs');
const assert = require('node:assert/strict');
const http = require('http'), fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..'), artifacts = path.join(root, 'docs/audit-2026-10-10/implemented');
(async () => {
  fs.mkdirSync(artifacts, { recursive: true });
  await assert.rejects(startApi(process.execPath, ['-e', 'process.exit(2)']).ready, /before readiness/);
  await assert.rejects(startApi(process.execPath, ['-e', 'setInterval(()=>{},1000)'], {}, 100).ready, /timed out/);
  const api = startApi(process.env.GREENOPS_PYTHON || path.join(root, 'functions/.venv/bin/python'), [path.join(__dirname, 'browser_api.py')], { cwd: root });
  let server, browser, page;
  const scans = [], errors = [], checks = [];
  try {
    const port = await api.ready;
    server = http.createServer((req, res) => {
      if (req.url.startsWith('/api/')) {
        const proxy = http.request(`http://127.0.0.1:${port}${req.url}`, { method: req.method, headers: req.headers }, r => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
        proxy.on('error', () => { res.writeHead(502); res.end('{}'); }); req.pipe(proxy); return;
      }
      const file = path.join(root, 'dashboard/dist', req.url.split('?')[0] === '/' ? 'index.html' : req.url.split('?')[0]);
      res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
      fs.createReadStream(file).on('error', () => { res.statusCode = 404; res.end(); }).pipe(res);
    });
    await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
    page = await context.newPage(); page.setDefaultTimeout(12000);
    page.on('pageerror', e => errors.push(e.message));
    // Offline tile state is deliberate and deterministic; no dependency on a public tile server.
    await page.route('https://tile.openstreetmap.org/**', route => route.abort());
    const url = `http://127.0.0.1:${server.address().port}`;
    const goto = async query => { await page.goto(`${url}/?${query}`); await page.locator('.connection').filter({ hasText: 'Fleet API connected' }).waitFor(); };
    const scan = async name => {
      const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']).analyze();
      scans.push({ name, violations: result.violations, incomplete: result.incomplete.map(r => ({ id: r.id, nodes: r.nodes.map(n => ({ target: n.target, summary: n.failureSummary })) })) });
      fs.writeFileSync(path.join(artifacts, 'accessibility.json'), JSON.stringify(scans, null, 2));
      assert.deepEqual(result.violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => ({ target: n.target, message: n.failureSummary })) })), [], `${name}: accessibility violations`);
      const dimensions = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }));
      assert(dimensions.scroll <= dimensions.width + 1, `${name}: horizontal overflow ${JSON.stringify(dimensions)}`);
    };
    await goto('view=overview');
    await page.getByRole('button', { name: 'Acknowledge TRK-001 TEMPERATURE' }).waitFor();
    assert(await page.getByRole('button', { name: 'Acknowledge TRK-001 TEMPERATURE' }).isDisabled());
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement.textContent), 'Skip to dashboard');
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'main');
    await scan('desktop overview read-only');
    await page.screenshot({ path: path.join(artifacts, 'desktop-overview.png'), fullPage: true });
    await page.getByText('Read-only · Connect operator').click();
    await scan('expanded operator access');
    await page.getByLabel('Operator access key').fill('bad-key'); await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await page.getByRole('alert').waitFor(); await scan('operator error');
    await page.getByLabel('Operator access key').fill('browser-test-key'); await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await page.getByText('Operator: Browser operator').waitFor();
    await page.getByRole('button', { name: 'Acknowledge TRK-001 TEMPERATURE' }).click();
    await page.getByRole('status').filter({ hasText: 'acknowledged' }).waitFor();
    // Focus moves on the next animation frame after the message renders, so wait for it rather than sampling once.
    await page.waitForFunction(() => document.activeElement?.className === 'action-feedback', null, { timeout: 5000 });
    await page.locator('.brand').click(); await page.getByText('Operator: Browser operator').waitFor();
    checks.push('operator gating, failed/successful connection, acknowledgement feedback/focus, brand preserves session');
    await page.getByRole('link', { name: 'Fleet', exact: true }).click();
    await page.getByLabel('Find a truck').pressSequentially('TRK-004');
    await page.goBack(); await page.getByRole('heading', { level: 1, name: 'Operations overview' }).waitFor();
    await page.goForward(); assert.equal(await page.getByLabel('Find a truck').inputValue(), 'TRK-004');
    await page.locator('.truck-row').click(); await page.locator('.chart').waitFor();
    assert.equal(await page.evaluate(() => document.activeElement.tagName), 'H1');
    assert.equal(await page.locator('.breach-dot').count(), 0);
    await page.getByRole('button', { name: /Back to fleet/ }).click();
    assert.equal(await page.getByLabel('Find a truck').inputValue(), 'TRK-004');
    await page.waitForFunction(() => document.activeElement.classList.contains('truck-row'));
    await page.getByRole('button', { name: 'Clear all filters' }).click();
    await page.getByLabel('Condition', { exact: true }).selectOption('waiting');
    assert.equal(await page.locator('.truck-row').count(), 4);
    assert.equal(await page.locator('.detail').count(), 0);
    checks.push('search replaces history, Back/Forward context, filter/selection consistency, inspector focus return');
    await goto('view=fleet&truck=TRK-001'); await page.locator('.chart').waitFor();
    let release;
    await page.route('**/api/trucks/TRK-004/history?*', async route => { await new Promise(resolve => { release = resolve; }); await route.continue(); });
    // Same document truck switch exercises query identity, without a full reload.
    await page.evaluate(() => { history.pushState(null, '', '?view=fleet&truck=TRK-004'); dispatchEvent(new PopStateEvent('popstate')); });
    await page.getByRole('heading', { level: 1, name: /TRK-004/ }).waitFor();
    assert.equal(await page.locator('.chart').count(), 0);
    await page.waitForTimeout(100); assert(release); release(); await page.locator('.chart').waitFor();
    await page.unroute('**/api/trucks/TRK-004/history?*');
    const historyStart = Date.now();
    await page.getByLabel('Window', { exact: true }).selectOption('24');
    await page.locator('.chart').waitFor();
    const historyRenderMs = Date.now() - historyStart;
    assert(historyRenderMs < 5000, `24h history render took ${historyRenderMs}ms`);
    assert(await page.locator('.temp-line').evaluateAll(nodes => nodes.reduce((n, node) => n + node.getAttribute('points').split(' ').length, 0)) <= 1002);
    await page.getByText(/representative samples from/).waitFor();
    checks.push(`24-hour history rendered in ${historyRenderMs} ms with bounded chart samples`);
    await page.getByRole('slider').focus(); const oldValue = await page.getByRole('slider').inputValue(); await page.keyboard.press('ArrowLeft');
    assert.notEqual(await page.getByRole('slider').inputValue(), oldValue);
    await page.getByText('View readings as a table', { exact: true }).click(); await page.locator('tbody tr').first().waitFor();
    assert.equal(await page.locator('tbody tr').count(), 50);
    const firstRaw = await page.locator('tbody tr').first().textContent();
    await page.getByRole('button', { name: 'Next readings' }).click();
    await page.waitForFunction(first => document.querySelector('tbody tr')?.textContent !== first && document.querySelectorAll('tbody tr').length === 50, firstRaw);
    const colors = await page.evaluate(() => {
      const style = selector => getComputedStyle(document.querySelector(selector));
      return { label: style('.band-label').fill, safe: style('.safe-band').fill, gap: style('.missing-band').fill,
        axis: style('.tick').fill, line: style('.temp-line').stroke, border: style('select').borderTopColor,
        white: style('.detail-card').backgroundColor };
    });
    const contrast = (a, b) => {
      const luminance = value => value.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => { const c = v / 255; return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4; }).reduce((sum, value, i) => sum + value * [.2126, .7152, .0722][i], 0);
      const [lo, hi] = [luminance(a), luminance(b)].sort((a, b) => a - b);
      return (hi + .05) / (lo + .05);
    };
    const contrastChecks = [
      ['safe-band label', colors.label, colors.safe, 4.5], ['gap label', colors.label, colors.gap, 4.5],
      ['chart axis', colors.axis, colors.white, 4.5], ['chart line over gap', colors.line, colors.gap, 3],
      ['input boundary', colors.border, colors.white, 3]
    ].map(([name, foreground, background, minimum]) => ({ name, foreground, background, minimum, ratio: contrast(foreground, background) }));
    contrastChecks.forEach(check => assert(check.ratio >= check.minimum, `${check.name}: contrast ${check.ratio}`));
    fs.writeFileSync(path.join(artifacts, 'contrast.json'), JSON.stringify(contrastChecks, null, 2));
    await scan('truck detail with raw readings and keyboard chart');
    await page.screenshot({ path: path.join(artifacts, 'desktop-detail.png'), fullPage: true });
    checks.push('obsolete chart data cleared, keyboard chart inspection, raw readings');
    await goto('view=alerts&tab=resolved'); await page.getByRole('button', { name: 'Next', exact: true }).click(); await page.getByText('Page 2', { exact: true }).waitFor();
    await page.getByRole('button', { name: /Inspect truck TRK-001/ }).first().click(); await page.locator('.chart').waitFor();
    await page.getByRole('button', { name: /Back to incidents/ }).click(); await page.getByText('Page 2', { exact: true }).waitFor();
    await scan('resolved page 2');
    checks.push('resolved pagination retained across inspection');
    for (const width of [1440, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      for (const query of ['view=overview', 'view=fleet', 'view=fleet&mode=map', 'view=alerts', 'view=alerts&tab=monitoring', 'view=alerts&tab=resolved', 'view=system', 'view=fleet&truck=TRK-001']) {
        await goto(query);
        if (query.includes('mode=map')) { await page.locator('.leaflet-container').waitFor(); await page.getByText(/Map tiles are unavailable/).waitFor(); }
        if (query.includes('truck=')) await page.locator('.chart').waitFor();
        if (query.includes('system')) await page.getByLabel('Fault scenario for TRK-001').waitFor();
        await scan(`${width}px ${query}`);
        if ([1440, 390].includes(width) && query === 'view=fleet&mode=map') await page.screenshot({ path: path.join(artifacts, `map-${width}.png`), fullPage: true });
        if (width === 390 && query === 'view=overview') await page.screenshot({ path: path.join(artifacts, 'mobile-overview.png'), fullPage: true });
        if (width === 390 && query.includes('truck=')) await page.screenshot({ path: path.join(artifacts, 'mobile-detail.png'), fullPage: true });
      }
    }
    await goto('view=fleet');
    await page.locator('.truck-row').filter({ hasText: 'TRK-004' }).focus(); await page.keyboard.press('Enter'); await page.locator('.chart').waitFor();
    assert.equal(await page.evaluate(() => document.activeElement.tagName), 'H1');
    // The heading takes focus so screen readers announce the new page, but it is not a control: no visible ring.
    assert.equal(await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle), 'none', 'page heading shows a focus ring');
    await page.getByRole('button', { name: /Back to fleet/ }).click();
    await page.waitForFunction(() => document.activeElement.classList.contains('truck-row'));
    checks.push('32 responsive view states: overflow and axe, mobile keyboard inspection and return');
    await page.setViewportSize({ width: 1440, height: 1000 });
    await goto('view=system'); await page.getByText('Read-only · Connect operator').click(); await page.getByLabel('Operator access key').fill('browser-test-key'); await page.getByRole('button', { name: 'Connect', exact: true }).click(); await page.getByText('Operator: Browser operator').waitFor();
    await page.getByLabel('Fault scenario for TRK-001').selectOption('door'); await page.getByRole('status').filter({ hasText: 'scenario applied' }).waitFor();
    await scan('operator simulation changed');
    await page.getByLabel('Fault scenario for TRK-001').selectOption('none'); await page.getByRole('status').filter({ hasText: 'scenario applied' }).waitFor();
    await page.route('**/api/alerts?*', route => route.fulfill({ status: 503, json: { error: 'Test outage' } }));
    await goto('view=overview'); await page.getByRole('alert').filter({ hasText: 'Open incidents: Test outage' }).waitFor();
    assert.equal(await page.getByText('No incidents reported in this view.').count(), 0);
    await scan('partial outage');
    await page.unroute('**/api/alerts?*');
    const fleetResponse = await (await page.request.get(`${url}/api/trucks`)).json();
    const stale = fleetResponse.map(t => ({ ...t, last_seen: '2020-01-01T00:00:00Z' }));
    await page.route('**/api/trucks', route => route.fulfill({ json: stale }));
    await goto('view=overview'); await page.getByText('0 / 6', { exact: true }).waitFor();
    assert(await page.getByText(/Stale ·/).count() > 0); await scan('stale telemetry despite successful API');
    await page.unroute('**/api/trucks');
    const incidentBase = (await (await page.request.get(`${url}/api/alerts?status=OPEN`)).json()).items[0];
    await page.route('**/api/alerts?*', route => route.fulfill({ json: { items: Array.from({ length: 25 }, (_, i) => ({ ...incidentBase, id: `test-${i}`, status: 'ACTIVE' })), next_cursor: null } }));
    await goto('view=alerts'); await page.waitForFunction(() => document.querySelectorAll('article.incident').length === 25);
    await scan('25 open incidents');
    await page.unroute('**/api/alerts?*');
    await goto('view=fleet&mode=map'); await page.getByText('2 trucks share this location. Choose a truck:').waitFor();
    await page.locator('.map-overlap').getByRole('button', { name: 'TRK-004' }).click(); await page.getByRole('button', { name: 'Inspect TRK-004', exact: true }).click(); await page.locator('.chart').waitFor();
    // Leaving the map while its first fit-to-fleet zoom is still running must not throw (Leaflet zoom-end timer).
    for (const delay of [0, 100, 200, 300]) {
      await goto('view=fleet&mode=map'); await page.locator('.leaflet-marker-icon').first().waitFor(); await page.waitForTimeout(delay);
      await page.getByRole('navigation', { name: 'Dashboard views' }).getByRole('link', { name: /^Incidents/ }).click(); await page.waitForTimeout(400);
    }
    assert.deepEqual(errors, [], 'leaving the map during its zoom threw');
    checks.push('simulation set/reset, partial outage, stale telemetry, 25 open incidents, co-located map trucks, leaving the map mid-zoom');
    await page.route('**/api/trucks', route => route.fulfill({ json: [{}] }));
    await page.goto(`${url}/?view=fleet`);
    await page.getByRole('alert').filter({ hasText: 'unexpected data' }).waitFor();
    await scan('malformed response recovery');
    await page.unroute('**/api/trucks');
    await page.getByRole('button', { name: 'Retry fleet', exact: true }).click();
    await page.locator('.truck-row').first().waitFor();
    await page.route('**/api/trucks', route => route.fulfill({ json: [] }));
    await goto('view=fleet'); await page.getByText(/No trucks match/).waitFor();
    await scan('empty fleet');
    await page.unroute('**/api/trucks');
    let releaseFleet;
    await page.route('**/api/trucks', async route => { await new Promise(resolve => { releaseFleet = resolve; }); await route.fulfill({ json: fleetResponse }); });
    await page.goto(`${url}/?view=overview`);
    await page.getByText('Connecting to fleet API…').waitFor();
    assert.equal(await page.locator('.metrics button').first().locator('strong').textContent(), '—');
    await scan('loading fleet has unknown counts');
    assert(releaseFleet); releaseFleet(); await page.locator('.connection').filter({ hasText: 'Fleet API connected' }).waitFor();
    await page.unroute('**/api/trucks');
    await page.setViewportSize({ width: 320, height: 900 });
    await goto('view=overview');
    await page.addStyleTag({ content: '* { line-height: 1.5 !important; letter-spacing: .12em !important; word-spacing: .16em !important } p { margin-bottom: 2em !important }' });
    await scan('320px reflow with increased text spacing');
    checks.push('malformed response recovery, empty/loading states and 320px text-spacing reflow');
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(artifacts, 'browser-results.json'), JSON.stringify({ passed: true, scans: scans.length, checks, errors }, null, 2));
    console.log(`Browser regressions passed; ${scans.length} axe scans have zero violations. Keyboard, focus, responsive, auth, incident, map and outage checks passed.`);
  } catch (error) {
    if (page) await page.screenshot({ path: path.join(artifacts, 'failure.png'), fullPage: true }).catch(() => {});
    throw error;
  } finally { if (browser) await browser.close(); if (server) server.close(); api.child.kill(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
