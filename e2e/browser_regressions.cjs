const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '../dashboard/node_modules/playwright');
const { spawn } = require('child_process');
const { once } = require('events');
const assert = require('node:assert/strict');
const http = require('http'), fs = require('fs'), path = require('path');
const root=path.resolve(__dirname,'..'), artifacts=path.join(root,'docs/audit-2026-10-07/fixed');
(async()=>{
  fs.mkdirSync(artifacts,{recursive:true});
  const python=spawn(process.env.GREENOPS_PYTHON || path.join(root,'functions/.venv/bin/python'),[path.join(__dirname,'browser_api.py')],{cwd:root,stdio:['ignore','pipe','inherit']});
  let server,browser;
  try {
    const port=Number((await once(python.stdout,'data'))[0].toString().trim());assert(port);
    server=http.createServer((req,res)=>{
      if(req.url.startsWith('/api/')) {
        const p=http.request(`http://127.0.0.1:${port}${req.url}`,{method:req.method,headers:req.headers},r=>{res.writeHead(r.statusCode,r.headers);r.pipe(res)});
        p.on('error',()=>{res.writeHead(502);res.end('{}')});req.pipe(p);return;
      }
      const file=path.join(root,'dashboard/dist',req.url.split('?')[0]==='/'?'index.html':req.url.split('?')[0]);
      res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');
      fs.createReadStream(file).on('error',()=>{res.statusCode=404;res.end()}).pipe(res);
    });
    await new Promise(r=>server.listen(0,'127.0.0.1',r));
    browser=await chromium.launch({headless:true});
    const page=await browser.newPage({viewport:{width:1440,height:1050}}), errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    const url='http://127.0.0.1:'+server.address().port;
    await page.goto(url);await page.locator('.chart').waitFor();
    assert.equal(await page.getByRole('button',{name:'Acknowledge TRK-001 TEMPERATURE'}).isDisabled(),true);
    await page.getByText('Read-only · Connect operator').click();
    await page.getByLabel('Operator access key').fill('browser-test-key');await page.getByRole('button',{name:'Connect',exact:true}).click();
    await page.getByText('Operator: Browser operator').waitFor();
    await page.getByRole('button',{name:'Acknowledge TRK-001 TEMPERATURE'}).click();await page.getByRole('status').filter({hasText:'acknowledged'}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Acknowledge TRK-001 TEMPERATURE'}).count(),0);
    let release;
    await page.route('**/api/trucks/TRK-004/history?*',async r=>{await new Promise(resolve=>release=resolve);await r.continue()});
    await page.locator('.truck-row').filter({hasText:'TRK-004'}).click();
    await page.locator('.detail h3').filter({hasText:'TRK-004'}).waitFor();
    assert.equal(await page.locator('.chart').count(),0,'old truck history must disappear immediately');
    while(!release) await page.waitForTimeout(20);release();await page.locator('.chart').waitFor();
    assert.equal(await page.locator('.breach-dot').count(),0,'frozen truck must not inherit vaccine samples');
    await page.unroute('**/api/trucks/TRK-004/history?*');
    await page.screenshot({path:path.join(artifacts,'desktop.png'),fullPage:true});
    for(const width of [320,390,768]) {
      await page.setViewportSize({width,height:900});
      for(const view of ['overview','fleet','map','alerts','system']) {
        await page.goto(url+'/?view='+view);await page.locator('.connection').filter({hasText:'Fleet connected'}).waitFor();
        await page.waitForTimeout(150);
        const dimensions=await page.evaluate(()=>({viewport:innerWidth,scroll:document.documentElement.scrollWidth}));
        assert(dimensions.scroll<=width+1,`${view} overflows ${width}px: ${JSON.stringify(dimensions)}`);
        if(width===390&&view==='overview') await page.screenshot({path:path.join(artifacts,'mobile.png'),fullPage:true});
      }
    }
    await page.setViewportSize({width:1440,height:1050});
    await page.goto(url+'/?view=system');await page.getByText('Read-only · Connect operator').click();
    await page.getByLabel('Operator access key').fill('browser-test-key');await page.getByRole('button',{name:'Connect',exact:true}).click();await page.getByText('Operator: Browser operator').waitFor();
    await page.getByLabel('Fault scenario for TRK-001').selectOption('door');await page.getByRole('status').filter({hasText:'scenario applied'}).waitFor();
    assert.equal(await page.getByLabel('Fault scenario for TRK-001').inputValue(),'door');
    await page.goto(url+'/?view=alerts');await page.getByRole('button',{name:'Next',exact:true}).click();await page.getByText('Page 2',{exact:true}).waitFor();
    await page.route('**/api/alerts?*',r=>r.fulfill({status:503,json:{error:'Test outage'}}));
    await page.goto(url);await page.getByRole('alert').filter({hasText:'Open incidents: Test outage'}).waitFor();
    assert.equal(await page.getByText('No incidents reported in this view.').count(),0);
    assert.deepEqual(errors,[]);console.log('Browser regressions passed: operator auth, acknowledgement, chart identity, 15 responsive views, fault mutation, paging and partial outage.');
  } finally { if(browser)await browser.close();if(server)server.close();python.kill(); }
})().catch(e=>{console.error(e);process.exitCode=1});
