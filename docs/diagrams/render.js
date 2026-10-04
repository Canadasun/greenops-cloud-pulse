// Renders architecture-local.html to ../architecture-local.png (needs playwright).
const path = require('path');
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME || undefined });
  const p = await b.newPage({ deviceScaleFactor: 3 });
  await p.goto('file://' + path.join(__dirname, 'architecture-local.html'));
  await p.waitForFunction(() => window.READY === true);
  await p.locator('#d').screenshot({ path: path.join(__dirname, '..', 'architecture-local.png') });
  await b.close();
})();
