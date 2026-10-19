const { chromium } = require('playwright');
const BASE=process.env.BASE_URL||'http://127.0.0.1:5055';
const EXE=process.env.CHROME_PATH||'/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
(async()=>{
 const b=await chromium.launch({executablePath:EXE});
 const fails=[];const ok=(l,c,x='')=>{console.log((c?'  PASS  ':'  FAIL  ')+l+(c?'':'\n          '+x));if(!c)fails.push(l)};

 // ---------- signed-in user
 const p=await b.newPage({viewport:{width:1500,height:1000}});
 const errs=[];p.on('pageerror',e=>errs.push(e.message));
 await p.goto(BASE+'/',{waitUntil:'networkidle'});
 const u=Date.now();
 await p.click('#atReg');await p.fill('#rgUser','f'+u);await p.fill('#rgEmail',`f${u}@t.com`);await p.fill('#rgPass','secret123');
 await p.click('#fReg button.auth-go');await p.waitForTimeout(2500);

 await p.click('.nav-item[data-v="portfolio"]');
 const add=async(t,q,e,s)=>{await p.fill('#pfTicker',t);await p.fill('#pfQty',String(q));await p.fill('#pfEntry',String(e));
  await p.fill('#pfStop',s?String(s):'');await p.click('button[onclick="addPosition()"]');await p.waitForTimeout(900)};
 await add('NVDA',50,200,null);await add('AAPL',30,150,140);await add('TSLA',20,300,295);
 ok('portfolio lists three positions',(await p.$$eval('#pfBody tr',r=>r.length))===3);
 ok('a position without a stop is flagged',(await p.$eval('#pfBody',e=>e.innerText)).includes('no stop'));
 await p.evaluate(async()=>{await store.addWatch('AMD');await store.addWatch('MSFT')});

 await p.click('.nav-item[data-v="command"]');await p.waitForTimeout(400);
 await p.click('button[onclick="toggleSettingsPanel()"]');
 await p.fill('#setEquity','100000');await p.fill('#setRisk','1');
 await p.click('button[onclick="saveSettings()"]');await p.waitForTimeout(3500);
 await p.waitForSelector('#ccActions .act',{timeout:25000});
 const acts=await p.$$eval('#ccActions .act',e=>e.map(x=>x.innerText.replace(/\s+/g,' ').slice(0,70)));
 console.log('  actions:');acts.forEach(a=>console.log('    '+a));
 ok('action feed is populated',acts.length>0);
 ok('the naked position is called out',acts.some(a=>/No stop/i.test(a)),JSON.stringify(acts));
 ok('severity words are English',(await p.$$eval('.sev-pill',e=>e.map(x=>x.textContent))).every(t=>/Critical|Urgent|Review|Note/.test(t)));
 ok('risk table lists every position',(await p.$$eval('#ccRisk tr',r=>r.length))===3);
 ok('entry cards render',(await p.$$eval('.ent',e=>e.length))>0);
 ok('entries are sized from the account',(await p.$eval('#ccEntryGrid',e=>e.innerText)).includes('shares'));

 // one-click stop
 const card=p.locator('#ccActions .act',{hasText:'No stop'}).first();
 await card.locator('button.btn-gold').click();await p.waitForTimeout(3500);
 ok('one-click stop protects the position',(await p.$eval('#ccUnprot',e=>e.textContent))==='0');

 // inline edit + guard
 const row=t=>p.locator('#ccRisk tr',{hasText:t}).first();
 p.once('dialog',d=>d.dismiss());
 const price=Number((await row('NVDA').locator('td').nth(2).innerText()).replace(/[$,]/g,''));
 const inp=row('NVDA').locator('input.stop-inp');
 await inp.fill(String(Math.round(price*1.2)));await inp.dispatchEvent('change');await p.waitForTimeout(1200);
 ok('a stop above price is confirmed and reverts on cancel',
   Number(await row('NVDA').locator('input.stop-inp').inputValue())!==Math.round(price*1.2));
 const want=Math.round(price*0.9);
 await inp.fill(String(want));await inp.dispatchEvent('change');await p.waitForTimeout(3000);
 ok('inline stop edit persists',Number(await row('NVDA').locator('input.stop-inp').inputValue())===want);
 await row('NVDA').locator('.seg button',{hasText:'Trail'}).click();await p.waitForTimeout(3000);
 ok('switching to a trailing stop sticks',
   await row('NVDA').locator('.seg button',{hasText:'Trail'}).evaluate(e=>e.classList.contains('on')));

 // backtest
 await p.click('.nav-item[data-v="backtest"]');await p.waitForTimeout(400);
 await p.fill('#btTicker','NVDA');await p.click('button[onclick="runBacktest()"]');
 await p.waitForSelector('.bt-stats',{timeout:30000});await p.waitForTimeout(1500);
 const bt=await p.$$eval('.bt-stat',e=>e.map(x=>x.innerText.replace(/\n/g,' ')));
 console.log('  backtest:',JSON.stringify(bt));
 ok('backtest reports stats',bt.length===5);
 ok('backtest compares against buy and hold',(await p.$eval('.bt-vs',e=>e.innerText)).includes('Buy and hold'));

 // news
 await p.click('.nav-item[data-v="news"]');await p.waitForSelector('.news-item',{timeout:25000});
 ok('news renders',(await p.$$eval('.news-item',e=>e.length))>0);
 ok('quiet sources are disclosed',(await p.$eval('#newsFailed',e=>e.innerText)).includes('not responding'));

 // reload persistence
 await p.reload({waitUntil:'networkidle'});await p.waitForTimeout(3000);
 await p.click('.nav-item[data-v="command"]');await p.waitForTimeout(4000);
 ok('stops survive a reload',Number(await row('NVDA').locator('input.stop-inp').inputValue())===want);
 ok('risk settings survive a reload',(await p.$eval('#setEquity',e=>e.value))==='100000');

 // mobile
 await p.setViewportSize({width:390,height:844});await p.waitForTimeout(900);
 const of=await p.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
 ok('no horizontal overflow on a phone',of<=2,'overflow='+of+'px');
 ok('no javascript errors (signed in)',errs.length===0,errs.slice(0,4).join('\n'));

 // ---------- guest, separate browser context
 const ctx=await b.newContext({viewport:{width:1400,height:950}});
 const g=await ctx.newPage();const gerrs=[];g.on('pageerror',e=>gerrs.push(e.message));
 await g.goto(BASE+'/',{waitUntil:'networkidle'});
 await g.click('button.auth-guest');await g.waitForTimeout(1500);
 ok('a guest sees no other account data',(await g.$eval('#pfBody',e=>e.innerText)).includes('No positions'),
   await g.$eval('#pfBody',e=>e.innerText));
 await g.click('.nav-item[data-v="portfolio"]');
 await g.fill('#pfTicker','NVDA');await g.fill('#pfQty','25');await g.fill('#pfEntry','110');
 await g.click('button[onclick="addPosition()"]');await g.waitForTimeout(1200);
 await g.evaluate(async()=>{await store.addWatch('AMD')});
 await g.click('.nav-item[data-v="command"]');await g.waitForSelector('#ccActions .act',{timeout:25000});
 ok('guest gets a plan',(await g.$$eval('#ccActions .act',e=>e.length))>0);
 const stored=await g.evaluate(()=>JSON.parse(localStorage.getItem('js_pf')||'[]'));
 ok('guest data stays in the browser',stored.length===1&&stored[0].ticker==='NVDA',JSON.stringify(stored));
 ok('no javascript errors (guest)',gerrs.length===0,gerrs.slice(0,4).join('\n'));

 await b.close();
 console.log('\n'+(fails.length?fails.length+' FAILED: '+fails.join(', '):'ALL FLOW CHECKS PASS'));
 process.exit(fails.length?1:0);
})();
