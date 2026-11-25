'use strict';
/* ===================== state ===================== */
const S={user:null,guest:false,watch:[],alerts:[],pf:[],cache:{},
 chart:{tkr:null,period:'6mo',type:'candles',lw:null,series:null,rsiC:null,macdC:null,data:null,levels:null,full:false},
 cmdkSel:0,plan:null,settings:null,bt:null,hm:null,notified:new Set(),newsScope:'all'};
const PRESETS={us:['AAPL','MSFT','NVDA','GOOGL','AMZN','META','TSLA','JPM','V','UNH'],
 il:['TEVA.TA','NICE.TA','CHKP.TA','ESLT.TA','POLI.TA','LUMI.TA','ICL.TA'],
 tech:['NVDA','AMD','AVGO','PLTR','CRM','ORCL','SMCI','ARM'],
 etf:['SPY','QQQ','DIA','IWM','GLD','TLT','XLE','XLF'],
 all:['AAPL','MSFT','NVDA','GOOGL','AMZN','META','TSLA','TEVA.TA','NICE.TA','CHKP.TA','SPY','QQQ']};
const TAPE=['AAPL','TSLA','NVDA','MSFT','GOOGL','AMZN','META','SPY','QQQ','TEVA.TA','NICE.TA','CHKP.TA'];
const IDX_US=[['^GSPC','S&P 500'],['^IXIC','Nasdaq'],['^DJI','Dow Jones'],['^RUT','Russell 2000'],['^VIX','VIX']];
const IDX_IL=[['^TA125.TA','TA-125'],['^TA35.TA','TA-35'],['^TA90.TA','TA-90'],['TEVA.TA','Teva'],['LUMI.TA','Leumi'],['POLI.TA','Hapoalim']];
const $=id=>document.getElementById(id);
/* Third-party text (headlines, company names) reaches innerHTML, so it is escaped. */
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(n,d=2)=>n==null||isNaN(n)?'—':Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
const fmtCap=n=>{if(n==null)return'—';const a=Math.abs(n);
 if(a>=1e12)return '$'+fmt(n/1e12)+'T';if(a>=1e9)return '$'+fmt(n/1e9)+'B';
 if(a>=1e6)return '$'+fmt(n/1e6)+'M';return '$'+fmt(n)};
const sign=(v,d=2)=>v==null?'—':(v>=0?'+':'')+fmt(v,d);
const cls=v=>v==null?'':v>=0?'up':'dn';
const api=async(url,opt)=>{const r=await fetch(url,{headers:{'Content-Type':'application/json'},...opt});
 if(window.noteProv)window.noteProv(r);
 let j={};try{j=await r.json()}catch(e){j={error:'The server returned an unexpected response.'}}
 if(!r.ok){if(r.status===404&&!j.error)j.error='Endpoint not found on the server.';throw j}return j};
function toast(msg,type='info'){const t=document.createElement('div');t.className='toast '+type;t.textContent=msg;
 $('toasts').appendChild(t);setTimeout(()=>{t.style.opacity='0';t.style.transition='.4s';setTimeout(()=>t.remove(),400)},4200)}

/* ===================== auth ===================== */
function switchAuthTab(tab){const l=tab==='login';$('atLogin').classList.toggle('on',l);$('atReg').classList.toggle('on',!l);
 $('fLogin').style.display=l?'':'none';$('fReg').style.display=l?'none':''}
function showAuth(){$('authOverlay').classList.remove('hidden')}
function guestMode(){S.guest=true;$('authOverlay').classList.add('hidden');
 toast('Guest mode — your data stays in this browser only','info');loadUserData()}
async function doLogin(){$('liErr').textContent='';
 try{const j=await api('/api/auth/login',{method:'POST',body:JSON.stringify({email:$('liEmail').value,password:$('liPass').value})});onAuthed(j.username)}
 catch(e){$('liErr').textContent=e.error||'Could not sign in. Try again.'}}
async function doRegister(){$('rgErr').textContent='';
 try{const j=await api('/api/auth/register',{method:'POST',body:JSON.stringify({username:$('rgUser').value,email:$('rgEmail').value,password:$('rgPass').value})});
  onAuthed(j.username);toast('Welcome — your account is ready','ok')}
 catch(e){$('rgErr').textContent=e.error||'Could not create the account.'}}
function onAuthed(name){S.user=name;S.guest=false;$('authOverlay').classList.add('hidden');
 $('userPill').style.display='flex';$('userName').textContent=name;$('userAv').textContent=(name[0]||'?').toUpperCase();
 $('loginBtn').style.display='none';loadUserData()}
async function doLogout(){try{await api('/api/auth/logout',{method:'POST'})}catch(e){}
 S.user=null;S.pf=[];S.watch=[];S.plan=null;$('userPill').style.display='none';$('loginBtn').style.display='';showAuth()}
async function checkAuth(){try{const j=await api('/api/auth/me');onAuthed(j.username)}catch(e){showAuth()}}

/* ===================== storage: server when signed in, browser as guest ===================== */
const store={
 async getWatch(){if(S.user)return api('/api/watchlist');return JSON.parse(localStorage.getItem('js_watch')||'[]')},
 async addWatch(t){if(S.user)return api('/api/watchlist/'+t,{method:'POST'});const w=await this.getWatch();if(!w.includes(t))w.push(t);localStorage.setItem('js_watch',JSON.stringify(w))},
 async delWatch(t){if(S.user)return api('/api/watchlist/'+t,{method:'DELETE'});localStorage.setItem('js_watch',JSON.stringify((await this.getWatch()).filter(x=>x!==t)))},
 async getPf(){if(S.user)return api('/api/portfolio');return JSON.parse(localStorage.getItem('js_pf')||'[]')},
 async addPf(p){if(S.user)return api('/api/portfolio',{method:'POST',body:JSON.stringify(p)});
  const a=await this.getPf();p.id=Date.now();a.push(p);localStorage.setItem('js_pf',JSON.stringify(a));return p},
 async delPf(id){if(S.user)return api('/api/portfolio/'+id,{method:'DELETE'});
  localStorage.setItem('js_pf',JSON.stringify((await this.getPf()).filter(x=>String(x.id)!==String(id))))},
 async patchPf(id,patch){if(S.user)return api('/api/portfolio/'+id,{method:'PATCH',body:JSON.stringify(patch)});
  const a=await this.getPf();const p=a.find(x=>String(x.id)===String(id));if(!p)throw{error:'Position not found'};
  if(patch.stop!=null&&p.init_stop==null)p.init_stop=patch.stop;  /* first stop = the risk every R is measured against */
  Object.assign(p,patch);localStorage.setItem('js_pf',JSON.stringify(a));return p},
 async getAlerts(){if(S.user)return api('/api/alerts');return JSON.parse(localStorage.getItem('js_al')||'[]')},
 async addAlert(a){if(S.user)return api('/api/alerts',{method:'POST',body:JSON.stringify(a)});
  const l=await this.getAlerts();a.id=Date.now();l.push(a);localStorage.setItem('js_al',JSON.stringify(l));return a},
 async delAlert(id){if(S.user)return api('/api/alerts/'+id,{method:'DELETE'});
  localStorage.setItem('js_al',JSON.stringify((await this.getAlerts()).filter(x=>String(x.id)!==String(id))))},
 async getSettings(){if(S.user)return api('/api/settings');return JSON.parse(localStorage.getItem('js_set')||'{"equity":0,"risk_pct":1,"trail_mult":null}')},
 async saveSettings(s){if(S.user)return api('/api/settings',{method:'POST',body:JSON.stringify(s)});localStorage.setItem('js_set',JSON.stringify(s));return s},
};
async function loadUserData(){S.watch=await store.getWatch().catch(()=>[]);S.alerts=await store.getAlerts().catch(()=>[]);
 await loadSettings();renderWatch();renderAlerts();loadPortfolio();loadPlan(true)}

/* ===================== navigation ===================== */
const VIEWS=['home','command','heatmap','gaps','backtest','portfolio','watchlist','news','compare','alerts'];
function go(v){document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('on',n.dataset.v===v));
 document.querySelectorAll('.view').forEach(x=>x.classList.remove('on'));
 const el=$('v-'+v);if(!el)return;el.classList.add('on');window.scrollTo({top:0,behavior:'instant'});
 if(v==='heatmap'&&!S.hm)loadHeatmap('sp500',document.querySelector('.hm-bar .btn'));
 if(v==='gaps'&&!S.gaps)loadGaps('sp100',document.querySelector('#gapScopes .btn'));
 if(v==='news'&&!S._newsLoaded){S._newsLoaded=1;loadNews('all',document.querySelector('#newsScopes .btn'))}
 if(v==='watchlist')renderWatch();if(v==='portfolio')loadPortfolio();if(v==='command')loadPlan(!S.plan)}

function tickClock(){const now=new Date();$('clockChip').textContent=now.toLocaleTimeString('en-GB');
 const ny=new Date(now.toLocaleString('en-US',{timeZone:'America/New_York'}));
 const d=ny.getDay(),m=ny.getHours()*60+ny.getMinutes();const open=d>=1&&d<=5&&m>=570&&m<960;
 const c=$('mktChip');c.className='chip '+(open?'mkt-open':'mkt-closed');
 $('mktTxt').textContent=open?'US market open':'US market closed'}

function sparkline(canvas,data,color){if(!canvas||!data||data.length<2)return;
 const dpr=window.devicePixelRatio||1;const w=canvas.clientWidth||canvas.parentElement.clientWidth,h=+canvas.getAttribute('height')||52;
 canvas.width=w*dpr;canvas.height=h*dpr;const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);
 const min=Math.min(...data),max=Math.max(...data),rng=(max-min)||1;
 const pts=data.map((v,i)=>[i/(data.length-1)*w,h-4-((v-min)/rng)*(h-10)]);
 ctx.beginPath();pts.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));
 ctx.strokeStyle=color;ctx.lineWidth=2;ctx.lineJoin='round';ctx.stroke();
 const g=ctx.createLinearGradient(0,0,0,h);g.addColorStop(0,color.replace('rgb','rgba').replace(')',',.18)'));
 g.addColorStop(1,'rgba(255,255,255,0)');ctx.lineTo(w,h);ctx.lineTo(0,h);ctx.closePath();ctx.fillStyle=g;ctx.fill()}
/* ===================== Fear & Greed (CNN) ===================== */
/* CNN's own band colours and boundaries, so a score reads the same here as
   it does on their page. */
const FG_BANDS=[[0,25,'#e5566c','Extreme Fear'],[25,45,'#e08b45','Fear'],
 [45,55,'#c9b945','Neutral'],[55,75,'#7eb356','Greed'],[75,100,'#3f9a4e','Extreme Greed']];
const fgColor=v=>(FG_BANDS.find(b=>v>=b[0]&&v<b[1])||FG_BANDS[4])[2];
const fgLabel=v=>(FG_BANDS.find(b=>v>=b[0]&&v<b[1])||FG_BANDS[4])[3];

/* Polar helpers for a 180-degree dial: 0 at the left, 100 at the right. */
function fgPoint(cx,cy,r,v){const a=Math.PI*(1-v/100);return[cx+r*Math.cos(a),cy-r*Math.sin(a)]}
function fgArc(cx,cy,r,from,to){const[x1,y1]=fgPoint(cx,cy,r,from),[x2,y2]=fgPoint(cx,cy,r,to);
 return `M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}`}

async function loadFearGreed(){
 const box=$('fgWrap');
 try{
  const d=await api('/api/feargreed');
  if(!d.ok){box.innerHTML=`<div class="empty" style="padding:22px"><div class="e-ic">📉</div><h4>Fear &amp; Greed unavailable</h4><div style="font-size:11.5px;line-height:1.6">${esc(d.error||'')}<br>Showing nothing is better than showing a number we invented.</div></div>`;
   $('fgChip').textContent='F&G —';return}
  S.fg=d;renderFearGreed(d);
 }catch(e){box.innerHTML='<div class="empty" style="padding:22px"><h4>Fear &amp; Greed unavailable</h4></div>'}}

function renderFearGreed(d){
 const v=Math.max(0,Math.min(100,d.score)),col=fgColor(v),label=d.rating||fgLabel(v);
 const cx=120,cy=112,r=88,W=14;
 const bands=FG_BANDS.map(([a,b,c])=>
  `<path d="${fgArc(cx,cy,r,a,b)}" fill="none" stroke="${c}" stroke-width="${W}" stroke-linecap="butt" opacity=".92"/>`).join('');
 /* Tick marks at each band boundary, as on CNN's dial. */
 const ticks=[0,25,45,55,75,100].map(t=>{const[x1,y1]=fgPoint(cx,cy,r-W/2-2,t),[x2,y2]=fgPoint(cx,cy,r+W/2+2,t);
  return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#080b12" stroke-width="2"/>`}).join('');
 const[nx,ny]=fgPoint(cx,cy,r-20,v);
 const prev=d.previous||{};
 const cell=(lab,val)=>`<div><i>${lab}</i><b style="color:${val==null?'var(--tx3)':fgColor(val)}">${val==null?'—':val}</b></div>`;
 $('fgWrap').innerHTML=`
  <svg class="fg-dial" viewBox="0 0 240 150" role="img" aria-label="Fear and Greed Index: ${v}, ${esc(label)}">
   ${bands}${ticks}
   <text x="18" y="140" fill="var(--tx3)" font-size="9" font-family="Inter">0</text>
   <text x="213" y="140" fill="var(--tx3)" font-size="9" font-family="Inter">100</text>
   <line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" stroke="var(--tx)" stroke-width="3" stroke-linecap="round"/>
   <circle cx="${cx}" cy="${cy}" r="9" fill="var(--s1)" stroke="var(--tx)" stroke-width="3"/>
  </svg>
  <div class="fg-num" style="color:${col}">${v}</div>
  <div class="fg-word" style="color:${col}">${esc(label)}</div>
  <div class="fg-prev">${cell('Prev close',prev.close)}${cell('1 week',prev.week)}${cell('1 month',prev.month)}${cell('1 year',prev.year)}</div>
  ${d.components&&d.components.length?`<div class="fg-comps" style="margin-top:14px">${d.components.map(c=>`
    <div class="fg-comp" title="${esc(c.blurb||'')}">
     <span class="cl">${esc(c.label)}</span>
     <span class="cv" style="color:${fgColor(c.score)}">${c.score}</span>
     <span class="fg-bar"><i style="width:${Math.max(2,c.score)}%;background:${fgColor(c.score)}"></i></span>
    </div>`).join('')}</div>`:''}
  <div class="fg-src">${esc(d.source||'CNN Business')}</div>`;
 $('fgChip').textContent=`F&G ${v} · ${label}`;
 $('fgChip').style.color=col}

/* ===================== indices, tape, breadth ===================== */
function idxCardHTML(q,name){const up=q.chg>=0;const safe=esc(name);
 return`<div class="idx-card" onclick="openChart('${esc(q.ticker)}')">
  <div class="nm"><span onclick="event.stopPropagation();openProfile('${esc(q.ticker)}','${safe.replace(/'/g,'')}')" style="cursor:pointer;text-decoration:underline;text-decoration-color:rgba(229,176,72,.3);text-underline-offset:3px">${safe}</span><small>${esc(q.ticker.replace('^',''))}</small></div>
  <div class="vl">${q.price!=null?fmt(q.price):'—'}</div>
  <div class="cg ${up?'up':'dn'}">${q.chg!=null?(up?'▲ +':'▼ ')+fmt(q.chg)+'%':''}</div></div>`}

async function loadIndices(){
 $('idxUS').innerHTML=skelCards(5);$('idxIL').innerHTML=skelCards(6);
 try{const all=[...IDX_US.map(x=>x[0]),...IDX_IL.map(x=>x[0])];
  const qs=await api('/api/quotes?tickers='+all.map(encodeURIComponent).join(','));
  const draw=(defs,elId)=>{const html=defs.map(([t,name])=>{const q=qs.find(x=>x.ticker===t.toUpperCase())||{ticker:t};
   return q.price!=null?idxCardHTML(q,name):''}).join('');
   $(elId).innerHTML=html||'<div class="empty" style="grid-column:1/-1;padding:20px">No data available right now</div>'};
  draw(IDX_US,'idxUS');draw(IDX_IL,'idxIL')}
 catch(e){$('idxUS').innerHTML='<div class="empty" style="grid-column:1/-1;padding:20px">Could not load indices</div>';$('idxIL').innerHTML=''}}

async function loadTapeAndBento(){
 try{const qs=await api('/api/quotes?tickers='+TAPE.join(','));const items=qs.filter(q=>q.price!=null);
  const html=items.map(q=>`<span class="tp" onclick="openChart('${esc(q.ticker)}')"><b>${esc(q.ticker)}</b><span class="pr">${fmt(q.price)}</span><span class="ch ${q.chg>=0?'up':'dn'}">${q.chg>=0?'▲':'▼'} ${fmt(Math.abs(q.chg))}%</span></span>`).join('');
  $('tape').innerHTML=html+html;
  const spy=items.find(q=>q.ticker==='SPY');
  if(spy){$('spyPrice').textContent='$'+fmt(spy.price);
   $('spyChg').textContent=(spy.chg>=0?'▲ +':'▼ ')+fmt(Math.abs(spy.chg))+'% today';
   $('spyChg').className='b-sub '+(spy.chg>=0?'up':'dn');
   sparkline($('spySpark'),spy.spark||[],spy.chg>=0?'rgb(38,208,124)':'rgb(255,77,106)')}
  /* breadth: see market.js (all S&P 500 members, not the tape) */
  checkAlerts(items)}
 catch(e){}}
/* ===================== heatmap ===================== */
/* Squarified treemap (Bruls, Huizing, van Wijk). Slice-and-dice is trivial to
   write but produces slivers that cannot be read or clicked; squarifying keeps
   every block close to square, which is what makes TradingView's readable. */
function squarify(items,x,y,w,h){
 const out=[];
 const total=items.reduce((s,i)=>s+i.value,0);
 if(total<=0||w<=0||h<=0)return out;
 let nodes=items.map(i=>({...i,area:i.value/total*w*h}));
 const worst=(row,len)=>{if(!row.length)return Infinity;
  const s=row.reduce((a,b)=>a+b.area,0),mx=Math.max(...row.map(r=>r.area)),mn=Math.min(...row.map(r=>r.area));
  const s2=s*s,l2=len*len;return Math.max(l2*mx/s2,s2/(l2*mn))};
 let rx=x,ry=y,rw=w,rh=h;
 while(nodes.length){
  const vertical=rw>=rh;const len=vertical?rh:rw;
  let row=[];
  while(nodes.length){
   const next=row.concat([nodes[0]]);
   if(row.length&&worst(next,len)>worst(row,len))break;
   row=next;nodes.shift();
  }
  const rowArea=row.reduce((a,b)=>a+b.area,0);
  const thick=rowArea/len;
  let off=vertical?ry:rx;
  row.forEach(it=>{
   const side=it.area/thick;
   out.push(vertical?{...it,x:rx,y:off,w:thick,h:side}:{...it,x:off,y:ry,w:side,h:thick});
   off+=side;
  });
  if(vertical){rx+=thick;rw-=thick}else{ry+=thick;rh-=thick}
  if(rw<=.5||rh<=.5)break;
 }
 return out}

function hmColor(chg,scale){
 if(chg==null)return'var(--hm0)';
 const steps=[.15,.35,.6,.8,1];
 const t=Math.min(1,Math.abs(chg)/scale);
 let idx=steps.findIndex(s=>t<=s);if(idx<0)idx=4;
 if(Math.abs(chg)<scale*0.04)return'var(--hm0)';
 return chg>=0?`var(--hm${idx+1})`:`var(--hmn${idx+1})`}

async function loadHeatmap(index,btn){
 index=index||'sp500';
 document.querySelectorAll('.hm-bar .btn').forEach(b=>b.className=b.className.replace('btn-gold','btn-ghost'));
 if(btn)btn.className=btn.className.replace('btn-ghost','btn-gold');
 $('hmBoard').innerHTML='<div class="sk" style="height:460px;border-radius:var(--r)"></div>';
 $('hmSummary').innerHTML='';
 try{S.hm=await api('/api/heatmap/'+index);renderHeatmap();
  $('hmStamp').textContent=`${S.hm.stocks.length} companies · ${fmtCap(S.hm.total_cap*1e9)} total · updated ${new Date(S.hm.generated_at*1000).toLocaleTimeString('en-GB')}`}
 catch(e){$('hmBoard').innerHTML=`<div class="empty"><div class="e-ic">🗺</div><h4>${esc(e.error||'Could not load the heatmap')}</h4></div>`}}

function renderHeatmap(){
 const d=S.hm;if(!d)return;
 const scale=parseFloat($('hmScale').value)||5;
 const showLogos=false; /* Clearbit's free logo service shut down in Dec 2025; tiles show the symbol */
 const board=$('hmBoard');
 const W=board.clientWidth||1200;
 /* 500 names need more canvas than 100, or the tail becomes unreadable
    confetti. Height grows with the count and stops at a screenful and a half. */
 const n=d.stocks.length;
 const ratio=n>300?0.78:n>150?0.62:0.50;
 const H=Math.max(460,Math.min(1180,Math.round(W*ratio)));
 board.style.height=H+'px';

 /* Sectors are laid out first, then each sector's companies inside its box -
    the grouping is the point, so it must survive the layout. */
 const sectors=d.sectors.map(s=>({...s,value:s.cap}));
 const boxes=squarify(sectors,0,0,W,H);
 const byS={};d.stocks.forEach(s=>{(byS[s.sector]=byS[s.sector]||[]).push(s)});

 let html='';
 boxes.forEach(b=>{
  const members=(byS[b.sector]||[]).slice().sort((a,c)=>c.cap-a.cap).map(s=>({...s,value:s.cap}));
  const PAD=1,HEAD=(b.h>60&&b.w>110)?19:0;
  const inner=squarify(members,PAD,HEAD+PAD,Math.max(0,b.w-PAD*2),Math.max(0,b.h-HEAD-PAD*2));
  const cells=inner.map(c=>{
   const area=c.w*c.h;
   /* What fits decides what is drawn. The logo is deliberately shown at
      sizes where no label would fit: on a 500-name map most of the tail is
      too small for text, and a logo still says which company it is where a
      bare coloured square says nothing. */
   const side=Math.min(c.w,c.h);
   const sym=Math.min(18,Math.max(7.5,Math.sqrt(area)/4.4));
   const showSym=c.w>32&&c.h>26;
   const showChg=c.w>44&&c.h>42;
   const showName=c.w>96&&c.h>70;
   const logoPx=Math.round(Math.min(36,Math.max(11,side*0.62)));
   const wantLogo=showLogos&&side>=12&&c.w>=14;
   const logo=wantLogo&&c.domain
    ? `<img class="hm-logo" style="--lg:${logoPx}px" src="https://logo.clearbit.com/${esc(c.domain)}" alt="" loading="lazy" onload="this.classList.add('ready')" onerror="this.remove()">`:'';
   /* Coordinates are relative to the sector box, which is itself positioned:
      adding the sector origin again would push every cell outside and
      overflow:hidden would silently clip it away. */
   return `<div class="hm-cell" style="left:${c.x.toFixed(1)}px;top:${c.y.toFixed(1)}px;width:${c.w.toFixed(1)}px;height:${c.h.toFixed(1)}px;background:${hmColor(c.chg,scale)}"
     data-t="${esc(c.ticker)}" onclick="openChart('${esc(c.ticker)}')"
     onmousemove="hmTip(event,'${esc(c.ticker)}')" onmouseleave="hmTipOff()">
     ${logo}
     ${showSym?`<span class="hm-sym" style="font-size:${sym.toFixed(1)}px">${esc(c.ticker)}</span>`:''}
     ${showName?`<span class="hm-nm">${esc(c.name)}</span>`:''}
     ${showChg?`<span class="hm-chg" style="font-size:${(sym*0.78).toFixed(1)}px">${c.chg>=0?'+':''}${fmt(c.chg,2)}%</span>`:''}
    </div>`}).join('');
  html+=`<div class="hm-sector" style="left:${b.x.toFixed(1)}px;top:${b.y.toFixed(1)}px;width:${b.w.toFixed(1)}px;height:${b.h.toFixed(1)}px">
   ${HEAD?`<div class="hm-head"><b>${esc(b.sector)}</b><span class="${cls(b.chg)}">${sign(b.chg)}%</span></div>`:''}
   ${cells}</div>`});
 board.innerHTML=html;

 $('hmSummary').innerHTML=d.sectors.map(s=>`
  <div class="hm-s" onclick="document.getElementById('hmBoard').scrollIntoView({behavior:'smooth',block:'center'})">
   <div class="n">${esc(s.sector)}</div>
   <div class="v ${cls(s.chg)}">${sign(s.chg)}%</div>
   <div class="w">${fmt(s.weight,1)}% of index · ${s.count}</div></div>`).join('');

 $('hmLegend').innerHTML=`<span>${-scale}%</span>`+
  ['hmn5','hmn4','hmn3','hmn2','hmn1','hm0','hm1','hm2','hm3','hm4','hm5']
   .map(c=>`<u style="background:var(--${c})"></u>`).join('')+`<span>+${scale}%</span>`;
}

/* Pre-market and after-hours move on the last regular close, so they are
   stated as their own session rather than folded into today's change. */
function extTip(s){
 const pre=s.pre_price!=null,post=s.post_price!=null;
 const st=s.state||'';
 /* Before the open the pre-market print is the live one; afterwards the
    post-market print is, and yesterday's pre-market is history. */
 const usePre=pre&&(!post||st==='PRE'||st==='PREPRE');
 if(!usePre&&!post)return '';
 const lab=usePre?'Pre-market':'After hours';
 const px=usePre?s.pre_price:s.post_price;
 const ch=usePre?s.pre_chg:s.post_chg;
 return `<div class="row ext"><i>${lab}</i><span>$${fmt(px)}
   <b class="${cls(ch)}">${ch==null?'—':sign(ch)+'%'}</b></span></div>`}

function hmTip(ev,ticker){
 const d=S.hm;if(!d)return;const s=d.stocks.find(x=>x.ticker===ticker);if(!s)return;
 const tip=$('hmTip');
 tip.innerHTML=`<h5>${esc(s.ticker)}</h5><div class="nm">${esc(s.name)}</div>
  <div class="row"><i>Price</i><span>$${fmt(s.price)}</span></div>
  <div class="row"><i>Change</i><span class="${cls(s.chg)}">${sign(s.chg)}%</span></div>
  ${extTip(s)}
  <div class="row"><i>Market cap</i><span>${fmtCap(s.cap*1e9)}</span></div>
  <div class="row"><i>Sector</i><span style="font-family:var(--ui)">${esc(s.sector)}</span></div>`;
 tip.classList.add('on');
 const w=tip.offsetWidth,h=tip.offsetHeight;
 tip.style.left=Math.min(window.innerWidth-w-12,ev.clientX+16)+'px';
 tip.style.top=Math.max(8,Math.min(window.innerHeight-h-12,ev.clientY-h/2))+'px'}
function hmTipOff(){$('hmTip').classList.remove('on')}
/* ===================== chart ===================== */
const PERIODS=[['1d','1D'],['5d','5D'],['1mo','1M'],['3mo','3M'],['6mo','6M'],['1y','1Y'],['2y','2Y'],['5y','5Y']];
const MA_COLORS={ma50:'#e5b048',ma100:'#22d3ee',ma150:'#3ea6ff',ma200:'#a78bfa'};
function buildPeriods(){$('chPeriods').innerHTML=PERIODS.map(([v,l])=>
 `<button class="p-btn ${v===S.chart.period?'on':''}" onclick="setPeriod('${v}',this)">${l}</button>`).join('')}
function setPeriod(p,btn){S.chart.period=p;document.querySelectorAll('.p-btn').forEach(b=>b.classList.remove('on'));
 if(btn)btn.classList.add('on');loadChart(S.chart.tkr)}
function indOn(name){const b=document.querySelector(`.ind[data-ind="${name}"]`);return b&&b.classList.contains('on')}
function toggleInd(btn){btn.classList.toggle('on');
 if(btn.dataset.ind==='trades'&&btn.classList.contains('on'))return ensureTradesVisible();
 renderChart()}
function setChartType(t,btn){S.chart.type=t;
 document.querySelectorAll('.ind[data-ind="candles"],.ind[data-ind="line"],.ind[data-ind="area"]').forEach(b=>b.classList.remove('on'));
 if(btn)btn.classList.add('on');renderChart()}
function toggleChartFull(){S.chart.full=!S.chart.full;$('chartShell').classList.toggle('full',S.chart.full);
 setTimeout(()=>{if(S.chart.lw){const el=$('lwChart');S.chart.lw.applyOptions({width:el.clientWidth,height:el.clientHeight})}},60)}

async function openChart(t){
 S.chart.tkr=t;S.chart.levels=null;$('chartModal').classList.add('open');
 buildPeriods();$('chSym').textContent=t;$('chName').textContent='';
 $('chPrice').textContent='…';$('chChg').textContent='';$('chFoot').innerHTML='';$('chLegend').innerHTML='';
 loadChartLevels(t);
 await loadChart(t);
 fetchStock(t).then(s=>{
  $('chName').textContent=s.name||'';
  $('chPrice').textContent='$'+fmt(s.price);
  $('chChg').textContent=(s.chg>=0?'▲ +':'▼ ')+fmt(Math.abs(s.chg))+'%';
  $('chChg').className='ch-chg '+(s.chg>=0?'up':'dn');
  const f=(lab,val,c='')=>`<div class="chf"><i>${lab}</i><b class="${c}">${val}</b></div>`;
  $('chFoot').innerHTML=f('Trend',s.regime_label||'—',['up','strong_up'].includes(s.regime)?'up':['down','weak'].includes(s.regime)?'dn':'')
   +f('RSI 14',s.rsi)+f('MACD',s.macd==='BULLISH'?'Bullish':'Bearish',s.macd==='BULLISH'?'up':'dn')
   +f('ATR',s.atr_pct+'%')+f('Support','$'+fmt(s.support))+f('Resistance','$'+fmt(s.resistance))
   +f('Suggested stop','$'+fmt(s.stop),'dn')+f('Target','$'+fmt(s.target),'up')
   +f('52w range','$'+fmt(s.wk52_low)+' – $'+fmt(s.wk52_high));
 }).catch(()=>{})}

function closeChart(){$('chartModal').classList.remove('open');
 if(S.chart.full)toggleChartFull();
 if(S.chart.lw){S.chart.lw.remove();S.chart.lw=null;S.chart.series=null}
 if(S.chart.rsiC){S.chart.rsiC.destroy();S.chart.rsiC=null}
 if(S.chart.macdC){S.chart.macdC.destroy();S.chart.macdC=null}}

async function loadChartLevels(t){
 try{const an=await api('/api/engine/analyze/'+encodeURIComponent(t));
  if(!an.ok)return;
  const pos=((S.plan&&S.plan.positions)||[]).find(p=>p.ticker===t);
  S.chart.levels={suggested_stop:an.suggested_stop,trail_stop:an.trail_stop,
   entry:(an.entries&&an.entries[0])||null,
   position:pos?{entry:pos.entry,stop:pos.stop}:null};
  if(S.chart.data)renderChart()}
 catch(e){/* the chart is still useful without the overlay */}}

async function loadChart(t){
 try{const d=await api('/api/chart/'+encodeURIComponent(t)+'?period='+S.chart.period);
  if(!d.candles||!d.candles.length)throw{error:'No chart data for this symbol'};
  S.chart.data=d;renderChart()}
 catch(e){toast(e.error||'Could not load the chart','err')}}

/* A trade date lands on the last bar at or before it: exact matching would
   silently drop every marker on a weekly chart. */
function barAt(dateStr){const d=S.chart.data;if(!d||!d.candles.length)return null;
 const ts=Math.floor(new Date(dateStr+'T00:00:00Z').getTime()/1000);const c=d.candles;
 if(ts<c[0].ts-86400*8)return null;
 let lo=0,hi=c.length-1,res=-1;
 while(lo<=hi){const mid=(lo+hi)>>1;if(c[mid].ts<=ts){res=mid;lo=mid+1}else hi=mid-1}
 return res>=0?c[res].ts:null}

async function ensureTradesVisible(){
 if(!S.bt||!S.bt.ok||S.bt.ticker!==S.chart.tkr){toast('Run a backtest for this symbol first','info');renderChart();return}
 if(!S.bt.trades.length){toast('That backtest produced no trades','info');renderChart();return}
 if(S.bt.trades.some(t=>barAt(t.entry_date))){renderChart();return}
 const oldest=S.bt.trades.map(t=>t.entry_date).sort()[0];
 const months=(Date.now()-new Date(oldest+'T00:00:00Z').getTime())/(86400000*30.4);
 S.chart.period=months<=11?'1y':'5y';buildPeriods();
 toast('Widened the range so the backtest trades are visible','info');
 await loadChart(S.chart.tkr)}

function bollinger(closes,n=20,k=2){
 const up=[],lo=[],mid=[];
 for(let i=0;i<closes.length;i++){
  if(i<n-1||closes[i]==null){up.push(null);lo.push(null);mid.push(null);continue}
  const win=closes.slice(i-n+1,i+1).filter(v=>v!=null);
  if(win.length<n){up.push(null);lo.push(null);mid.push(null);continue}
  const m=win.reduce((a,b)=>a+b,0)/win.length;
  const sd=Math.sqrt(win.reduce((a,b)=>a+(b-m)*(b-m),0)/win.length);
  mid.push(m);up.push(m+k*sd);lo.push(m-k*sd)}
 return{up,lo,mid}}

function renderChart(){
 const d=S.chart.data;if(!d)return;
 if(typeof LightweightCharts==='undefined'){toast('Charting library failed to load — check your connection','err');return}
 if(S.chart.lw){S.chart.lw.remove()}
 const el=$('lwChart');el.innerHTML='';
 const lw=LightweightCharts.createChart(el,{
  layout:{background:{color:'#0e1420'},textColor:'#9aa8c0',fontFamily:"'JetBrains Mono',monospace",fontSize:11},
  grid:{vertLines:{color:'rgba(255,255,255,.05)'},horzLines:{color:'rgba(255,255,255,.05)'}},
  rightPriceScale:{borderColor:'rgba(255,255,255,.10)',scaleMargins:{top:.08,bottom:indOn('vol')?.22:.08},
   mode:indOn('log')?1:0},
  timeScale:{borderColor:'rgba(255,255,255,.10)',timeVisible:S.chart.period==='1d'||S.chart.period==='5d',secondsVisible:false},
  crosshair:{mode:1,
   vertLine:{color:'rgba(154,168,192,.45)',width:1,style:2,labelBackgroundColor:'#222e44'},
   horzLine:{color:'rgba(154,168,192,.45)',width:1,style:2,labelBackgroundColor:'#222e44'}},
  handleScroll:true,handleScale:true});
 S.chart.lw=lw;

 const up='#26d07c',dn='#ff4d6a';
 let main;
 if(S.chart.type==='line'){
  main=lw.addLineSeries({color:'#e5b048',lineWidth:2,priceLineVisible:true});
  main.setData(d.candles.map(c=>({time:c.ts,value:c.c})));
 }else if(S.chart.type==='area'){
  main=lw.addAreaSeries({lineColor:'#e5b048',topColor:'rgba(229,176,72,.28)',bottomColor:'rgba(229,176,72,0)',lineWidth:2});
  main.setData(d.candles.map(c=>({time:c.ts,value:c.c})));
 }else{
  main=lw.addCandlestickSeries({upColor:up,downColor:dn,borderUpColor:up,borderDownColor:dn,wickUpColor:up,wickDownColor:dn});
  main.setData(d.candles.map(c=>({time:c.ts,open:c.o,high:c.h,low:c.l,close:c.c})));
 }
 S.chart.series=main;

 if(indOn('vol')){
  const vs=lw.addHistogramSeries({priceFormat:{type:'volume'},priceScaleId:'vol'});
  lw.priceScale('vol').applyOptions({scaleMargins:{top:0.82,bottom:0}});
  vs.setData(d.candles.map(c=>({time:c.ts,value:c.v,color:c.c>=c.o?'rgba(38,208,124,.35)':'rgba(255,77,106,.3)'})))}

 const maLine=(key,color,width)=>{if(!indOn(key)||!Array.isArray(d[key]))return;
  const pts=d.candles.map((c,i)=>d[key][i]!=null?{time:c.ts,value:d[key][i]}:null).filter(Boolean);
  if(!pts.length)return;
  const s=lw.addLineSeries({color,lineWidth:width,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
  s.setData(pts)};
 maLine('ma50',MA_COLORS.ma50,2);maLine('ma100',MA_COLORS.ma100,1.5);
 maLine('ma150',MA_COLORS.ma150,1.5);maLine('ma200',MA_COLORS.ma200,1.8);

 if(indOn('bb')){
  const bb=bollinger(d.candles.map(c=>c.c));
  [['up','rgba(62,166,255,.55)'],['lo','rgba(62,166,255,.55)']].forEach(([k,col])=>{
   const pts=d.candles.map((c,i)=>bb[k][i]!=null?{time:c.ts,value:bb[k][i]}:null).filter(Boolean);
   if(!pts.length)return;
   const s=lw.addLineSeries({color:col,lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false,lineStyle:2});
   s.setData(pts)})}

 /* The levels the command centre prescribes, drawn where you look at price. */
 if(indOn('levels')&&S.chart.levels){const L=S.chart.levels;
  const line=(price,color,title,style)=>{if(price==null)return;
   main.createPriceLine({price,color,lineWidth:1,lineStyle:style==null?2:style,axisLabelVisible:true,title})};
  if(L.position){line(L.position.entry,'#9aa8c0','My entry',0);
   if(L.position.stop!=null)line(L.position.stop,'#ff4d6a','My stop',0)}
  line(L.suggested_stop,'#ff4d6a','Suggested stop');
  line(L.trail_stop,'#ffa726','Trailing stop');
  if(L.entry){line(L.entry.zone_low,'#26d07c','Entry zone');
   line(L.entry.target1,'#26d07c','Target 1');line(L.entry.target2,'#26d07c','Target 2')}}

 if(indOn('trades')&&S.bt&&S.bt.ok&&S.bt.ticker===S.chart.tkr){
  const marks=[];
  S.bt.trades.forEach(t=>{const a=barAt(t.entry_date),b=barAt(t.exit_date);
   if(a)marks.push({time:a,position:'belowBar',color:'#26d07c',shape:'arrowUp',text:'BUY'});
   if(b)marks.push({time:b,position:'aboveBar',color:(t.r||0)>=0?'#3ea6ff':'#ff4d6a',shape:'arrowDown',
    text:(t.r!=null?(t.r>=0?'+':'')+t.r+'R':'EXIT')})});
  marks.sort((a,b)=>a.time-b.time);
  if(marks.length)main.setMarkers(marks)}

 /* Crosshair legend: OHLC under the cursor, the way a real terminal reads. */
 const legend=$('chLegend');
 const paint=(c,i)=>{
  if(!c){legend.innerHTML='';return}
  const prev=i>0?d.candles[i-1]:null;
  const chg=prev?((c.c-prev.c)/prev.c*100):null;
  const mas=['ma50','ma100','ma150','ma200'].filter(k=>indOn(k)&&d[k]&&d[k][i]!=null)
   .map(k=>`<span><u style="background:${MA_COLORS[k]}"></u>${k.toUpperCase()} ${fmt(d[k][i])}</span>`).join('');
  legend.innerHTML=
   `<div class="lg"><i>O</i><span class="lg-v">${fmt(c.o)}</span></div>
    <div class="lg"><i>H</i><span class="lg-v">${fmt(c.h)}</span></div>
    <div class="lg"><i>L</i><span class="lg-v">${fmt(c.l)}</span></div>
    <div class="lg"><i>C</i><span class="lg-v ${chg==null?'':cls(chg)}">${fmt(c.c)}</span></div>
    ${chg!=null?`<div class="lg"><span class="lg-v ${cls(chg)}">${sign(chg)}%</span></div>`:''}
    <div class="lg"><i>Vol</i><span class="lg-v">${c.v>=1e6?fmt(c.v/1e6,1)+'M':fmt(c.v,0)}</span></div>
    ${mas?`<div class="ch-ma">${mas}</div>`:''}`};
 const byTs={};d.candles.forEach((c,i)=>{byTs[c.ts]=i});
 lw.subscribeCrosshairMove(param=>{
  if(!param.time){paint(d.candles[d.candles.length-1],d.candles.length-1);return}
  const i=byTs[param.time];paint(i!=null?d.candles[i]:null,i)});
 paint(d.candles[d.candles.length-1],d.candles.length-1);

 lw.timeScale().fitContent();
 if(S.chart._ro)S.chart._ro.disconnect();
 S.chart._ro=new ResizeObserver(()=>lw.applyOptions({width:el.clientWidth,height:el.clientHeight}));
 S.chart._ro.observe(el);

 $('rsiWrap').style.display=indOn('rsi')?'':'none';$('macdWrap').style.display=indOn('macd')?'':'none';
 const labels=d.candles.map(c=>c.t);
 if(S.chart.rsiC){S.chart.rsiC.destroy();S.chart.rsiC=null}
 if(S.chart.macdC){S.chart.macdC.destroy();S.chart.macdC=null}
 const ax={x:{display:false},y:{ticks:{color:'#7d8dac',font:{size:9,family:'JetBrains Mono'}},grid:{color:'rgba(255,255,255,.05)'}}};
 const common={responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{display:false},tooltip:{enabled:false}}};
 if(indOn('rsi')&&typeof Chart!=='undefined')
  S.chart.rsiC=new Chart($('rsiC'),{type:'line',data:{labels,datasets:[{data:d.rsi,borderColor:'#a78bfa',borderWidth:1.5,pointRadius:0,tension:.2}]},
   options:{...common,scales:{...ax,y:{...ax.y,min:0,max:100,ticks:{...ax.y.ticks,stepSize:30}}}}});
 if(indOn('macd')&&typeof Chart!=='undefined')
  S.chart.macdC=new Chart($('macdC'),{type:'line',data:{labels,datasets:[
   {data:d.macd,borderColor:'#22d3ee',borderWidth:1.5,pointRadius:0,tension:.2},
   {data:d.signal,borderColor:'#e5b048',borderWidth:1.2,pointRadius:0,tension:.2}]},options:{...common,scales:ax}})}
/* ===================== skeletons ===================== */
function skelCards(n){return Array(n).fill(0).map(()=>
 '<div class="glass sk-card"><div class="sk sk-line"></div><div class="sk sk-line short"></div><div class="sk" style="height:38px;margin:12px 0;border-radius:5px"></div><div class="sk sk-line short"></div></div>').join('')}
function skelRows(n){return Array(n).fill(0).map(()=>'<div class="glass sk sk-row"></div>').join('')}
function skeletonNews(){
 const row='<div class="glass sk-item"><div class="sk sk-n"></div><div style="flex:1"><div class="sk sk-line"></div><div class="sk sk-line short"></div></div></div>';
 return `<div class="news-grid"><div class="glass sk-hero"><div class="sk sk-visual"></div><div style="padding:16px"><div class="sk sk-line"></div><div class="sk sk-line"></div><div class="sk sk-line short"></div></div></div><div class="news-list">${row.repeat(5)}</div></div>`}

/* ===================== scanner ===================== */
async function fetchStock(t){if(S.cache[t]&&Date.now()-S.cache[t]._at<60000)return S.cache[t];
 const d=await api('/api/stock/'+encodeURIComponent(t));d._at=Date.now();S.cache[t]=d;return d}
async function loadPreset(key,btn){
 const list=PRESETS[key]||[];$('stocksGrid').innerHTML=skelCards(8);
 document.querySelectorAll('#v-home .filters .btn').forEach(x=>{x.className=x.className.replace('btn-gold','btn-ghost')});
 if(btn)btn.className=btn.className.replace('btn-ghost','btn-gold');
 const results=await Promise.allSettled(list.map(fetchStock));
 const stocks=results.filter(r=>r.status==='fulfilled').map(r=>r.value);
 renderCards(stocks);updateStats(stocks)}
function updateStats(stocks){if(!stocks.length)return;
 $('stAvgRsi').textContent=fmt(stocks.reduce((a,s)=>a+s.rsi,0)/stocks.length,1);
 $('stBuy').textContent=stocks.filter(s=>['up','strong_up'].includes(s.regime)).length;
 $('stSell').textContent=stocks.filter(s=>['down','weak'].includes(s.regime)).length;
 $('stCount').textContent=stocks.length}
const ringColor=c=>c>=75?'#26d07c':c>=55?'#e5b048':'#ff4d6a';
function cardHTML(s){
 const up=s.chg>=0,inW=S.watch.includes(s.ticker),ts=s.trend_score??0,rc=ringColor(ts),circ=2*Math.PI*27,dash=(ts/100)*circ;
 const rg=s.regime||'range',rgc=['up','strong_up','recovering'].includes(rg)?'up':['down','weak'].includes(rg)?'dn':'warn';
 const name=esc(s.name||'');
 return`<div class="glass card">
  <div class="c-top">
   <div class="c-mid"><div class="c-tkr" onclick="openChart('${esc(s.ticker)}')">${esc(s.ticker)}</div><div class="c-name">${name}</div></div>
   <div class="c-acts">
    <button class="iconbtn neutral ${inW?'on':''}" onclick="toggleWatch('${esc(s.ticker)}',this)" title="Watchlist" style="color:${inW?'var(--gold)':''}">★</button>
    <button class="iconbtn neutral" onclick="quickAdd('${esc(s.ticker)}',${s.price})" title="Add to portfolio">+</button>
   </div>
   <div class="score-ring"><svg width="60" height="60"><circle cx="30" cy="30" r="27" fill="none" stroke="var(--s3)" stroke-width="5"/>
    <circle cx="30" cy="30" r="27" fill="none" stroke="${rc}" stroke-width="5" stroke-linecap="round" stroke-dasharray="${dash} ${circ}"/></svg>
    <div class="sr-num" style="color:${rc}" title="Rule-based trend score: moving-average structure, slope, MACD, ADX and RSI. A description of the trend, not a forecast.">${ts}</div><div class="sr-lab">TREND</div></div>
  </div>
  <div class="c-price-row"><div class="c-price">$${fmt(s.price)}</div><div class="c-chg ${up?'up':'dn'}">${up?'▲ +':'▼ '}${fmt(Math.abs(s.chg))}%</div></div>
  <canvas class="spark c-spark" data-s='${JSON.stringify(s.history||[]).replace(/'/g,'')}' height="38"></canvas>
  <div class="c-metrics">
   <div class="m"><div class="lbl">RSI</div><div class="vl ${s.rsi<35?'up':s.rsi>70?'dn':''}">${s.rsi}</div></div>
   <div class="m"><div class="lbl">MACD</div><div class="vl ${s.macd==='BULLISH'?'up':'dn'}">${s.macd==='BULLISH'?'▲':'▼'}</div></div>
   <div class="m"><div class="lbl">ATR</div><div class="vl">${s.atr_pct}%</div></div>
   <div class="m"><div class="lbl">VOL</div><div class="vl ${s.vol_ratio>1.4?'up':''}">×${s.vol_ratio}</div></div>
  </div>
  <div class="c-bottom">
   <span class="rec" style="color:var(--${rgc});border-color:var(--${rgc}-br);background:var(--${rgc}-bg)">${esc(s.regime_label||rg)}</span>
   <div class="levels">${s.suggested_stop!=null?`Suggested stop $${fmt(s.suggested_stop)}<br>`:''}52w high $${fmt(s.wk52_high)}</div>
  </div></div>`}
function renderCards(stocks){
 $('stocksGrid').innerHTML=stocks.length?stocks.map(cardHTML).join('')
  :'<div class="empty" style="grid-column:1/-1"><h4>No data returned — try again in a moment</h4></div>';
 requestAnimationFrame(()=>document.querySelectorAll('#stocksGrid canvas').forEach(c=>{
  let d=[];try{d=JSON.parse(c.dataset.s)}catch(e){}
  if(d.length>1)sparkline(c,d,d[d.length-1]>=d[0]?'rgb(38,208,124)':'rgb(255,77,106)')}))}
async function toggleWatch(t,btn){
 if(S.watch.includes(t)){await store.delWatch(t).catch(()=>{});S.watch=S.watch.filter(x=>x!==t);
  if(btn){btn.style.color='';btn.classList.remove('on')}toast(t+' removed from watchlist','info')}
 else{await store.addWatch(t).catch(()=>{});S.watch.push(t);
  if(btn){btn.style.color='var(--gold)';btn.classList.add('on')}toast(t+' added to watchlist ★','ok')}
 if(S.plan)loadPlan(false)}
function quickAdd(t,price){go('portfolio');$('pfTicker').value=t;$('pfEntry').value=price;$('pfQty').focus();
 toast('Fill in the quantity and add it','info')}

/* ===================== profile drawer ===================== */
async function openProfile(t,fallbackName){
 $('proDrawer').classList.add('open');$('proName').textContent=fallbackName||t;$('proTkr').textContent=t;
 $('proBody').innerHTML='<div class="spinner"></div>';
 try{
  const[p,qs]=await Promise.all([api('/api/profile/'+encodeURIComponent(t)),
   api('/api/quotes?tickers='+encodeURIComponent(t)).catch(()=>[])]);
  const q=(qs||[])[0]||{};if(p.name)$('proName').textContent=p.name;
  const up=(q.chg||0)>=0;
  const fact=(lab,val)=>`<div><i>${lab}</i><b>${val}</b></div>`;
  $('proBody').innerHTML=`
   <div class="pro-price-row"><div class="pro-price">${q.price!=null?'$'+fmt(q.price):'—'}</div>
    <div class="pro-chg ${up?'up':'dn'}">${q.chg!=null?(up?'▲ +':'▼ ')+fmt(Math.abs(q.chg))+'%':''}</div></div>
   <div class="pro-facts">
    ${fact('Sector',esc(p.sector||'—'))}${fact('Industry',esc(p.industry||'—'))}
    ${fact('Market cap',fmtCap(p.market_cap))}${fact('Employees',p.employees?fmt(p.employees,0):'—')}
    ${fact('CEO',esc(p.ceo||'—'))}${fact('Country',esc(p.country||'—'))}
    ${fact('Dividend yield',p.dividend_yield?fmt(p.dividend_yield*100,2)+'%':'—')}${fact('Currency',esc(p.currency||'USD'))}
   </div>
   <div style="display:flex;gap:8px;margin:14px 0">
    <button class="btn btn-gold btn-sm" style="flex:1" onclick="closeProfile();openChart('${esc(t)}')">Open chart</button>
    <button class="btn btn-ghost btn-sm" onclick="closeProfile();btGo('${esc(t)}')">🧪 Backtest</button>
   </div>
   ${p.summary?`<div class="pro-sum">${esc(p.summary)}</div>`:''}
   ${p.website?`<div style="margin-top:12px"><a href="${esc(p.website)}" target="_blank" rel="noopener noreferrer" style="color:var(--info);font-size:12px">${esc(p.website)}</a></div>`:''}`}
 catch(e){$('proBody').innerHTML='<div class="empty"><h4>Could not load this profile</h4></div>'}}
function closeProfile(){$('proDrawer').classList.remove('open')}

/* ===================== command palette ===================== */
let cmdkTimer=null;
function openCmdk(){$('cmdk').classList.add('open');$('cmdkInput').value='';$('cmdkList').innerHTML='';$('cmdkInput').focus()}
function closeCmdk(){$('cmdk').classList.remove('open')}
function pickCmdk(sym){closeCmdk();openChart(sym)}
function timeAgo(ts){if(!ts)return'unknown time';
 const m=Math.floor((Date.now()/1000-ts)/60);
 if(m<1)return'just now';if(m<60)return m+'m ago';
 const h=Math.floor(m/60);if(h<24)return h+'h ago';
 const dd=Math.floor(h/24);return dd===1?'yesterday':dd+'d ago'}
/* ===================== command centre ===================== */
const ACT_ICON={SET_STOP:'🛡',STOP_HIT:'🚨',STOP_NEAR:'⚠️',BREAKEVEN:'🔒',TRAIL_UP:'📈',
 TREND_BREAK:'📉',TAKE_PARTIAL:'💰',RISK_OVERSIZE:'⚖️',PORTFOLIO_HEAT:'🔥'};
const SEV_EN={critical:'Critical',high:'Urgent',medium:'Review',info:'Note'};
const today=()=>new Date().toISOString().slice(0,10);
const actKey=a=>`${a.code}:${a.ticker}:${a.suggest||''}`;
function getDone(){try{const d=JSON.parse(localStorage.getItem('js_done')||'{}');return d._day===today()?d:{_day:today()}}catch(e){return{_day:today()}}}
function markDone(key){const d=getDone();d[key]=1;localStorage.setItem('js_done',JSON.stringify(d))}
function toggleSettingsPanel(){const p=$('ccSettings');p.style.display=p.style.display==='none'?'':'none'}

async function loadSettings(){
 try{S.settings=await store.getSettings()}catch(e){S.settings={equity:0,risk_pct:1,trail_mult:null}}
 $('setEquity').value=S.settings.equity||'';
 $('setRisk').value=S.settings.risk_pct||1;
 $('setTrail').value=S.settings.trail_mult==null?'':String(S.settings.trail_mult);
 return S.settings}
async function saveSettings(){
 const s={equity:parseFloat($('setEquity').value)||0,risk_pct:parseFloat($('setRisk').value)||1,
  trail_mult:$('setTrail').value?parseFloat($('setTrail').value):null};
 try{S.settings=await store.saveSettings(s);toast('Risk settings saved','ok');loadPlan(true)}
 catch(e){toast(e.error||'Could not save','err')}}
async function enableNotifications(){
 if(!('Notification'in window)){toast('This browser does not support notifications','err');return}
 const p=await Notification.requestPermission();
 toast(p==='granted'?'Alerts enabled — you will be notified of urgent actions':'Notifications are blocked in your browser settings',p==='granted'?'ok':'err')}
function desktopNotify(plan){
 if(!('Notification'in window)||Notification.permission!=='granted')return;
 const urgent=plan.actions.filter(a=>a.severity==='critical'||a.severity==='high');
 const fresh=urgent.filter(a=>!S.notified.has(actKey(a)));
 if(!fresh.length)return;
 fresh.forEach(a=>S.notified.add(actKey(a)));
 const head=fresh[0];
 new Notification(`Jonathan Stocks · ${head.ticker}`,{body:head.title+(fresh.length>1?`\nand ${fresh.length-1} more`:''),tag:'js-plan'})}

async function loadPlan(force){
 /* Signed in, the server reads the portfolio itself. As a guest the plan is
    computed from the request body, so re-read local storage every time. */
 if(!S.user){try{S.pf=await store.getPf()}catch(e){}try{S.watch=await store.getWatch()}catch(e){}}
 if(force||!S.plan)$('ccActions').innerHTML=skelRows(4);
 try{
  const body=S.user?{}:{positions:S.pf,watch:S.watch,settings:S.settings||{}};
  const plan=await api('/api/engine/plan',{method:'POST',body:JSON.stringify(body)});
  S.plan=plan;renderPlan(plan);desktopNotify(plan)}
 catch(e){$('ccActions').innerHTML=`<div class="empty"><div class="e-ic">⚠</div><h4>${esc(e.error||'Could not build the plan')}</h4></div>`}}

function renderPlan(p){
 const urgent=p.actions.filter(a=>a.severity==='critical'||a.severity==='high').length;
 $('ccUrgent').textContent=urgent;$('ccUrgent').className='t-val '+(urgent?'dn':'up');
 $('ccHeat').textContent=p.risk.heat_pct!=null?fmt(p.risk.heat_pct,1)+'%':'—';
 $('ccHeat').className='t-val '+(p.risk.heat_pct==null?'':p.risk.heat_pct>8?'dn':'up');
 $('ccHeatSub').textContent=p.risk.open_risk!=null?'$'+fmt(p.risk.open_risk,0)+' at risk':'distance to stops';
 $('ccUnprot').textContent=p.risk.unprotected;
 $('ccUnprot').className='t-val '+(p.risk.unprotected?'dn':'up');
 $('ccEntries').textContent=p.entries.length;
 $('ccStamp').textContent='Updated '+new Date(p.generated_at*1000).toLocaleTimeString('en-GB');
 renderBrief(p,urgent);renderActions(p.actions);renderRiskTable(p.positions);renderEntries(p.entries)}

function renderBrief(p,urgent){
 const b=$('ccBrief');b.style.display='';
 let ic='✅',title='Everything is under control',txt='No open actions. Every position has a stop and the trends are intact.';
 if(!p.positions.length){ic='💼';title='Your portfolio is empty';
  txt='Add positions in the Portfolio tab and the engine will start monitoring them for stops and exits.'}
 else if(urgent){ic='🚨';title=`${urgent} action${urgent>1?'s':''} need attention`;
  txt='Start with anything marked Critical — those are positions where the risk is undefined or the stop has already been breached.'}
 else if(p.risk.unprotected){ic='🛡';title=`${p.risk.unprotected} position${p.risk.unprotected>1?'s':''} without a stop`;
  txt='Every position needs a predefined stop. It is the one decision that caps your maximum loss.'}
 else if(p.entries.length){ic='🎯';title=`${p.entries.length} entry signal${p.entries.length>1?'s':''} on your watchlist`;
  txt='The portfolio is protected. Scroll down for the technical setups found on the names you follow.'}
 $('ccBriefIc').textContent=ic;$('ccBriefTitle').textContent=title;$('ccBriefText').textContent=txt}

function renderActions(actions){
 const box=$('ccActions'),done=getDone();
 const live=actions.filter(a=>!done[actKey(a)]);
 if(!live.length){box.innerHTML='<div class="glass" style="padding:34px;text-align:center;color:var(--tx2)"><div style="font-size:34px;margin-bottom:10px">✅</div><b style="font-size:15px">No open actions</b><div style="font-size:13px;color:var(--tx3);margin-top:5px">Every position is protected and up to date</div></div>';return}
 box.innerHTML=live.map(a=>{
  const k=actKey(a).replace(/'/g,'');
  const apply=a.suggest?`<button class="btn btn-gold btn-sm" onclick="applySuggested('${esc(a.ticker)}','${a.code}',${a.suggest},'${a.stop_type||'fixed'}')">Set stop $${fmt(a.suggest)}</button>`:'';
  return`<div class="glass act sev-${a.severity}">
   <div class="act-ic">${ACT_ICON[a.code]||'•'}</div>
   <div><span class="act-tkr" onclick="openChart('${esc(a.ticker)}')">${esc(a.ticker)}</span>
    <div class="act-title">${esc(a.title)}</div><div class="act-detail">${esc(a.detail)}</div></div>
   <div class="act-side"><span class="sev-pill">${SEV_EN[a.severity]||''}</span>${apply}
    <button class="btn btn-ghost btn-sm" onclick="dismissAction('${k}',this)">Mark done</button></div></div>`}).join('')}

function dismissAction(key,btn){markDone(key);const card=btn.closest('.act');card.classList.add('done');
 setTimeout(()=>{card.remove();if(!document.querySelectorAll('#ccActions .act').length)renderActions(S.plan?S.plan.actions:[])},250)}

async function applySuggested(ticker,code,value,type){
 const pos=((S.plan&&S.plan.positions)||[]).find(p=>p.ticker===ticker);
 if(!pos){toast('No matching position found','err');return}
 await setStop(pos.id,value,type)}
async function setStop(id,value,type){
 const patch={stop:value};if(type)patch.stop_type=type;
 try{await store.patchPf(id,patch);toast('Stop updated to $'+fmt(value),'ok');
  S.pf=await store.getPf().catch(()=>S.pf);loadPlan(true)}
 catch(e){toast(e.error||'Could not update the stop','err')}}
function onStopInput(id,el){
 const p=((S.plan&&S.plan.positions)||[]).find(x=>String(x.id)===String(id));
 const revert=()=>{el.value=p&&p.stop!=null?p.stop:''};
 const v=parseFloat(el.value);
 if(!(v>0)){toast('Enter a valid stop price','err');revert();return}
 /* A stop above the current price sells on the spot — almost always a typo. */
 if(p&&v>=p.price&&!confirm(`The stop you entered ($${fmt(v)}) is above the current price ($${fmt(p.price)}).\nAn order like that would execute immediately and sell the position.\n\nContinue anyway?`)){revert();return}
 setStop(id,v)}
async function setStopType(id,type){
 try{await store.patchPf(id,{stop_type:type});S.pf=await store.getPf().catch(()=>S.pf);
  toast(type==='trail'?'Switched to a trailing stop — it will rise with price':'Switched to a fixed stop','info');loadPlan(true)}
 catch(e){toast(e.error||'Could not update','err')}}
const regimeClass=r=>r==='strong_up'||r==='up'?'r-up':r==='down'||r==='weak'?'r-down':'r-flat';
const REGIME_EN={strong_up:'Strong uptrend',up:'Uptrend',recovering:'Recovering',range:'Range',weak:'Weakening',down:'Downtrend'};

function renderRiskTable(positions){
 const b=$('ccRisk');
 if(!positions.length){b.innerHTML='<tr><td colspan="12" style="padding:40px;color:var(--tx3)">No positions yet — add one in the Portfolio tab</td></tr>';return}
 b.innerHTML=positions.map(p=>{
  const sug=p.stop_type==='trail'?p.trail_stop:(p.has_stop?(p.trail_stop||p.suggested_stop):p.suggested_stop);
  const better=sug!=null&&(!p.has_stop||sug>p.stop*1.005);
  return`<tr>
  <td class="tkr-cell" onclick="openChart('${esc(p.ticker)}')">${esc(p.ticker)}</td>
  <td><span class="regime-chip ${regimeClass(p.regime)}">${REGIME_EN[p.regime]||esc(p.regime)}</span></td>
  <td>$${fmt(p.price)}</td><td>$${fmt(p.entry)}</td>
  <td class="${cls(p.pnl)}">${sign(p.pnl)==='—'?'—':(p.pnl>=0?'+':'−')+'$'+fmt(Math.abs(p.pnl))}<br><small>${sign(p.pnl_pct)}%</small></td>
  <td><input class="stop-inp ${p.has_stop?'':'unset'}" type="number" step="any" value="${p.stop!=null?p.stop:''}" placeholder="none" aria-label="Stop for ${esc(p.ticker)}" onchange="onStopInput(${p.id},this)"></td>
  <td><span class="seg"><button class="${p.stop_type!=='trail'?'on':''}" onclick="setStopType(${p.id},'fixed')">Fixed</button><button class="${p.stop_type==='trail'?'on':''}" onclick="setStopType(${p.id},'trail')">Trail</button></span></td>
  <td class="${p.stop_distance_pct!=null&&p.stop_distance_pct<3?'dn':''}">${p.stop_distance_pct!=null?fmt(p.stop_distance_pct,1)+'%':'—'}</td>
  <td><span class="rpill ${cls(p.r_multiple)}">${p.r_multiple!=null?sign(p.r_multiple,1)+'R':'—'}</span></td>
  <td>${p.open_risk!=null?'$'+fmt(p.open_risk,0):'—'}</td>
  <td>${sug!=null?`<button class="btn ${better?'btn-gold':'btn-ghost'} btn-sm" onclick="setStop(${p.id},${sug},'${p.stop_type==='trail'?'trail':'fixed'}')">$${fmt(sug)}</button>`:'—'}</td>
  <td style="white-space:nowrap"><button class="iconbtn neutral" onclick="btGo('${esc(p.ticker)}')" title="Backtest">🧪</button><button class="iconbtn" onclick="delPosition(${p.id})" title="Remove">🗑</button></td></tr>`}).join('')}

function renderEntries(entries){
 const g=$('ccEntryGrid');
 if(!entries.length){g.innerHTML='<div class="empty" style="grid-column:1/-1"><div class="e-ic">🎯</div><h4>No entry signals right now</h4><div style="font-size:13px">Add names to your watchlist with ★ and they will be scanned after each session</div></div>';return}
 g.innerHTML=entries.map(e=>{
  const size=e.sized_qty?`By your risk policy: <b>${fmt(e.sized_qty,0)} shares</b> · risking <b>$${fmt(e.sized_qty*e.risk_per_share,0)}</b> if the stop is hit`
   :'Set your account value in Risk settings to get a suggested size';
  return`<div class="glass ent">
   <div class="ent-top"><span class="ent-tkr" onclick="openChart('${esc(e.ticker)}')">${esc(e.ticker)}</span>
    <span class="regime-chip ${regimeClass(e.regime)}">${REGIME_EN[e.regime]||''}</span>
    <span class="ent-q">${e.quality}</span></div>
   <div class="ent-setup">${esc(e.title)}</div>
   <ul class="ent-why">${e.why.map(w=>`<li>${esc(w)}</li>`).join('')}</ul>
   ${e.also&&e.also.length?`<div style="font-size:11.5px;color:var(--tx3);margin:-7px 0 11px">Also confirming: ${e.also.map(esc).join(' · ')}</div>`:''}
   <div class="ent-lv">
    <div><i>Price</i><b>$${fmt(e.price)}</b></div>
    <div><i>Stop</i><b class="dn">$${fmt(e.stop)}</b></div>
    <div><i>Target 1</i><b class="up">$${fmt(e.target1)}</b></div>
    <div><i>Target 2</i><b class="up">$${fmt(e.target2)}</b></div>
   </div>
   <div class="ent-size">${size}</div>
   <div style="display:flex;gap:8px">
    <button class="btn btn-gold btn-sm" style="flex:1" onclick="entryToPortfolio('${esc(e.ticker)}',${e.price},${e.stop},${e.sized_qty||0})">Add to portfolio</button>
    <button class="btn btn-ghost btn-sm" onclick="btGo('${esc(e.ticker)}')" title="Backtest these rules on this stock">🧪</button>
    <button class="btn btn-ghost btn-sm" onclick="openChart('${esc(e.ticker)}')">Chart</button>
   </div></div>`}).join('')}
function entryToPortfolio(t,price,stop,qty){
 go('portfolio');$('pfTicker').value=t;$('pfEntry').value=price;$('pfStop').value=stop;
 if(qty)$('pfQty').value=qty;
 toast('Check the details and press Add','info');$('pfQty').focus()}
/* ===================== portfolio ===================== */
let pfPie=null;
async function loadPortfolio(){
 try{S.pf=await store.getPf()}catch(e){S.pf=[]}
 if(!S.pf.length){
  $('pfBody').innerHTML='<tr><td colspan="9" style="text-align:center;padding:44px;color:var(--tx3)">No positions yet — add your first one below</td></tr>';
  ['pfTotal','pfPnl'].forEach(i=>$(i).textContent='$0');$('pfRet').textContent='0%';$('pfN').textContent='0';
  if(pfPie){pfPie.destroy();pfPie=null}return}
 const tickers=[...new Set(S.pf.map(p=>p.ticker))];
 let quotes=[];try{quotes=await api('/api/quotes?tickers='+tickers.join(','))}catch(e){}
 const pmap=Object.fromEntries(quotes.map(q=>[q.ticker,q.price]));
 let total=0,cost=0;
 $('pfBody').innerHTML=S.pf.map(p=>{
  const cur=pmap[p.ticker];const val=cur!=null?cur*p.qty:null;const c=p.entry*p.qty;
  cost+=c;if(val!=null)total+=val;
  const pnl=val!=null?val-c:null;const pct=pnl!=null?pnl/c*100:null;
  const stopTxt=p.stop!=null&&p.stop!==''?`$${fmt(p.stop)}${p.stop_type==='trail'?' <small style="color:var(--info)">trail</small>':''}`
   :'<small style="color:var(--dn)">no stop</small>';
  return`<tr><td class="tkr-cell" onclick="openChart('${esc(p.ticker)}')">${esc(p.ticker)}</td>
   <td>${fmt(p.qty,p.qty%1?3:0)}</td><td>$${fmt(p.entry)}</td><td>${cur!=null?'$'+fmt(cur):'—'}</td>
   <td>${stopTxt}</td><td>${val!=null?'$'+fmt(val):'—'}</td>
   <td class="${cls(pnl)}">${pnl!=null?(pnl>=0?'+':'−')+'$'+fmt(Math.abs(pnl)):'—'}</td>
   <td class="${cls(pct)}">${pct!=null?sign(pct)+'%':'—'}</td>
   <td><button class="iconbtn" onclick="delPosition(${p.id})" title="Remove">🗑</button></td></tr>`}).join('');
 const pnl=total-cost;
 $('pfTotal').textContent='$'+fmt(total);
 $('pfPnl').textContent=(pnl>=0?'+':'−')+'$'+fmt(Math.abs(pnl));
 $('pfPnl').style.color=pnl>=0?'var(--up)':'var(--dn)';
 $('pfRet').textContent=cost?sign(pnl/cost*100)+'%':'0%';
 $('pfRet').style.color=pnl>=0?'var(--up)':'var(--dn)';
 $('pfN').textContent=S.pf.length;
 if(pfPie){pfPie.destroy();pfPie=null}
 const agg={};S.pf.forEach(p=>{const v=(pmap[p.ticker]||p.entry)*p.qty;agg[p.ticker]=(agg[p.ticker]||0)+v});
 if(typeof Chart!=='undefined')pfPie=new Chart($('pfPie'),{type:'doughnut',
  data:{labels:Object.keys(agg),datasets:[{data:Object.values(agg),
   backgroundColor:['#e5b048','#3ea6ff','#26d07c','#a78bfa','#22d3ee','#ff4d6a','#ffa726','#7d8dac'],
   borderColor:'#0e1420',borderWidth:3}]},
  options:{plugins:{legend:{position:'bottom',labels:{color:'#9aa8c0',font:{size:11,family:'Inter'},boxWidth:10}}},cutout:'62%'}})}

async function addPosition(){
 const t=$('pfTicker').value.trim().toUpperCase(),q=parseFloat($('pfQty').value),e=parseFloat($('pfEntry').value);
 if(!t||!(q>0)||!(e>0)){toast('Fill in a symbol, quantity and entry price','err');return}
 const st=parseFloat($('pfStop').value);
 if(st>0&&st>=e){toast('The stop must be below the entry price','err');return}
 try{await store.addPf({ticker:t,qty:q,entry:e,notes:$('pfNotes').value,
   stop:st>0?st:null,init_stop:st>0?st:null,stop_type:'fixed'});
  ['pfTicker','pfQty','pfEntry','pfNotes','pfStop'].forEach(i=>$(i).value='');
  toast(t+(st>0?' added with a stop 🛡':' added — set a stop in the command centre'),'ok');
  loadPortfolio();loadPlan(true)}
 catch(err){toast(err.error||'Could not add the position','err')}}
async function delPosition(id){await store.delPf(id).catch(()=>{});loadPortfolio();loadPlan(true);toast('Position removed','info')}

/* ===================== watchlist ===================== */
async function renderWatch(){
 S.watch=await store.getWatch().catch(()=>[]);const g=$('wlGrid');
 if(!S.watch.length){g.innerHTML='<div class="empty" style="grid-column:1/-1"><div class="e-ic">★</div><h4>Nothing on the watchlist</h4><div style="font-size:13px">Press ★ on any stock card to follow it</div></div>';return}
 g.innerHTML=skelCards(Math.min(6,S.watch.length));
 let quotes=[];try{quotes=await api('/api/quotes?tickers='+S.watch.join(','))}catch(e){}
 g.innerHTML=quotes.map(q=>`<div class="glass wl-item" onclick="openChart('${esc(q.ticker)}')">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
   <b style="font-family:var(--mono);color:var(--gold)">${esc(q.ticker)}</b>
   <button class="iconbtn" onclick="event.stopPropagation();toggleWatch('${esc(q.ticker)}');renderWatch()" title="Remove">✕</button></div>
  <div style="font-family:var(--mono);font-size:21px;font-weight:600">${q.price!=null?'$'+fmt(q.price):'—'}</div>
  <div class="${cls(q.chg)}" style="font-family:var(--mono);font-size:13px;font-weight:600;margin-top:3px">${q.chg!=null?(q.chg>=0?'▲ +':'▼ ')+fmt(Math.abs(q.chg))+'%':''}</div>
  <canvas class="spark" data-s='${JSON.stringify(q.spark||[])}' height="38" style="margin-top:8px"></canvas></div>`).join('');
 requestAnimationFrame(()=>document.querySelectorAll('#wlGrid canvas').forEach(c=>{
  let d=[];try{d=JSON.parse(c.dataset.s)}catch(e){}
  if(d.length>1)sparkline(c,d,d[d.length-1]>=d[0]?'rgb(38,208,124)':'rgb(255,77,106)')}))}

/* ===================== compare ===================== */
async function runCompare(){
 const raw=$('cmpInput').value.split(',').map(s=>s.trim().toUpperCase()).filter(Boolean).slice(0,4);
 if(raw.length<2){toast('Enter at least two symbols','err');return}
 $('cmpBox').innerHTML='<div class="spinner"></div>';
 const res=await Promise.allSettled(raw.map(fetchStock));
 const st=res.filter(r=>r.status==='fulfilled').map(r=>r.value);
 if(st.length<2){$('cmpBox').innerHTML='<div class="empty"><h4>Not enough data to compare</h4></div>';return}
 const rows=[['Price',s=>'$'+fmt(s.price),null],
  ['Change today',s=>sign(s.chg)+'%',(a,b)=>a.chg>b.chg],
  ['RSI',s=>s.rsi,null],
  ['MACD',s=>s.macd==='BULLISH'?'Bullish ↑':'Bearish ↓',null],
  ['Volatility (ATR)',s=>s.atr_pct+'%',(a,b)=>a.atr_pct<b.atr_pct],
  ['Relative volume',s=>'×'+s.vol_ratio,null],
  ['Dividend yield',s=>s.dividend_yield?fmt(s.dividend_yield*100)+'%':'—',(a,b)=>(a.dividend_yield||0)>(b.dividend_yield||0)],
  ['Trend score',s=>s.trend_score,(a,b)=>(a.trend_score??0)>(b.trend_score??0)],
  ['Trend',s=>s.regime_label,null]];
 $('cmpBox').innerHTML=`<table class="cmp-table"><thead><tr><th>Metric</th>${st.map(s=>`<th style="color:var(--gold);font-family:var(--mono);font-size:13px">${esc(s.ticker)}</th>`).join('')}</tr></thead><tbody>
  ${rows.map(([lab,fn,better])=>{let bestIdx=-1;if(better){bestIdx=0;st.forEach((s,i)=>{if(better(s,st[bestIdx]))bestIdx=i})}
   return`<tr><td style="font-family:var(--ui);color:var(--tx2);text-align:left;font-weight:600">${lab}</td>${st.map((s,i)=>`<td class="${i===bestIdx?'cmp-best':''}">${fn(s)}</td>`).join('')}</tr>`}).join('')}
  </tbody></table>`}

/* ===================== alerts ===================== */
async function addAlert(){
 const t=$('alTicker').value.trim().toUpperCase(),c=$('alCond').value,p=parseFloat($('alPrice').value);
 if(!t||!(p>0)){toast('Fill in a symbol and a price','err');return}
 try{await store.addAlert({ticker:t,condition:c,price:p});$('alTicker').value=$('alPrice').value='';
  S.alerts=await store.getAlerts();renderAlerts();toast('Alert created 🔔','ok')}
 catch(e){toast(e.error||'Could not create the alert','err')}}
async function delAlert(id){await store.delAlert(id).catch(()=>{});S.alerts=await store.getAlerts();renderAlerts()}
function renderAlerts(){
 const box=$('alList');
 if(!S.alerts.length){box.innerHTML='<div class="empty"><div class="e-ic">🔔</div><h4>No active alerts</h4></div>';return}
 box.innerHTML=S.alerts.map(a=>`<div class="glass al-item" id="al-${a.id}">
  <div><b style="font-family:var(--mono);color:var(--gold)">${esc(a.ticker)}</b>
   <span style="font-size:13px;color:var(--tx2);margin-left:8px">${a.condition==='above'?'rises above':'falls below'} $${fmt(a.price)}</span></div>
  <button class="iconbtn" onclick="delAlert(${a.id})" title="Remove">🗑</button></div>`).join('')}
function checkAlerts(quotes){
 S.alerts.forEach(a=>{if(a.condition!=='above'&&a.condition!=='below')return;const q=quotes.find(x=>x.ticker===a.ticker);if(!q||q.price==null)return;
  const hit=a.condition==='above'?q.price>=a.price:q.price<=a.price;
  if(hit){const el=$('al-'+a.id);if(el)el.classList.add('hit');
   if(!a._notified){a._notified=true;toast(`🔔 ${a.ticker} crossed $${fmt(a.price)} — now $${fmt(q.price)}`,'ok')}}})}
/* ===================== news artwork =====================
   Most wire stories arrive without a picture. Rather than a decorative stock
   photo, each gets drawn art built from what the headline is about: the
   topic sets the motif and palette, the direction tints it, and the company
   logo is overlaid when one was identified. Deterministic, so the same story
   always looks the same. */
const ART_TOPICS={
 markets:{label:'Markets',a:'#3ea6ff',b:'#1b3a63'},
 rates:{label:'Rates',a:'#a78bfa',b:'#2d2550'},
 inflation:{label:'Inflation',a:'#ffa726',b:'#4a3012'},
 jobs:{label:'Labour',a:'#22d3ee',b:'#143c45'},
 energy:{label:'Energy',a:'#ffb547',b:'#4a3110'},
 crypto:{label:'Crypto',a:'#f7931a',b:'#43280a'},
 chips:{label:'Semis',a:'#26d07c',b:'#10402a'},
 ai:{label:'AI',a:'#60a5fa',b:'#1c2f55'},
 deal:{label:'M&A',a:'#e5b048',b:'#423010'},
 earnings:{label:'Earnings',a:'#38bdf8',b:'#123047'},
 policy:{label:'Policy',a:'#94a3b8',b:'#26303f'},
 housing:{label:'Housing',a:'#f472b6',b:'#45162c'},
 health:{label:'Health',a:'#34d399',b:'#10392b'},
};
/* A small deterministic hash, so a headline always draws the same shape. */
function artSeed(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return Math.abs(h)}

function artMotif(topic,col,seed,W,H){
 const rnd=(n=>()=>((n=Math.imul(n^n>>>15,2246822507))>>>0)/4294967296)(seed);
 const mid=H*0.6;
 /* Line weight and detail follow the size of the picture, so a 96px thumbnail
    and a hero panel both read as drawn for that box rather than scaled up. */
 const k=Math.max(.8,Math.min(2.6,H/150)),big=W>300;
 if(topic==='earnings'||topic==='jobs'||topic==='housing'){
  /* bars */
  let out='';const n=big?12:7,bw=W/(n*1.9);
  for(let i=0;i<n;i++){const h=H*(0.18+rnd()*0.46);
   out+=`<rect x="${(W*0.12+i*bw*1.75).toFixed(1)}" y="${(mid-h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="2" fill="${col}" opacity="${(0.35+i/n*0.6).toFixed(2)}"/>`}
  return out}
 if(topic==='rates'||topic==='inflation'||topic==='policy'){
  /* stepped curve: policy moves in steps, not smooth lines */
  let d=`M 0 ${mid}`,x=0,y=mid;const steps=big?9:6;
  for(let i=0;i<steps;i++){const nx=x+W/steps,ny=y-(rnd()-0.35)*H*0.26;
   d+=` L ${nx.toFixed(1)} ${y.toFixed(1)} L ${nx.toFixed(1)} ${ny.toFixed(1)}`;x=nx;y=Math.max(H*0.16,Math.min(H*0.82,ny))}
  d+=` L ${W} ${y.toFixed(1)}`;
  const fid='f'+seed.toString(36);
  return `<defs><linearGradient id="${fid}" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="${col}" stop-opacity=".30"/>
    <stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
   <path d="${d} L ${W} ${H} L 0 ${H} Z" fill="url(#${fid})" stroke="none"/>
   <path d="${d}" fill="none" stroke="${col}" stroke-width="${(2.4*k).toFixed(1)}" stroke-linejoin="round" opacity=".95"/>`}
 if(topic==='chips'||topic==='ai'){
  /* circuit traces */
  let out='';const rows=big?7:5,step=(big?0.10:0.14);
  for(let i=0;i<rows;i++){const y=H*(0.18+i*step),x1=W*(0.08+rnd()*0.2),x2=W*(0.55+rnd()*0.35);
   out+=`<path d="M ${x1.toFixed(0)} ${y.toFixed(0)} H ${(x2*0.7).toFixed(0)} L ${x2.toFixed(0)} ${(y-10*k).toFixed(0)}" fill="none" stroke="${col}" stroke-width="${(1.5*k).toFixed(1)}" opacity=".55"/>`+
        `<circle cx="${x2.toFixed(0)}" cy="${(y-10*k).toFixed(0)}" r="${(2.4*k).toFixed(1)}" fill="${col}" opacity=".9"/>`}
  out+=`<rect x="${(W*0.36).toFixed(0)}" y="${(H*0.3).toFixed(0)}" width="${(W*0.28).toFixed(0)}" height="${(H*0.36).toFixed(0)}" rx="${(4*k).toFixed(0)}" fill="none" stroke="${col}" stroke-width="${(1.9*k).toFixed(1)}" opacity=".7"/>`;
  return out}
 if(topic==='energy'){
  /* stacked flow bands */
  let out='';const bands=big?6:4;
  for(let i=0;i<bands;i++){const y=H*(0.26+i*(big?0.10:0.13));
   out+=`<path d="M 0 ${y.toFixed(0)} Q ${(W*0.3).toFixed(0)} ${(y-(18+rnd()*12)*k).toFixed(0)} ${(W*0.55).toFixed(0)} ${y.toFixed(0)} T ${W} ${(y-8*k).toFixed(0)}" fill="none" stroke="${col}" stroke-width="${(1.9*k).toFixed(1)}" opacity="${(0.25+i*0.12).toFixed(2)}"/>`}
  return out}
 if(topic==='deal'){
  /* two paths converging */
  const sw=(2.5*k).toFixed(1);
  return `<path d="M 0 ${(H*0.28).toFixed(0)} Q ${(W*0.42).toFixed(0)} ${(H*0.3).toFixed(0)} ${(W*0.52).toFixed(0)} ${mid.toFixed(0)}" fill="none" stroke="${col}" stroke-width="${sw}" opacity=".8"/>
   <path d="M 0 ${(H*0.82).toFixed(0)} Q ${(W*0.42).toFixed(0)} ${(H*0.8).toFixed(0)} ${(W*0.52).toFixed(0)} ${mid.toFixed(0)}" fill="none" stroke="${col}" stroke-width="${sw}" opacity=".5"/>
   <path d="M ${(W*0.52).toFixed(0)} ${mid.toFixed(0)} H ${(W*0.9).toFixed(0)}" fill="none" stroke="${col}" stroke-width="${sw}" opacity=".9"/>
   <circle cx="${(W*0.52).toFixed(0)}" cy="${mid.toFixed(0)}" r="${(4.6*k).toFixed(1)}" fill="${col}"/>`}
 if(topic==='crypto'){
  let out=`<circle cx="${(W*0.5).toFixed(0)}" cy="${(H*0.5).toFixed(0)}" r="${(H*0.22).toFixed(0)}" fill="none" stroke="${col}" stroke-width="${(2.3*k).toFixed(1)}" opacity=".75"/>`;
  for(let i=0;i<6;i++){const a=i*Math.PI/3,r1=H*0.24,r2=H*0.34;
   out+=`<line x1="${(W*0.5+Math.cos(a)*r1).toFixed(0)}" y1="${(H*0.5+Math.sin(a)*r1).toFixed(0)}" x2="${(W*0.5+Math.cos(a)*r2).toFixed(0)}" y2="${(H*0.5+Math.sin(a)*r2).toFixed(0)}" stroke="${col}" stroke-width="${(1.7*k).toFixed(1)}" opacity=".5"/>`}
  return out}
 /* default: candlesticks, the universal symbol of a market story */
 let out='';const n=big?16:9,cw=W/(n*1.8);
 for(let i=0;i<n;i++){const cx=W*0.1+i*cw*1.7,bh=H*(0.08+rnd()*0.26),cy=mid-H*0.12+(rnd()-0.5)*H*0.3;
  out+=`<line x1="${(cx+cw/2).toFixed(1)}" y1="${(cy-8).toFixed(1)}" x2="${(cx+cw/2).toFixed(1)}" y2="${(cy+bh+8).toFixed(1)}" stroke="${col}" stroke-width="${(1.1*k).toFixed(1)}" opacity=".5"/>`+
       `<rect x="${cx.toFixed(1)}" y="${cy.toFixed(1)}" width="${cw.toFixed(1)}" height="${bh.toFixed(1)}" rx="1.5" fill="${col}" opacity="${(0.4+i/n*0.5).toFixed(2)}"/>`}
 return out}

function artMeta(item){
 const art=item.art||{};
 const t=ART_TOPICS[art.topic]||ART_TOPICS.markets;
 const dir=art.direction;
 /* Direction tints the accent: the art should agree with the story. */
 return{label:t.label,base:t.b,dir,ticker:art.ticker||'',topic:art.topic||'markets',
  col:dir==='up'?'#26d07c':dir==='down'?'#ff4d6a':t.a}}

function newsArt(item,W,H){
 const art=item.art||{};
 const t=ART_TOPICS[art.topic]||ART_TOPICS.markets;
 const col=artMeta(item).col;
 const seed=artSeed(item.title||'');
 const gid='g'+seed.toString(36);
 return `<svg class="na-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
  <defs><linearGradient id="${gid}" x1="0" y1="0" x2="1" y2="1">
   <stop offset="0" stop-color="${t.b}"/><stop offset="1" stop-color="#0b1119"/></linearGradient></defs>
  <rect width="${W}" height="${H}" fill="url(#${gid})"/>
  <g opacity=".09">${Array.from({length:Math.ceil(W/24)},(_,i)=>`<line x1="${i*24}" y1="0" x2="${i*24}" y2="${H}" stroke="#fff" stroke-width=".5"/>`).join('')}</g>
  ${artMotif(art.topic||'markets',col,seed,W,H)}
 </svg>`}

/* A real photo when the feed carried one, drawn over the art; if it never
   loads it is removed and the art is what shows. The caption sits above both
   as HTML, so it is never cropped and can shorten itself when space is tight. */
function newsVisual(item,W,H,cls){
 const m=artMeta(item);
 const arrow=m.dir==='up'?'▲':m.dir==='down'?'▼':'';
 return `<span class="na ${cls}">${newsArt(item,W,H)}${item.image?
  `<img class="na-img" src="${esc(item.image)}" alt="" loading="lazy"
    onload="this.classList.add('ready')" onerror="this.remove()">`:''}
  <span class="na-cap${m.ticker?' has-sym':''}" style="--ac:${m.col}">
   <b>${esc(m.label)}</b>
   ${m.ticker?`<i class="${m.dir==='up'?'up':m.dir==='down'?'dn':''}">${arrow} ${esc(m.ticker)}</i>`
             :(arrow?`<i class="${m.dir==='up'?'up':'dn'}">${arrow}</i>`:'')}
  </span></span>`}

/* ===================== news ===================== */
let newsCache=[];
async function loadNews(scope,btn){
 scope=scope||'all';S.newsScope=scope;
 document.querySelectorAll('#newsScopes .btn').forEach(x=>x.className=x.className.replace('btn-gold','btn-ghost'));
 if(btn)btn.className=btn.className.replace('btn-ghost','btn-gold');
 $('newsBox').innerHTML=skeletonNews();$('newsFailed').innerHTML='';$('newsStamp').textContent='';
 try{
  let url='/api/news?scope='+scope;
  if(scope==='mine'&&!S.user){
   const mine=[...new Set([...S.pf.map(p=>p.ticker),...S.watch])].slice(0,6);
   url+='&tickers='+encodeURIComponent(mine.join(','))}
  const d=await api(url);
  newsCache=d.items||[];
  if(d.error&&!newsCache.length){
   $('newsBox').innerHTML=`<div class="empty"><div class="e-ic">★</div><h4>${esc(d.error)}</h4></div>`;return}
  renderNews();
  $('newsStamp').textContent=`${newsCache.length} stories · ${new Date().toLocaleTimeString('en-GB')}`;
  /* Feeds move and block; name the quiet ones instead of silently thinning out. */
  if(d.failed&&d.failed.length){
   const names=[...new Set(d.failed.map(f=>f.source))];
   $('newsFailed').innerHTML=`<div class="sub" style="margin-top:14px">Sources not responding right now: ${names.map(esc).join(' · ')}. The rest loaded normally.</div>`}}
 catch(e){$('newsBox').innerHTML=`<div class="empty"><div class="e-ic">⚠</div><h4>${esc(e.error||'Could not load the news')}</h4></div>`}}
function filterNews(){renderNews()}
function toneTag(n){const t=n.tone;if(!t||t.tone==='neutral')return'';
 return `<span class="tone t-${t.tone}" title="Machine-labelled from wording: ${esc((t.words||[]).join(', '))}">${t.tone==='positive'?'▲ positive':'▼ negative'}</span>`}
function renderNews(){
 const q=($('newsSearch').value||'').trim().toLowerCase(),tf=($('newsTone')&&$('newsTone').value)||'';
 const c={positive:0,negative:0,neutral:0};newsCache.forEach(n=>{const k=(n.tone&&n.tone.tone)||'neutral';c[k]=(c[k]||0)+1});
 if($('newsToneSum'))$('newsToneSum').textContent=newsCache.length?`Wording: ${c.positive} positive · ${c.negative} negative · ${c.neutral} neutral`:'';
 const list=newsCache.filter(n=>(!q||(n.title+' '+(n.summary||'')).toLowerCase().includes(q))&&(!tf||((n.tone&&n.tone.tone)||'neutral')===tf));
 if(!list.length){$('newsBox').innerHTML=`<div class="empty"><div class="e-ic">📰</div><h4>${q?'No headlines match that filter':'No news right now'}</h4></div>`;return}
 const[hero,...rest]=list;
 $('newsBox').innerHTML=`<div class="news-grid">
  <a class="glass news-hero" href="${esc(hero.link)}" target="_blank" rel="noopener noreferrer">
   <div class="nh-visual">${newsVisual(hero,560,360,'hero')}</div>
   <div class="nh-body"><span class="nh-kicker">${esc(hero.source||'')} · Top story</span>
    <div class="nh-title">${esc(hero.title)}</div>
    ${hero.summary?`<div class="nh-sum">${esc(hero.summary)}</div>`:''}
    <div class="nh-meta">${toneTag(hero)} ${timeAgo(hero.time)}</div></div></a>
  <div class="news-list">${rest.slice(0,14).map((n,i)=>`
   <a class="glass news-item" href="${esc(n.link)}" target="_blank" rel="noopener noreferrer">
    ${newsVisual(n,96,70,'thumb')}
    <div style="flex:1;min-width:0"><div class="ni-title">${esc(n.title)}</div>
     <div class="ni-meta"><span class="ni-num">${String(i+2).padStart(2,'0')}</span><span class="n-tag">${esc(n.source||'')}</span>${toneTag(n)}${timeAgo(n.time)}</div></div></a>`).join('')}</div></div>`}

/* ===================== gap detector ===================== */
async function loadGaps(scope,btn){
 scope=scope||'sp100';S.gapScope=scope;S.gapFilter=S.gapFilter||'all';
 document.querySelectorAll('#gapScopes .btn').forEach(x=>x.className=x.className.replace('btn-gold','btn-ghost'));
 if(btn)btn.className=btn.className.replace('btn-ghost','btn-gold');
 $('gapBox').innerHTML=skelRows(6);$('gapTiles').innerHTML='';$('gapStamp').textContent='';
 try{
  let url='/api/gaps?scope='+scope+'&min='+($('gapMin').value||1);
  if(scope==='mine'&&!S.user){
   const mine=[...new Set([...S.pf.map(p=>p.ticker),...S.watch])];
   url+='&tickers='+encodeURIComponent(mine.join(','));}
  const d=await api(url);
  S.gaps=d;
  if(d.error&&!(d.gaps||[]).length){
   $('gapBox').innerHTML=`<div class="empty"><div class="e-ic">★</div><h4>${esc(d.error)}</h4></div>`;return}
  renderGaps();
  $('gapStamp').textContent=`${d.scanned} scanned · ${new Date(d.generated_at*1000).toLocaleTimeString('en-GB')}`;
 }catch(e){$('gapBox').innerHTML=`<div class="empty"><div class="e-ic">⚠</div><h4>${esc(e.error||'Gap scan failed')}</h4></div>`}}

function setGapFilter(f,btn){S.gapFilter=f;
 document.querySelectorAll('#gapScopes .seg button').forEach(b=>b.classList.toggle('on',b===btn));
 renderGaps()}

function renderGaps(){
 const d=S.gaps;if(!d)return;
 const all=d.gaps||[];
 const unfilled=all.filter(g=>!g.filled).length;
 const biggest=all.length?Math.max(...all.map(g=>Math.abs(g.gap_pct||0))):null;
 $('gapTiles').innerHTML=`
  <div class="glass tile"><div class="t-lab">Gaps found</div><div class="t-val">${all.length}</div><div class="t-sub">of ${d.scanned} scanned</div></div>
  <div class="glass tile"><div class="t-lab">Gap up</div><div class="t-val up">${d.up}</div><div class="t-sub">opened higher</div></div>
  <div class="glass tile"><div class="t-lab">Gap down</div><div class="t-val dn">${d.down}</div><div class="t-sub">opened lower</div></div>
  <div class="glass tile"><div class="t-lab">Still unfilled</div><div class="t-val ${unfilled?'':'up'}">${unfilled}</div><div class="t-sub">${biggest!=null?'largest '+fmt(biggest,1)+'%':'—'}</div></div>`;

 const f=S.gapFilter||'all';
 const list=all.filter(g=>f==='all'||(f==='open'?!g.filled:g.direction===f));
 if(!list.length){$('gapBox').innerHTML=`<div class="empty"><div class="e-ic">⚡</div><h4>No gaps match this filter</h4><div style="font-size:13px">Nothing opened far enough from yesterday's close${f!=='all'?' in this category':''}</div></div>`;return}

 $('gapBox').innerHTML=list.map(g=>{
  const up=g.direction==='up';
  const col=up?'var(--up)':'var(--dn)';
  const fillPct=g.filled?100:(g.retrace_pct||0);
  return`<div class="glass gap-row ${g.direction}">
   <div class="gap-ic">${up?'▲':'▼'}</div>
   <div>
    <div class="gap-sym" onclick="openChart('${esc(g.ticker)}')">${esc(g.ticker)}</div>
    <div class="gap-pct ${up?'up':'dn'}">${sign(g.gap_pct,1)}%</div>
    <div class="gap-sub">${g.gap_atr!=null?fmt(g.gap_atr,1)+'× ATR':''}</div>
   </div>
   <div>
    <div class="gap-bar" title="${fmt(fillPct,0)}% of the gap retraced"><i style="width:${Math.min(100,fillPct)}%;background:${g.filled?'var(--tx3)':col}"></i></div>
    <div class="gap-meta">
     <span>prev close <b>$${fmt(g.prev_close)}</b></span>
     <span>open <b>$${fmt(g.open)}</b></span>
     <span>now <b>$${fmt(g.price)}</b></span>
     <span>fills at <b>$${fmt(g.fill_level)}</b></span>
     <span>from open <b class="${cls(g.from_open_pct)}">${sign(g.from_open_pct,1)}%</b></span>
     <span>vol <b>×${fmt(g.vol_ratio,1)}</b></span>
    </div>
   </div>
   <div class="gap-acts">
    <span class="gap-badge ${g.filled?'filled':'open'}">${g.filled?'Filled':'Unfilled'}</span>
    <span class="gap-badge ${g.held?'held':'faded'}">${g.held?'Held':'Faded'}</span>
    <button class="btn btn-ghost btn-sm" onclick="openChart('${esc(g.ticker)}')">Chart</button>
   </div></div>`}).join('')}

/* ===================== backtest ===================== */
let btChart=null;
async function runBacktest(ticker,years){
 const t=(ticker||$('btTicker').value||'').trim().toUpperCase();
 if(!t){toast('Enter a symbol','err');return}
 $('btTicker').value=t;if(years)$('btYears').value=String(years);
 const y=$('btYears').value;
 $('btBox').innerHTML='<div class="bt-stats">'+skelRows(5)+'</div>'+skelRows(2);$('btStamp').textContent='';
 try{
  const risk=(S.settings&&S.settings.risk_pct)||1;
  const b=await api(`/api/engine/backtest/${encodeURIComponent(t)}?years=${y}&risk_pct=${risk}`);
  if(!b.ok){$('btBox').innerHTML=`<div class="bt-empty">${esc(b.error||'Cannot backtest this symbol')}</div>`;return}
  S.bt=b;renderBacktest(b)}
 catch(e){$('btBox').innerHTML=`<div class="bt-empty">${esc(e.error||'Backtest failed')}</div>`}}
function btGo(t){go('backtest');runBacktest(t)}
function renderBacktest(b){
 const s=b.stats,edge=s.system_dd!=null&&s.hold_dd!=null?s.hold_dd-s.system_dd:null;
 $('btStamp').textContent=`${b.from} — ${b.to} · ${b.years}y · ${s.cost_pct}% cost per side`;
 $('btBox').innerHTML=`
 <div class="bt-stats">
  <div class="bt-stat"><div class="bt-k">Trades</div><div class="bt-v">${s.count}</div><div class="bt-note">${s.avg_bars!=null?'~'+s.avg_bars+' days each':''}</div></div>
  <div class="bt-stat"><div class="bt-k">Win rate</div><div class="bt-v">${s.win_rate!=null?fmt(s.win_rate,0)+'%':'—'}</div><div class="bt-note">${s.wins}/${s.count} winners</div></div>
  <div class="bt-stat"><div class="bt-k">Expectancy</div><div class="bt-v ${cls(s.expectancy_r)}">${s.expectancy_r!=null?sign(s.expectancy_r)+'R':'—'}</div><div class="bt-note">per trade, in risk units</div></div>
  <div class="bt-stat"><div class="bt-k">Worst trade</div><div class="bt-v ${cls(s.worst_r)}">${s.worst_r!=null?sign(s.worst_r)+'R':'—'}</div><div class="bt-note">${s.worst_r!=null&&s.worst_r>=0?'even the worst won':'how the stop capped it'}</div></div>
  <div class="bt-stat"><div class="bt-k">Exposure</div><div class="bt-v">${s.exposure_pct!=null?fmt(s.exposure_pct,0)+'%':'—'}</div><div class="bt-note">of the time in a position</div></div>
 </div>
 <div class="bt-vs">
  <div class="bt-col sys"><h4>🎯 This system</h4>
   <div class="bt-line"><span>Return</span><b class="${cls(s.system_return)}">${sign(s.system_return,1)}%</b></div>
   <div class="bt-line"><span>Max drawdown</span><b class="dn">−${fmt(s.system_dd,1)}%</b></div></div>
  <div class="bt-col"><h4>📈 Buy and hold</h4>
   <div class="bt-line"><span>Return</span><b class="${cls(s.hold_return)}">${sign(s.hold_return,1)}%</b></div>
   <div class="bt-line"><span>Max drawdown</span><b class="dn">−${fmt(s.hold_dd,1)}%</b></div></div>
 </div>
 ${edge!=null?`<div class="ent-size" style="margin-bottom:14px">${edge>0
   ?`The system's worst drawdown was <b>${fmt(edge,1)} percentage points shallower</b> than buy-and-hold. That is what stops actually buy you: not a higher return, but <b>less pain on the way</b> — which is what makes a plan survivable.`
   :`Buy-and-hold had the shallower drawdown over this window. In an uninterrupted uptrend stops mostly take you out early — that is the other side of the trade-off, and worth seeing.`}</div>`:''}
 <div class="bt-legend"><span><i style="background:#e5b048"></i>System</span><span><i style="background:#7d8dac"></i>Buy and hold</span><span style="margin-left:auto">Starting value 100</span></div>
 <div class="glass" style="padding:14px"><div class="bt-chart"><canvas id="btCanvas"></canvas></div></div>
 ${b.trades.length?`<div class="sec" style="margin-top:22px">Trades <span class="tag">${b.trades.length}</span></div>
 <div class="glass tbl-wrap"><table class="risk-tbl"><thead><tr><th>Entered</th><th>Exited</th><th>Days</th><th>Setup</th><th>Entry</th><th>Stop</th><th>Exit</th><th>Return</th><th>R</th></tr></thead><tbody>
 ${b.trades.map(t=>`<tr><td>${t.entry_date}</td><td>${t.exit_date}</td><td>${t.bars}</td>
  <td style="font-family:var(--ui);font-size:11.5px;color:var(--tx2)">${esc(t.setup_he||t.setup)}</td>
  <td>$${fmt(t.entry)}</td><td class="dn">$${fmt(t.stop)}</td><td>$${fmt(t.exit)}</td>
  <td class="${cls(t.return_pct)}">${sign(t.return_pct,1)}%</td>
  <td><span class="rpill ${cls(t.r)}">${t.r!=null?sign(t.r)+'R':'—'}</span></td></tr>`).join('')}
 </tbody></table></div>`:'<div class="bt-empty">These rules found no entry at all in this window — usually a sign the stock was not in an uptrend.</div>'}
 <div class="sub" style="margin-top:16px">Past results promise nothing about the future, and a small number of trades is not evidence. The test includes ${s.cost_pct}% cost per side and assumes a fixed ${(S.settings&&S.settings.risk_pct)||1}% of the account risked per trade.</div>`;
 drawBtChart(b)}
function drawBtChart(b){
 if(typeof Chart==='undefined'){const box=$('btCanvas');
  if(box&&box.parentElement)box.parentElement.innerHTML='<div class="bt-empty">The charting library did not load — the numbers above are complete, only the curve is missing.</div>';
  return}
 if(btChart){btChart.destroy();btChart=null}
 const step=Math.max(1,Math.floor(b.dates.length/420));
 const pick=a=>a.filter((_,i)=>i%step===0);
 btChart=new Chart($('btCanvas'),{type:'line',
  data:{labels:pick(b.dates),datasets:[
   {label:'System',data:pick(b.curve),borderColor:'#e5b048',backgroundColor:'rgba(229,176,72,.10)',borderWidth:2,pointRadius:0,tension:.15,fill:true},
   {label:'Buy and hold',data:pick(b.hold_curve),borderColor:'#7d8dac',borderWidth:1.5,pointRadius:0,tension:.15,borderDash:[5,4]}]},
  options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false},
   plugins:{legend:{display:false},tooltip:{backgroundColor:'#141c2c',borderColor:'#2b3a52',borderWidth:1,
    titleFont:{family:'JetBrains Mono',size:11},bodyFont:{family:'JetBrains Mono',size:11},
    callbacks:{label:c=>` ${c.dataset.label}: ${fmt(c.parsed.y,1)}`}}},
   scales:{x:{ticks:{color:'#7d8dac',font:{size:9,family:'JetBrains Mono'},maxTicksLimit:8},grid:{display:false}},
    y:{ticks:{color:'#7d8dac',font:{size:9,family:'JetBrains Mono'}},grid:{color:'rgba(255,255,255,.05)'}}}}})}
/* ===================== glossary: English terms, Hebrew explanations ===================== */
const GLOSSARY=[
['RSI','מדד עוצמה יחסית','מודד מהירות שינויי מחיר בין 0 ל־100. מתחת ל־30 המניה נחשבת במכירת יתר (הזדמנות אפשרית), מעל 70 בקניית יתר (זהירות).'],
['MACD','התכנסות/התבדרות ממוצעים','ההפרש בין ממוצע נע 12 ל־26. כשקו ה־MACD חוצה את קו האיתות כלפי מעלה — מומנטום חיובי.'],
['ATR','טווח אמיתי ממוצע','מודד תנודתיות. ATR גבוה = תנועות מחיר חדות. משמש לקביעת סטופ־לוס מרוחק מרעשי שוק.'],
['ADX','עוצמת מגמה','מודד כמה המגמה חזקה (לא לאיזה כיוון). מעל 25 = מגמה ברורה; מתחת ל־20 = דשדוש שבו איתותי מגמה נוטים להיכשל.'],
['Bollinger Bands','רצועות בולינגר','ממוצע נע ± שתי סטיות תקן. מחיר בקצה הרצועה התחתונה עשוי לרמז על מכירת יתר.'],
['Support','תמיכה','רמת מחיר שבה ביקוש עצר ירידות בעבר. שבירה שלה — איתות שלילי.'],
['Resistance','התנגדות','רמת מחיר שבה היצע עצר עליות בעבר. פריצה שלה — איתות חיובי.'],
['Stop Loss','סטופ לוס','פקודת מכירה אוטומטית להגבלת הפסד. במערכת מחושב מתחת לשפל האחרון ועל פי מכפלת ATR.'],
['Trailing Stop','סטופ נגרר','סטופ שמטפס אוטומטית עם עליית המחיר ולעולם לא יורד. מחושב בשיטת Chandelier: השיא של 22 הימים האחרונים פחות מכפלת ATR.'],
['Chandelier Exit','יציאת נברשת','שיטת הטריילינג סטופ שבה המערכת משתמשת: הסטופ "תלוי" מהשיא האחרון כמו נברשת מהתקרה, במרחק 2.5–3 ATR.'],
['R Multiple','מכפיל R','הרווח הנוכחי ביחידות הסיכון המקורי. אם סיכנת $2 למניה והמחיר עלה $6 — זה 3R. הכלי החשוב ביותר: הוא מנטרל את גודל הפוזיציה ומשווה עסקאות על אותו סרגל.'],
['Breakeven Stop','סטופ בנקודת איזון','העלאת הסטופ למחיר הכניסה אחרי שהעסקה הרוויחה לפחות 1R. מרגע זה העסקה אינה יכולה להפוך להפסד.'],
['Portfolio Heat','חום התיק','סך הכסף שתפסיד אם כל הסטופים בתיק ייפגעו יחד, כאחוז משווי התיק. מקובל לשמור מתחת ל־6%.'],
['Position Sizing','גודל פוזיציה','כמה מניות לקנות. מחושב מהסיכון: (שווי תיק × אחוז סיכון) ÷ (מחיר כניסה − סטופ). כך ההפסד המקסימלי זהה בכל עסקה.'],
['Max Drawdown','ירידה מקסימלית','הירידה העמוקה ביותר משיא לשפל. המספר שקובע אם תצליח להישאר בתוכנית כשקשה — לרוב חשוב יותר מהתשואה.'],
['Expectancy','תוחלת','הרווח הממוצע לעסקה ביחידות R. תוחלת חיובית אומרת שהשיטה משתלמת לאורך מספיק עסקאות.'],
['MA200','ממוצע נע 200','ממוצע מחיר הסגירה של 200 ימי המסחר האחרונים — קו הגבול בין מגמה ראשית עולה ליורדת.'],
['Golden Cross','צלב זהב','ממוצע 50 חוצה מעל ממוצע 200 — איתות קלאסי לשינוי מגמה ארוך־טווח. ההפך, Death Cross, מסמן היחלשות.'],
['Volume Ratio','נפח יחסי','נפח המסחר היום מול הממוצע. מעל ×1.4 = עניין חריג במניה.'],
['Dividend Yield','תשואת דיבידנד','אחוז החלוקה השנתית מהמחיר. Ex-Date הוא היום הקובע לזכאות.'],
['Fear & Greed','מדד פחד ותאווה','מדד הסנטימנט של CNN בין 0 (פחד קיצוני) ל־100 (תאווה קיצונית), המשוקלל משבעה מדדי שוק. קיצוניות היא לרוב איתות מנוגד.'],
['Market Cap','שווי שוק','שווי כל מניות החברה יחד: מחיר × מספר מניות. מודד את גודל החברה, וקובע את גודל הריבוע במפת החום.'],
['Gap','גאפ · פער פתיחה','ההפרש בין מחיר הפתיחה היום למחיר הסגירה אתמול — טווח מחירים שבו לא נסחרה אף מניה. גאפ אפ נפתח מעל, גאפ דאון מתחת.'],
['Gap Fill','סגירת גאפ','מצב שבו המחיר חוזר במהלך היום לרמת הסגירה של אתמול ו"ממלא" את הפער. גאפ שלא נסגר משאיר אחריו רמת מחיר שלא נבחנה; גאפ שנסגר כבר נדחה על ידי השוק.'],
['Gap in ATR','גאפ ביחידות ATR','גודל הגאפ ביחס לתנועה היומית הרגילה של המניה. 2% הם שגרה במניה אחת וזעזוע באחרת — ולכן המדידה הזו משמעותית יותר מהאחוז לבדו.'],
['Trend Template','תבנית מגמה','מבנה שבו ממוצע 50 מעל 150 מעל 200 וכולם עולים. נחשב לסימן המובהק למגמת עלייה בריאה, ומשמש במערכת לסיווג "מגמת עלייה חזקה".'],
['Backtest','בדיקה היסטורית','הרצת כללי המסחר על נתוני עבר כדי לראות מה הם היו עושים. חשוב: תוצאות עבר אינן מבטיחות דבר.'],
['Lookahead Bias','הטיית הצצה קדימה','טעות נפוצה בבדיקות היסטוריות: שימוש במידע שלא היה זמין באותו רגע. המערכת נמנעת מזה — איתות בסגירה נכנס בפתיחה שלמחרת.'],
];
function buildGloss(){$('glBody').innerHTML=GLOSSARY.map(([t,he,def])=>
 `<div class="gl-item"><div class="gl-term">${t}</div><div class="gl-he">${he}</div><div class="gl-def">${def}</div></div>`).join('')}
function toggleGloss(){$('gloss').classList.toggle('open')}

/* ===================== keyboard ===================== */
const SHORTCUTS=[['Ctrl / ⌘ + K','Search any stock'],['1 – 9','Switch section'],
 ['G','Glossary'],['R','Refresh the plan'],['F','Fullscreen chart'],['?','This panel'],['Esc','Close']];
function toggleShortcuts(){
 let el=$('shortcuts');
 if(el){el.remove();return}
 el=document.createElement('div');el.id='shortcuts';el.className='modal open';
 el.onclick=ev=>{if(ev.target===el)el.remove()};
 el.innerHTML=`<div class="glass sc-box"><div class="sc-hdr"><h3>Keyboard shortcuts</h3><button class="x-btn" onclick="toggleShortcuts()">✕</button></div>
  ${SHORTCUTS.map(([k,d])=>`<div class="sc-row"><kbd>${k}</kbd><span>${d}</span></div>`).join('')}</div>`;
 document.body.appendChild(el)}

document.addEventListener('keydown',e=>{
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openCmdk();return}
 if(e.key==='Escape'){closeCmdk();closeChart();closeProfile();const s=$('shortcuts');if(s)s.remove();return}
 /* Never steal a key while the user is typing. */
 const t=e.target,typing=t&&(t.tagName==='INPUT'||t.tagName==='TEXTAREA'||t.tagName==='SELECT'||t.isContentEditable);
 if(typing||e.ctrlKey||e.metaKey||e.altKey)return;
 if(e.key>='1'&&e.key<='9'){const v=VIEWS[+e.key-1];if(v){e.preventDefault();go(v)}return}
 const k=e.key.toLowerCase();
 if(k==='g'){e.preventDefault();toggleGloss()}
 else if(k==='r'&&$('v-command').classList.contains('on')){e.preventDefault();loadPlan(true)}
 else if(k==='f'&&$('chartModal').classList.contains('open')){e.preventDefault();toggleChartFull()}
 else if(e.key==='?'){e.preventDefault();toggleShortcuts()}});

$('cmdkInput').addEventListener('input',e=>{
 clearTimeout(cmdkTimer);const q=e.target.value.trim();
 if(!q){$('cmdkList').innerHTML='';return}
 cmdkTimer=setTimeout(async()=>{
  try{const res=await api('/api/search?q='+encodeURIComponent(q));
   S.cmdkSel=0;
   $('cmdkList').innerHTML=res.length?res.map((r,i)=>
    `<div class="cmdk-item ${i===0?'on':''}" onclick="pickCmdk('${esc(r.symbol)}')">
      <span class="sym">${esc(r.symbol)}</span><span class="nm">${esc(r.name)}</span><span class="ex">${esc(r.exch)}</span></div>`).join('')
    :'<div class="cmdk-item"><span class="nm">No matches</span></div>'}
  catch(err){}},230)});
$('cmdkInput').addEventListener('keydown',e=>{
 const items=[...document.querySelectorAll('.cmdk-item')];
 if(!items.length){if(e.key==='Enter'&&e.target.value.trim())pickCmdk(e.target.value.trim().toUpperCase());return}
 if(e.key==='ArrowDown'){e.preventDefault();S.cmdkSel=Math.min(items.length-1,S.cmdkSel+1)}
 else if(e.key==='ArrowUp'){e.preventDefault();S.cmdkSel=Math.max(0,S.cmdkSel-1)}
 else if(e.key==='Enter'){e.preventDefault();items[S.cmdkSel]&&items[S.cmdkSel].click();return}
 else return;
 items.forEach((it,i)=>it.classList.toggle('on',i===S.cmdkSel));
 items[S.cmdkSel].scrollIntoView({block:'nearest'})});
$('cmdk').addEventListener('click',e=>{if(e.target.id==='cmdk')closeCmdk()});
$('chartModal').addEventListener('click',e=>{if(e.target.id==='chartModal')closeChart()});
let hmResize=null;
window.addEventListener('resize',()=>{clearTimeout(hmResize);hmResize=setTimeout(()=>{if(S.hm&&$('v-heatmap').classList.contains('on'))renderHeatmap()},220)});

/* ===================== boot ===================== */
document.addEventListener('DOMContentLoaded',()=>{
 buildGloss();tickClock();setInterval(tickClock,1000);
 checkAuth();loadIndices();loadTapeAndBento();loadFearGreed();
 loadPreset('us',document.querySelector('#v-home .filters .btn'));
 setInterval(()=>{loadTapeAndBento();loadIndices()},60000);
 setInterval(loadFearGreed,900000);
 setInterval(()=>{if($('v-command').classList.contains('on'))loadPlan(false)},300000);
 if('serviceWorker'in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
});
