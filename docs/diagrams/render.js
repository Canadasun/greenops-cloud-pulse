// Renders every diagram source (*.html in this folder) to ../NAME.png at 3x resolution.
// Hand-drawn diagrams are plain SVG; the UML class and sequence diagrams use Mermaid from node_modules.
// Run: npm install && npm run render            (one file: node render.js architecture-azure)
// Chromium: Playwright's own download, or CHROME=/path/to/chrome.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined });
  const page = await browser.newPage({ deviceScaleFactor: 3, viewport: { width: 1700, height: 1200 } });
  const only = process.argv[2];
  for (const f of fs.readdirSync(__dirname).filter((n) => n.endsWith('.html') && (!only || n.startsWith(only))).sort()) {
    const errors = [];
    page.removeAllListeners('pageerror');
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto('file://' + path.join(__dirname, f));
    await page.waitForFunction(() => window.READY === true, null, { timeout: 30000 }).catch(() => {});
    if (errors.length) throw new Error(`${f}: ${errors.join('; ')}`);
    const out = path.join(__dirname, '..', f.replace('.html', '.png'));
    await page.locator('#d').screenshot({ path: out });
    console.log('wrote docs/' + path.basename(out));
  }
  await browser.close();
})().catch((e) => { console.error(e.message); process.exit(1); });
