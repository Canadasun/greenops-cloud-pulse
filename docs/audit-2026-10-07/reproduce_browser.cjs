const {chromium}=require('/home/canadasun/scribe11/e2e/node_modules/playwright');
const http=require('http'),fs=require('fs'),path=require('path');
const root='/home/canadasun/greenops-cloud-pulse/dashboard/dist';
const out='/home/canadasun/greenops-cloud-pulse/docs/audit-2026-10-07';
(async()=>{
 const server=http.createServer((req,res)=>{
   if(req.url.startsWith('/api/')||req.url.startsWith('/sim/')) {
     const p=http.request('http://127.0.0.1:5173'+req.url,{method:req.method,headers:req.headers},r=>{res.writeHead(r.statusCode,r.headers);r.pipe(res)});p.on('error',()=>{res.writeHead(502);res.end('{}')});req.pipe(p);return;
   }
   const p=path.join(root,req.url==='/'?'index.html':req.url.split('?')[0]);
   res.setHeader('Content-Type',p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':'text/html');
   fs.createReadStream(p).on('error',()=>res.end()).pipe(res);
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true});
 try {
 const page=await browser.newPage({viewport:{width:1440,height:1050}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const url='http://127.0.0.1:'+server.address().port;
 await page.goto(url);await page.waitForSelector('.detail h3');await page.waitForTimeout(1500);
 await page.screenshot({path:out+'/desktop.png',fullPage:true});
 console.log('desktop',JSON.stringify({errors,text:(await page.locator('.updated').innerText())}));
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:out+'/mobile.png',fullPage:true});
 console.log('mobile',JSON.stringify(await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('table,.faults,.brand')].map(x=>({element:x.className,width:x.getBoundingClientRect().width,right:x.getBoundingClientRect().right}))}))));
 // Inject a representative alert list, without modifying any backend records.
 await page.route('**/api/alerts?*',r=>r.fulfill({json:[{id:'audit-alert',truck_id:'TRK-001',type:'TEMPERATURE',details:'10.0 °C outside 2–8 °C (vaccines)',status:'ACTIVE',started_at:new Date().toISOString(),email_sent_at:null}]}));
 await page.reload();await page.waitForSelector('table.alerts');
 await page.screenshot({path:out+'/mobile-alert.png',fullPage:true});
 console.log('mobile_with_alert',JSON.stringify(await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,tableWidth:document.querySelector('table.alerts').getBoundingClientRect().width}))));
 // Delay the new truck history response: old data should not be labelled as the new truck.
 await page.setViewportSize({width:1440,height:1050});
 await page.route('**/api/trucks/*/history?*',async r=>{
 const frozen=r.request().url().includes('TRK-004');
 if(frozen) await new Promise(x=>setTimeout(x,3000));
 await r.fulfill({json:{points:[{timestamp:'2026-10-07T08:00:00Z',temp_c:frozen?-20:4},{timestamp:'2026-10-07T08:01:00Z',temp_c:frozen?-21:5}]}});
 });
 await page.reload();
 await page.locator('.chart').waitFor();
 const before=await page.locator('.temp-line').getAttribute('points');
 await page.locator('[title="TRK-004 – Normal"]').click();await page.waitForTimeout(200);
 console.log('truck_switch',JSON.stringify({heading:await page.locator('.detail h3').innerText(),breachDots:await page.locator('.breach-dot').count(),chartLabel:await page.locator('.chart').getAttribute('aria-label')}));
 await page.unroute('**/api/alerts?*');
 await page.route('**/api/alerts?*',r=>r.fulfill({status:503,json:{error:'audit outage'}}));
 await page.reload();await page.waitForTimeout(1200);
 console.log('alerts_outage',JSON.stringify({text:await page.locator('[aria-label="Alert history"]').innerText(),header:await page.locator('.updated').innerText()}));
 } finally {await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
