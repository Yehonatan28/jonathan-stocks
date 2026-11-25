const { chromium } = require('playwright');
const B='http://127.0.0.1:5055/';
const res=[]; const ok=(name,cond,info='')=>{res.push(`${cond?'PASS':'FAIL'}  ${name}${info?'  ('+info+')':''}`)};
(async () => {
  const b = await chromium.launch();
  // 1. guest -> search -> research -> compare -> watchlist
  { const p = await b.newPage({viewport:{width:1280,height:900}}); const errs=[]; p.on('pageerror',e=>errs.push(e.message));
    await p.goto(B+'#/home'); await p.waitForTimeout(1500);
    ok('1a guest lands without a sign-in gate', await p.evaluate(()=>document.getElementById('authOverlay').classList.contains('hidden')));
    await p.keyboard.press('Control+k'); await p.keyboard.type('micro'); await p.waitForTimeout(900);
    ok('1b search finds Microsoft', (await p.textContent('#gsList')).includes('MSFT'));
    await p.keyboard.press('Enter'); await p.waitForTimeout(2500);
    ok('1c Enter opens research', (await p.evaluate(()=>location.hash))==='#/research?t=MSFT' && (await p.textContent('#v-research')).includes('SEC'));
    await p.click('.ph-tabs a:has-text("Compare")'); await p.waitForTimeout(3000);
    ok('1d symbol carried into Compare, benchmark added', (await p.inputValue('#relInput'))==='MSFT, SPY', await p.inputValue('#relInput'));
    await p.keyboard.press('Control+k'); await p.keyboard.type('MSFT'); await p.waitForTimeout(900);
    await p.click('#gsActs [data-act=watch]'); await p.waitForTimeout(600);
    ok('1e added to the watchlist from search', await p.evaluate(()=>JSON.stringify(S.watch).includes('MSFT')));
    ok('1f no script errors', !errs.length, errs.join('|')); await p.close(); }
  // 2. filter -> open result -> back with filters kept
  { const p = await b.newPage({viewport:{width:1280,height:900}});
    await p.goto(B+'#/screener'); await p.waitForTimeout(2500);
    await p.click('#scrFiltersBox summary'); await p.fill('[data-k=pe][data-i="1"]','25'); await p.dispatchEvent('[data-k=pe][data-i="1"]','change'); await p.waitForTimeout(400);
    const n1=await p.textContent('#scrCount');
    await p.click('#scrTable tbody tr'); await p.waitForTimeout(1500);
    await p.keyboard.press('Escape'); await p.waitForTimeout(300);
    await p.goto(B+'#/research?t=AAPL'); await p.waitForTimeout(1500); await p.goBack(); await p.waitForTimeout(1500);
    const n2=await p.textContent('#scrCount');
    ok('2 filters kept after opening a result and going back', n1.split(' match')[0]===n2.split(' match')[0] && /P\/E/.test(await p.textContent('#scrChips')), n1.split('·')[0]+' / '+n2.split('·')[0]); await p.close(); }
  // 3. empty and test portfolio -> risk and alerts (isolated browser storage)
  { const p = await b.newPage({viewport:{width:1280,height:900}});
    await p.goto(B+'#/command'); await p.waitForTimeout(2500);
    ok('3a empty portfolio says nothing was checked', (await p.textContent('#ccBrief')).includes('No positions to check'));
    await p.goto(B+'#/risk'); await p.waitForTimeout(1500);
    ok('3b empty risk screen is not a clean result', /No holdings|No positions/.test(await p.textContent('#rkBody')));
    await p.evaluate(()=>localStorage.setItem('js_pf',JSON.stringify([{id:1,ticker:'MSFT',qty:10,entry:300,stop:null},{id:2,ticker:'AAPL',qty:20,entry:150,stop:140}])));
    await p.reload(); await p.waitForTimeout(1000); await p.evaluate(()=>{location.hash='#/command'}); await p.waitForTimeout(3000);
    const brief=await p.textContent('#ccBrief');
    ok('3c test portfolio: missing stop reported as a condition', /without a recorded stop|condition/.test(brief), brief.slice(0,80));
    await p.evaluate(()=>{location.hash='#/risk'}); await p.waitForTimeout(2500);
    ok('3d risk lists limit breaches first', (await p.textContent('#rkBody')).includes('Limit breaches'));
    await p.evaluate(()=>{location.hash='#/alertsx'}); await p.waitForTimeout(1200);
    await p.fill('#alxForm [name=ticker]','MSFT'); await p.click('#alxForm [type=submit]'); await p.waitForTimeout(1500);
    ok('3e alert created with its limitation beside it', (await p.textContent('#alxList')).includes('MSFT') && (await p.isVisible('#alxLimit'))); await p.close(); }
  // 4. backtest -> change params -> updated result
  { const p = await b.newPage({viewport:{width:1280,height:900}});
    await p.goto(B+'#/lab?t=MSFT'); await p.waitForTimeout(1000);
    await p.selectOption('#labPreset','Trend pullback');
    await p.click('#labForm [type=submit]'); await p.waitForTimeout(2500); const r1=await p.textContent('#labOut .mi-tiles');
    await p.fill('[name=commission_bps]','50'); await p.click('#labForm [type=submit]'); await p.waitForTimeout(2500); const r2=await p.textContent('#labOut .mi-tiles');
    ok('4 changing costs changes the result and the stated assumption', r1!==r2 && (await p.textContent('.lab-asm')).includes('50 bp')); await p.close(); }
  // 5. provider failure, missing data, Hebrew, keyboard, narrow screen
  { const p = await b.newPage({viewport:{width:360,height:800}});
    await p.route('**/api/market/breadth*', r=>r.fulfill({status:503, body:'{"error":"down"}', contentType:'application/json'}));
    await p.goto(B+'#/home'); await p.waitForTimeout(2500);
    const t=await p.textContent('#brTiles');
    ok('5a provider failure: unavailable with Retry, no zeros', /Unavailable/.test(t) && await p.isVisible('#brTiles .mi-retry') && !/\b0\.0%/.test(t));
    ok('5b narrow screen: no horizontal scroll', await p.evaluate(()=>document.documentElement.scrollWidth<=360));
    await p.evaluate(()=>localStorage.setItem('js.lang','he')); await p.reload(); await p.waitForTimeout(2000);
    ok('5c Hebrew: rtl and translated header', await p.evaluate(()=>document.documentElement.dir==='rtl') && (await p.textContent('#pageTitle'))==='סקירת שוק');
    await p.close(); }
  { const p = await b.newPage({viewport:{width:1280,height:900}});
    await p.goto(B+'#/home'); await p.waitForTimeout(1500);
    await p.keyboard.press('Tab'); const first=await p.evaluate(()=>document.activeElement.className);
    await p.keyboard.press('Enter'); await p.waitForTimeout(200);
    ok('5d keyboard: first Tab is the skip link and it moves focus to the content', first.includes('skip') && await p.evaluate(()=>document.activeElement.id==='content'));
    await p.keyboard.press('Control+k'); await p.keyboard.press('Escape'); await p.waitForTimeout(200);
    ok('5e search closes on Escape', await p.evaluate(()=>document.getElementById('gsearch').hidden));
    await p.close(); }
  console.log(res.join('\n')); await b.close();
})();
