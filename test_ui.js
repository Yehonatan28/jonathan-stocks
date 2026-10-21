const { chromium } = require('playwright');
const BASE=process.env.BASE_URL||'http://127.0.0.1:5055';
const EXE=process.env.CHROME_PATH||'/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const OUT='/tmp/claude-0/-home-user-jonathan-stocks/c7fb86cc-eb29-51d7-bc2d-9dbf7ef204b8/scratchpad';
(async()=>{
 const b=await chromium.launch({executablePath:EXE});
 const p=await b.newPage({viewport:{width:1500,height:1000}});
 const errs=[];p.on('pageerror',e=>errs.push('PAGEERROR '+e.message));
 p.on('console',m=>{if(m.type()==='error'&&!/TUNNEL|CERT|ERR_NAME|ERR_INTERNET|401|404|favicon|clearbit|fonts\.|unpkg|jsdelivr/i.test(m.text()))errs.push('CONSOLE '+m.text())});
 const fails=[];const ok=(l,c,x='')=>{console.log((c?'  PASS  ':'  FAIL  ')+l+(c?'':'\n          '+x));if(!c)fails.push(l)};

 // charting libs are CDN-blocked here; record what the chart asks to draw
 await p.addInitScript(()=>{
  window.__draw={lines:[],priceLines:[],markers:[],points:0,type:null,opts:null};
  /* main=true only for the price series; overlay lines must not overwrite it */
  const series=(kind,main)=>({setData:d=>{if(main){window.__draw.points=d.length;window.__draw.type=kind}},
    createPriceLine:o=>window.__draw.priceLines.push(o),setMarkers:m=>window.__draw.markers.push(...m)});
  window.LightweightCharts={createChart:(el,o)=>{
    /* each render is a fresh chart; stale state would mask the series type */
    window.__draw={lines:[],priceLines:[],markers:[],points:0,type:null,opts:o};
    return{
    addCandlestickSeries:()=>series('candles',true),addLineSeries:o=>{window.__draw.lines.push(o.color);return series('line',window.__draw.type===null)},
    addAreaSeries:()=>series('area',true),addHistogramSeries:()=>({setData:()=>{}}),
    priceScale:()=>({applyOptions:()=>{}}),timeScale:()=>({fitContent:()=>{}}),
    subscribeCrosshairMove:f=>{window.__cross=f},applyOptions:()=>{},remove:()=>{}}}};
 });

 await p.goto(BASE+'/',{waitUntil:'networkidle'});
 const u=Date.now();
 await p.click('#atReg');await p.fill('#rgUser','t'+u);await p.fill('#rgEmail',`t${u}@t.com`);await p.fill('#rgPass','secret123');
 await p.click('#fReg button.auth-go');await p.waitForTimeout(3000);

 // --- language
 const htmlAttrs=await p.evaluate(()=>[document.documentElement.lang,document.documentElement.dir]);
 ok('page is English and LTR',htmlAttrs[0]==='en'&&htmlAttrs[1]==='ltr',JSON.stringify(htmlAttrs));
 const hebOutsideGloss=await p.evaluate(()=>{
  const g=document.getElementById('gloss');
  const walk=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  const hits=[];let n;
  while(n=walk.nextNode()){ if(g&&g.contains(n))continue;
   const tag=n.parentElement&&n.parentElement.tagName;
   if(tag==='SCRIPT'||tag==='STYLE')continue;   /* source, not visible text */
   if(/[֐-׿]/.test(n.nodeValue))hits.push(n.nodeValue.trim().slice(0,40))}
  return hits});
 ok('no Hebrew outside the glossary',hebOutsideGloss.length===0,JSON.stringify(hebOutsideGloss.slice(0,5)));
 await p.click('button[onclick="toggleGloss()"]');await p.waitForTimeout(400);
 const gl=await p.$eval('#glBody',e=>e.innerText);
 ok('glossary keeps Hebrew explanations',/[֐-׿]/.test(gl));
 ok('glossary terms stay in English',gl.includes('Chandelier Exit')&&gl.includes('R Multiple'),gl.slice(0,80));
 ok('glossary covers the new concepts',gl.includes('Gap Fill')&&gl.includes('Trend Template'));
 await p.click('#gloss .x-btn');await p.waitForTimeout(300);

 // --- Fear & Greed
 ok('fear & greed gauge renders',await p.$('.fg-dial')!==null);
 const fgTxt=await p.$eval('#fgWrap',e=>e.innerText);
 ok('gauge shows score and rating',/38/.test(fgTxt)&&/Fear/.test(fgTxt),fgTxt.slice(0,60));
 ok('gauge shows the previous comparisons',/PREV CLOSE/i.test(fgTxt)&&/1 YEAR/i.test(fgTxt));
 ok('gauge lists CNN components',(await p.$$eval('.fg-comp',e=>e.length))===7,await p.$$eval('.fg-comp',e=>e.length));
 ok('header chip mirrors the index',(await p.$eval('#fgChip',e=>e.textContent)).includes('38'));

 // --- heatmap
 await p.click('.nav-item[data-v="heatmap"]');
 await p.waitForSelector('.hm-cell',{timeout:25000});await p.waitForTimeout(1800);
 const geo=await p.evaluate(()=>{
  const board=document.getElementById('hmBoard');const br=board.getBoundingClientRect();
  let outside=0,overlapOk=true;
  document.querySelectorAll('.hm-cell').forEach(c=>{const r=c.getBoundingClientRect();
   if(r.left<br.left-2||r.right>br.right+2||r.top<br.top-2||r.bottom>br.bottom+2)outside++});
  const sizes=[...document.querySelectorAll('.hm-cell')].map(c=>c.getBoundingClientRect().width*c.getBoundingClientRect().height);
  return{cells:document.querySelectorAll('.hm-cell').length,outside,
   zero:sizes.filter(s=>s<1).length,board:[br.width,br.height]}});
 ok('the whole S&P 500 is on the map',geo.cells>480,JSON.stringify(geo));
 ok('no block escapes the board',geo.outside===0,'outside='+geo.outside);
 ok('no zero-size blocks',geo.zero===0,'zero='+geo.zero);
 ok('all 11 sectors are grouped',(await p.$$eval('.hm-sector',e=>e.length))===11);
 const big=await p.evaluate(()=>{const c=[...document.querySelectorAll('.hm-cell')]
   .sort((a,b)=>b.getBoundingClientRect().width*b.getBoundingClientRect().height-a.getBoundingClientRect().width*a.getBoundingClientRect().height)[0];
  return c.innerText});
 ok('large blocks show symbol, name and change',/NVDA/.test(big)&&/%/.test(big),JSON.stringify(big));
 // tooltip
 await p.hover('.hm-cell');await p.waitForTimeout(400);
 ok('hovering a block shows a tooltip',await p.$eval('#hmTip',e=>e.classList.contains('on')));
 const tip=await p.$eval('#hmTip',e=>e.innerText);
 ok('tooltip carries price, change, cap and sector',/Price/.test(tip)&&/Market cap/.test(tip)&&/Sector/.test(tip),tip);
 await p.click('.hm-bar .btn[data-idx="ndx"]');await p.waitForTimeout(3000);
 const ndxCount=await p.$$eval('.hm-cell',e=>e.length);
 ok('Nasdaq 100 shows about a hundred names',ndxCount>=95&&ndxCount<=101,'cells='+ndxCount);
 await p.click('.hm-bar .btn[data-idx="sp500"]');await p.waitForTimeout(3500);

 // --- gap detector
 await p.click('.nav-item[data-v="gaps"]');
 await p.waitForSelector('.gap-row',{timeout:30000});await p.waitForTimeout(1200);
 const gapRows=await p.$$eval('.gap-row',e=>e.length);
 ok('gap detector lists gaps',gapRows>0,'rows='+gapRows);
 ok('gap tiles summarise up, down and unfilled',
   /gap up[\s\S]*gap down[\s\S]*still unfilled/i.test(await p.$eval('#gapTiles',e=>e.innerText)),
   await p.$eval('#gapTiles',e=>e.innerText.replace(/\n/g,' | ')));
 const row1=await p.$eval('.gap-row',e=>e.innerText.replace(/\n/g,' '));
 ok('a gap row shows prev close, open, fill level and ATR size',
   /prev close/.test(row1)&&/fills at/.test(row1)&&/ATR/.test(row1),row1);
 ok('each gap is labelled filled or unfilled',
   (await p.$$eval('.gap-badge.open,.gap-badge.filled',e=>e.length))===gapRows);
 await p.click('#gapScopes .seg button[data-f="up"]');await p.waitForTimeout(700);
 const ups=await p.$$eval('.gap-row',e=>e.map(x=>x.className));
 ok('filtering to gap up hides the down gaps',ups.every(c=>c.includes('up')&&!c.includes('down')),JSON.stringify(ups.slice(0,3)));
 await p.click('#gapScopes .seg button[data-f="open"]');await p.waitForTimeout(700);
 ok('filtering to unfilled hides the filled ones',
   (await p.$$eval('.gap-badge.filled',e=>e.length))===0);
 await p.click('#gapScopes .seg button[data-f="all"]');await p.waitForTimeout(700);

 // --- chart
 await p.evaluate(()=>openChart('NVDA'));await p.waitForTimeout(4500);
 let d=await p.evaluate(()=>window.__draw);
 ok('chart draws candles by default',d.type==='candles'&&d.points>0,JSON.stringify({t:d.type,p:d.points}));
 ok('MA50 and MA200 are on by default',d.lines.includes('#e5b048')&&d.lines.includes('#a78bfa'),JSON.stringify(d.lines));
 ok('MA100 and MA150 exist as toggles',(await p.$$('.ind[data-ind="ma100"],.ind[data-ind="ma150"]')).length===2);
 await p.click('.ind[data-ind="ma100"]');await p.waitForTimeout(800);
 d=await p.evaluate(()=>window.__draw);
 ok('turning on MA100 draws it',d.lines.includes('#22d3ee'),JSON.stringify(d.lines));
 ok('MA20 is no longer offered',(await p.$$('.ind[data-ind="ma20"]')).length===0);
 ok('trade levels are drawn',d.priceLines.length>0,JSON.stringify(d.priceLines.map(l=>l.title)));
 const legend=await p.$eval('#chLegend',e=>e.innerText.replace(/\n/g,' '));
 ok('crosshair legend shows OHLC',/O/.test(legend)&&/H/.test(legend)&&/L/.test(legend)&&/C/.test(legend)&&/Vol/.test(legend),legend);
 await p.click('.ind[data-ind="line"]');await p.waitForTimeout(900);
 d=await p.evaluate(()=>window.__draw);
 ok('switching to a line chart works',d.type==='line',d.type);
 await p.click('.ind[data-ind="candles"]');await p.waitForTimeout(700);
 await p.click('.ind[data-ind="bb"]');await p.waitForTimeout(900);
 d=await p.evaluate(()=>window.__draw);
 ok('Bollinger bands add two lines',d.lines.filter(c=>/62,166,255/.test(c)).length===2,JSON.stringify(d.lines));
 await p.click('.ind[data-ind="log"]');await p.waitForTimeout(900);
 d=await p.evaluate(()=>window.__draw);
 ok('log scale reaches the chart options',d.opts.rightPriceScale.mode===1,JSON.stringify(d.opts.rightPriceScale));
 await p.keyboard.press('f');await p.waitForTimeout(500);
 ok('F toggles fullscreen',await p.$eval('#chartShell',e=>e.classList.contains('full')));
 await p.keyboard.press('Escape');await p.waitForTimeout(500);
 ok('Escape closes the chart',!(await p.$eval('#chartModal',e=>e.classList.contains('open'))));

 ok('no javascript errors',errs.length===0,errs.slice(0,6).join('\n'));
 await p.screenshot({path:OUT+'/en-final.png',fullPage:false});
 await b.close();
 console.log('\n'+(fails.length?fails.length+' FAILED: '+fails.join(', '):'ALL UI CHECKS PASS'));
 process.exit(fails.length?1:0);
})();
