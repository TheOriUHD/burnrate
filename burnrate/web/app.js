'use strict';
/* Burnrate UI: #/ overview, #/p/<provider> one provider, #/a/<id> account, #/settings. Vanilla JS, no build step. */
const $=id=>document.getElementById(id);
const NS='http://www.w3.org/2000/svg';
function el(n,a,p){const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);if(p)p.appendChild(e);return e}
const LOC=navigator.language||'en-GB';
const NARROW=()=>innerWidth<620;
const f1=v=>v==null?'–':(Math.round(v*10)/10).toLocaleString(LOC);
const pc=v=>v==null?'–':f1(v)+' %';
const dt=(t,o)=>new Date(t*1000).toLocaleString(LOC,o);
const fmtT=t=>dt(t,{weekday:'short',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
const ago=t=>{const s=Math.round(Date.now()/1000-t);return s<90?s+' s ago':s<5400?Math.round(s/60)+' min ago':s<172800?Math.round(s/3600)+' h ago':Math.round(s/86400)+' d ago'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=(v,c)=>{if(v==null)return '–';try{return v.toLocaleString(LOC,{style:'currency',currency:c||'USD',maximumFractionDigits:Math.abs(v)<10?2:0})}catch(e){return f1(v)+' '+(c||'')}};
const amount=(v,c)=>/^[A-Z]{3}$/.test(c||'')?money(v,c):(v==null?'–':(Math.round(v*100)/100).toLocaleString(LOC)+' '+esc(c||''));
function until(t){let s=Math.max(0,t-Date.now()/1000);const d=Math.floor(s/86400);s-=d*86400;const h=Math.floor(s/3600),m=Math.floor((s-h*3600)/60);
  return d?d+'d '+h+'h':h?h+'h '+String(m).padStart(2,'0')+'m':m+' min'}
const ICON={good:'<svg viewBox="0 0 16 16"><path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
 warn:'<svg viewBox="0 0 16 16"><path d="M8 2l6.5 12h-13z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M8 6.5v3.5M8 12v.01" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
 crit:'<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8 4.5v4.5M8 11.3v.01" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
 gear:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>',
 plus:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
 back:'<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 3L5 8l5 5"/></svg>',
 x:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
 refresh:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.6-6.4M21 4v5h-5"/></svg>',
 logo:'<svg viewBox="0 0 32 32"><circle cx="16" cy="16" r="12" fill="none" stroke="var(--line)" stroke-width="4"/><path d="M16 4a12 12 0 0 1 11.4 15.7" fill="none" stroke="var(--use)" stroke-width="4" stroke-linecap="round"/></svg>'};
/* breakdown colours: fixed order, colour follows the key */
const PAL=['var(--use)','var(--time)','var(--aqua)','var(--violet)','var(--gold)','var(--gray)'];
let KEYS=[],NAMES={};
const col=k=>k==='_total'?'var(--gray)':PAL[Math.max(0,KEYS.indexOf(k))%PAL.length];

const S={session:null,providers:null,data:null,timer:null,tick:null};

/* ---------- api ---------- */
async function api(path,body){
  const r=await fetch(path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  let d={};try{d=await r.json()}catch(e){}
  if(r.status===401&&!path.startsWith('/api/login')&&!path.startsWith('/api/first-run')){S.session=null;boot();throw new Error('login required')}
  if(!r.ok)throw new Error(d.error||('HTTP '+r.status));
  return d;
}
function toast(msg,bad){const t=$('toast');t.textContent=msg;t.className='on'+(bad?' bad':'');clearTimeout(t._h);t._h=setTimeout(()=>t.className=bad?'bad':'',bad?6000:2600)}
const tip=$('tip');
function showTip(ev,html){tip.innerHTML=html;tip.style.display='block';const w=tip.offsetWidth;let x=ev.clientX+14;if(x+w>innerWidth-8)x=ev.clientX-w-14;tip.style.left=x+'px';tip.style.top=Math.max(6,ev.clientY-14-tip.offsetHeight)+'px'}
function hideTip(){tip.style.display='none'}
function hover(node,fn){node.addEventListener('mousemove',ev=>showTip(ev,fn()));node.addEventListener('mouseleave',hideTip)}
function mono(p,cls){return '<span class="mono-b '+(cls||'')+'" style="--c:'+esc(p.color)+'" aria-hidden="true">'+esc(p.mono)+'</span>'}
function theme(t){const r=document.documentElement;if(t==='dark'||t==='light')r.dataset.theme=t;else delete r.dataset.theme;try{localStorage.setItem('br-theme',t||'auto')}catch(e){}}
try{theme(localStorage.getItem('br-theme'))}catch(e){}

/* ---------- boot / routing ---------- */
async function boot(){
  try{S.session=await api('/api/session')}catch(e){$('app').innerHTML='<div class="banner">'+ICON.crit+'<div>Cannot reach Burnrate: '+esc(e.message)+'</div></div>';return}
  if(S.session.setup_needed)return firstRun();
  if(!S.session.logged_in)return login();
  route();
}
addEventListener('hashchange',()=>{closeModal();route()});
function route(){
  if(!S.session||!S.session.logged_in)return;
  clearInterval(S.timer);hideTip();
  const h=location.hash.replace(/^#\/?/,'').split('/');
  if(h[0]==='a'&&h[1])return accountPage(+h[1]);
  if(h[0]==='settings')return settingsPage().then(()=>{if(h[1]==='add')addAccount(h[2]||null)});
  return overviewPage(h[0]==='p'?h[1]:null);
}
function topbar(extra){
  return '<div class="top"><a class="brand" href="#/" style="text-decoration:none">'+ICON.logo+esc(S.session.title||'Burnrate')+'</a><div class="nav">'+
    (S.session.demo?'<span class="pill" title="Made-up accounts; polling is off. Start with an empty data directory for real use.">Demo data</span>':'')+(extra||'')+
    '<a class="iconbtn" href="#/settings" title="Settings" aria-label="Settings">'+ICON.gear+'</a></div></div>';
}
function login(){
  document.title='Sign in · Burnrate';
  $('app').innerHTML='<div class="login card"><div class="brand">'+ICON.logo+'Burnrate</div><h1>Welcome back.</h1><p class="sub">Enter the password for this Burnrate instance.</p>'+
    '<form id="lf"><input type="password" id="pw" autocomplete="current-password" placeholder="Password" required autofocus><button>Sign in</button><div id="lerr" class="bad"></div></form></div>';
  $('lf').onsubmit=async e=>{e.preventDefault();try{await api('/api/login',{password:$('pw').value});boot()}catch(x){$('lerr').textContent=x.message}};
}
function firstRun(){
  document.title='Set up · Burnrate';
  $('app').innerHTML='<div class="login card"><div class="brand">'+ICON.logo+'Burnrate</div><h1>First run.</h1>'+
    '<p class="sub">Choose a password for this instance. To prove you run it, enter the setup code printed in the server log '+
    '(<code>docker logs burnrate</code> or <code>journalctl -u burnrate</code>).</p>'+
    '<form id="ff"><input id="code" autocomplete="off" placeholder="Setup code (xxxx-xxxx-xxxx)" required><input type="password" id="p1" autocomplete="new-password" placeholder="New password (8+ characters)" minlength="8" required>'+
    '<input type="password" id="p2" autocomplete="new-password" placeholder="Repeat password" required><button>Save and continue</button><div id="lerr" class="bad"></div></form></div>';
  $('ff').onsubmit=async e=>{e.preventDefault();if($('p1').value!==$('p2').value){$('lerr').textContent='The passwords differ.';return}
    try{await api('/api/first-run',{code:$('code').value,password:$('p1').value});boot()}catch(x){$('lerr').textContent=x.message}};
}

/* ---------- shared bits ---------- */
function prim(a){return (a.windows||[]).find(w=>w.id===a.primary)||(a.windows||[])[0]}
function statusOf(a){
  if(!a.connected)return ['err','not connected'];
  if(a.error)return ['err','failing'];
  if(!a.last_ok)return ['stale','waiting'];
  if(Date.now()/1000-a.last_ok>3*(a.interval||300)+60)return ['stale',ago(a.last_ok)];
  return ['live',ago(a.last_ok)];
}
function verdictHTML(state){const w=(state||'').split(' ');return w.length>1?esc(w.slice(0,-1).join(' '))+' <em>'+esc(w[w.length-1])+'.</em>':'<em>'+esc(state)+'</em>'}
function periodWord(w){const p=w.period;if(!p)return 'this period';if(p<=6*3600)return 'this session';if(p<=26*3600)return 'today';if(p<=8*86400)return 'this week';if(p<=32*86400)return 'this month';return 'this period'}
function ringSVG(size,w,inner,outer,stroke){
  const c=size/2,r1=c-outer/2-1,r2=r1-outer/2-5-inner/2,u=Math.min(w.pct||0,100),e=Math.min(w.elapsed||0,100);
  const C1=2*Math.PI*r1,C2=2*Math.PI*r2,lvl=w.level==='crit'?'var(--crit)':'var(--use)';
  return '<svg viewBox="0 0 '+size+' '+size+'" aria-hidden="true"><circle cx="'+c+'" cy="'+c+'" r="'+r1+'" fill="none" stroke="var(--surface-2)" stroke-width="'+outer+'"/>'+
    (w.elapsed!=null?'<circle class="arc" cx="'+c+'" cy="'+c+'" r="'+r1+'" fill="none" stroke="var(--time)" stroke-width="'+outer+'" stroke-linecap="round" stroke-dasharray="'+C1+'" stroke-dashoffset="'+C1*(1-e/100)+'"/>':'')+
    '<circle cx="'+c+'" cy="'+c+'" r="'+r2+'" fill="none" stroke="var(--surface-2)" stroke-width="'+inner+'"/>'+
    '<circle class="arc" cx="'+c+'" cy="'+c+'" r="'+r2+'" fill="none" stroke="'+lvl+'" stroke-width="'+inner+'" stroke-linecap="round" stroke-dasharray="'+C2+'" stroke-dashoffset="'+C2*(1-u/100)+'"/></svg>';
}
function track(pct,elapsed,lvl,off){return '<div class="track"><i class="'+(off?'off':lvl==='crit'?'crit':lvl==='warn'?'warn':'')+'" style="width:'+Math.min(Math.max(pct||0,0),100)+'%"></i>'+
  (elapsed!=null?'<b style="left:calc('+Math.min(elapsed,100)+'% - 1px)" title="share of the window gone"></b>':'')+'</div>'}
function winRow(w){
  const off=w.note==='inactive',sub=[];
  if(w.used!=null&&w.limit!=null)sub.push(f1(w.used)+' / '+f1(w.limit)+(w.unit?' '+w.unit:''));
  if(w.resets)sub.push('resets in '+until(w.resets));
  if(w.forecast&&w.projected!=null)sub.push('forecast '+Math.round(w.projected)+' %');
  if(w.note)sub.push(w.note);
  return '<div class="wrow"><span class="n">'+esc(w.label)+'</span><span class="num">'+pc(w.pct)+'</span>'+track(w.pct,w.elapsed,w.level,off)+
    (sub.length?'<span class="s">'+esc(sub.join(' · '))+'</span>':'')+'</div>';
}
function balRow(b){
  const sub=[];
  if(b.limit!=null)sub.push((b.kind==='spent'?'of ':'of ')+amount(b.limit,b.currency)+(b.kind==='spent'?' cap':''));
  if(b.per_day)sub.push(amount(b.per_day,b.currency)+'/day');
  if(b.runway_days!=null)sub.push('lasts ~'+(b.runway_days>99?'99+':Math.round(b.runway_days))+' days');
  if(b.note)sub.push(b.note);
  return '<div class="wrow"><span class="n">'+esc(b.label)+(b.kind==='spent'?' (spent)':'')+'</span><span class="num">'+amount(b.amount,b.currency)+'</span>'+
    (b.pct!=null?track(b.pct,null,b.pct>=90?'crit':b.pct>=75?'warn':''):'')+(sub.length?'<span class="s">'+esc(sub.join(' · '))+'</span>':'')+'</div>';
}
function sparkSVG(v){
  if(!v||!v.some(x=>x>0))return '';
  const W=300,H=34,m=Math.max(...v),bw=W/v.length;
  return '<svg class="spark" viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none" aria-label="use per hour, last 24 hours">'+
    v.map((x,i)=>x>0?'<rect x="'+(i*bw+1).toFixed(1)+'" y="'+(H-Math.max(2,H*x/m)).toFixed(1)+'" width="'+(bw-2).toFixed(1)+'" height="'+Math.max(2,H*x/m).toFixed(1)+'" rx="1.5" fill="var(--use)" opacity="'+(0.35+0.65*x/m).toFixed(2)+'"/>':'').join('')+'</svg>';
}

/* ---------- overview ---------- */
async function overviewPage(filter){
  document.title=(S.session.title||'Burnrate');
  let d;try{d=await api('/api/overview')}catch(e){return}
  S.data=d;
  const accs=d.accounts.filter(a=>a.enabled);
  const provs=[...new Map(accs.map(a=>[a.provider,{id:a.provider,name:a.provider_name,color:a.color,mono:a.mono}])).values()];
  const shown=filter?accs.filter(a=>a.provider===filter):accs;
  let h=topbar();
  if(!d.accounts.length){
    h+='<section class="card welcome">'+ICON.logo.replace('<svg','<svg width="56" height="56"')+'<h2>Track every AI plan in one place.</h2>'+
      '<p>Connect your subscriptions and API accounts — Claude, ChatGPT, Copilot, Cursor, Gemini, OpenRouter and many more. Burnrate polls them, keeps the history and tells you whether you are on pace.</p>'+
      '<button id="add1">'+'Add your first account</button></section>';
    $('app').innerHTML=h;$('add1').onclick=()=>addAccount();return;
  }
  const hot=accs.filter(a=>{const w=prim(a);return w&&w.level&&w.level!=='good'}).length;
  const failing=accs.filter(a=>a.error||!a.connected).length;
  const next=accs.map(a=>({a,w:prim(a)})).filter(x=>x.w&&x.w.resets).sort((x,y)=>x.w.resets-y.w.resets)[0];
  const fp=filter&&provs.find(p=>p.id===filter);
  h+='<div class="pagehead"><div><p class="eyebrow">'+(fp?'Provider':'Overview')+'</p><h1>'+(fp?esc(fp.name):'All <em>accounts</em>')+'</h1></div></div>';
  if(provs.length>1)h+='<div class="chips" role="group" aria-label="Filter by provider"><button class="all" aria-pressed="'+!filter+'" data-f="">All</button>'+
    provs.map(p=>'<button aria-pressed="'+(filter===p.id)+'" data-f="'+esc(p.id)+'">'+mono(p)+esc(p.name)+'</button>').join('')+'</div>';
  h+='<div class="strip"><div class="tile"><div class="k">Accounts</div><div class="v num">'+shown.length+'</div></div>'+
    '<div class="tile"><div class="k">Ahead of pace</div><div class="v num" style="color:'+(hot?'var(--warn)':'inherit')+'">'+hot+'</div></div>'+
    '<div class="tile"><div class="k">Need attention</div><div class="v num" style="color:'+(failing?'var(--crit)':'inherit')+'">'+failing+'</div></div>'+
    '<div class="tile"><div class="k">Next reset</div><div class="v num" style="font-size:18px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+(next?until(next.w.resets)+'<small style="display:block;margin:2px 0 0;font-family:var(--sans)">'+esc(next.a.label)+'</small>':'–')+'</div></div></div>';
  h+='<div class="cards">'+shown.map(card).join('')+(filter?'':'<button class="card addcard" id="addc">'+ICON.plus+'<span>Add account</span></button>')+'</div>';
  h+='<footer><span>Updated '+fmtT(d.now)+' · refreshes every minute</span><span>Burnrate '+esc(S.session.version)+'</span></footer>';
  $('app').innerHTML=h;
  document.querySelectorAll('.chips button').forEach(b=>b.onclick=()=>location.hash=b.dataset.f?'#/p/'+b.dataset.f:'#/');
  document.querySelectorAll('.acard').forEach(c=>{c.onclick=()=>location.hash='#/a/'+c.dataset.id;c.onkeydown=e=>{if(e.key==='Enter')c.click()}});
  if($('addc'))$('addc').onclick=()=>addAccount();
  S.timer=setInterval(()=>{if(!document.querySelector('#modal:not([hidden])'))overviewPage(filter)},60000);
}
function card(a){
  const [dot,stxt]=statusOf(a),w=prim(a);
  let h='<article class="card acard" tabindex="0" role="link" data-id="'+a.id+'" aria-label="'+esc(a.label)+'">'+
    '<div class="ah">'+mono(a)+'<div class="who"><b>'+esc(a.label)+'</b><span>'+esc(a.provider_name)+(a.plan?' · '+esc(a.plan):'')+'</span></div>'+
    '<span class="pill" style="padding:3px 9px;font-size:12px"><span class="dot '+(dot==='live'?'':dot)+'"></span>'+esc(stxt)+'</span></div>';
  if(w&&w.pct!=null){
    const fc=w.forecast;
    h+='<div class="amain"><div class="mini">'+ringSVG(96,w,10,4)+'<div class="c"><span>'+Math.round(w.pct)+'<small>%</small></span></div></div><div>'+
      '<div class="vline">'+verdictHTML(w.state)+'</div><div class="facts">'+
      '<span>'+esc(w.label)+'</span>'+(w.resets?'<span>resets in <b>'+until(w.resets)+'</b></span>':'')+
      (w.projected!=null?'<span>'+(fc?'forecast':'at this pace')+' <b>'+Math.round(w.projected)+' %</b>'+(fc?' ('+Math.round(fc.p10)+'–'+Math.round(fc.p90)+')':'')+'</span>':'')+
      (w.today?'<span>today <b>'+f1(w.today)+' %</b></span>':'')+'</div></div></div>';
  }
  if(!w&&(a.balances||[]).length){const b=a.balances[0],sub=[];
    if(b.runway_days!=null)sub.push('lasts ~'+(b.runway_days>99?'99+':Math.round(b.runway_days))+' days');
    if(b.per_day)sub.push(amount(b.per_day,b.currency)+'/day');if(b.today)sub.push(amount(b.today,b.currency)+' today');
    h+='<div><div class="bigamt num">'+amount(b.amount,b.currency)+'</div><div class="facts"><span>'+esc(b.label)+(b.kind==='spent'?' (spent)':'')+'</span>'+sub.map(x=>'<span><b>'+esc(x)+'</b></span>').join('')+'</div></div>'}
  const rest=(a.windows||[]).filter(x=>x!==w),rbal=w?(a.balances||[]):(a.balances||[]).slice(1);
  if(rest.length||rbal.length)h+='<div class="wins">'+rest.slice(0,4).map(winRow).join('')+rbal.slice(0,3).map(balRow).join('')+'</div>';
  h+=sparkSVG(w?w.spark:((a.balances||[])[0]||{}).spark);
  if(!a.connected)h+='<div class="err-line">'+ICON.crit+'<span>Not connected. Open Settings to sign in.</span></div>';
  else if(a.error)h+='<div class="err-line">'+ICON.crit+'<span>'+esc(a.error.slice(0,180))+'</span></div>';
  else if(!a.windows.length&&!a.balances.length)h+='<div class="sub">Waiting for the first sample…</div>';
  return h+'</article>';
}

/* ---------- charts ---------- */
function nice(m){for(const s of [0.5,1,2,5,10,20,25,50,100])if(m<=s)return s;const p=10**Math.floor(Math.log10(m));return Math.ceil(m/p)*p}
function roundTop(x,y,w,h,r){r=Math.min(r,w/2,h);return `M${x},${y+h}V${y+r}Q${x},${y} ${x+r},${y}H${x+w-r}Q${x+w},${y} ${x+w},${y+r}V${y+h}Z`}
function yAxis(s,W,L,T,P,max,fmt){for(let i=0;i<=4;i++){const y=T+P*(1-i/4);el('line',{x1:L,x2:W,y1:y,y2:y,class:i?'grid':'base'},s);el('text',{x:L-8,y:y+4,'text-anchor':'end'},s).textContent=fmt(max*i/4)}}
function emptyNote(box,msg){const d=document.createElement('div');d.className='empty';d.innerHTML='<span>'+esc(msg)+'</span>';box.style.position='relative';box.appendChild(d)}
function stack(box,data,lab,every,legendBox,emptyMsg,unit){
  const W=NARROW()?560:1100,H=230,L=58,B=26,T=10,P=H-T-B,n=data.length,fmt=unit||(v=>pc(v));
  const tot=data.map(d=>Object.values(d[1]).reduce((a,b)=>a+b,0));
  const max=nice(Math.max(0.5,...tot));
  const s=el('svg',{viewBox:`0 0 ${W} ${H}`,class:'chart',role:'img'});
  yAxis(s,W,L,T,P,max,v=>unit?unit(v,true):(+v.toFixed(2)).toLocaleString(LOC)+'%');
  const bw=(W-L)/n,inner=Math.max(2,bw*0.68),used=new Set();
  data.forEach((d,i)=>{const x=L+i*bw+(bw-inner)/2;let y=T+P;const keys=KEYS.concat(['_total']).filter(k=>d[1][k]>0);
    keys.forEach((k,j)=>{used.add(k);const h=Math.max(1,P*d[1][k]/max);y-=h;const top=j==keys.length-1,hh=top?h:Math.max(0,h-2);
      if(top)el('path',{d:roundTop(x,y,inner,hh,3),fill:col(k)},s);else el('rect',{x,y:y+2,width:inner,height:hh,fill:col(k)},s)});
    const hit=el('rect',{x:L+i*bw,y:T,width:bw,height:P,fill:'transparent'},s);
    hover(hit,()=>'<b>'+lab(d[0],false)+'</b><br>'+(tot[i]>0?(keys.length>1||keys[0]!=='_total'?keys.map(k=>esc(NAMES[k]||k)+': '+fmt(d[1][k])).join('<br>')+'<br>':'')+'Total: <b>'+fmt(tot[i])+'</b>':'nothing used'));
    const l=lab(d[0],true,i);if(l&&i%(NARROW()?every*2:every)==0)el('text',{x:L+i*bw+bw/2,y:H-6,'text-anchor':'middle'},s).textContent=l});
  box.replaceChildren(s);
  if(legendBox)legendBox.innerHTML=[...used].filter(k=>k!=='_total').length>1?KEYS.filter(k=>used.has(k)).map(k=>'<span><i style="background:'+col(k)+'"></i>'+esc(NAMES[k]||k)+'</span>').join(''):'';
  if(!tot.some(v=>v>0))emptyNote(box,emptyMsg);
}
function burn(box,w,now){
  const pts=w.burn||[],W=NARROW()?560:1100,H=280,L=48,R=78,B=28,T=14,P=H-T-B;
  const s=el('svg',{viewBox:`0 0 ${W} ${H}`,class:'chart',role:'img','aria-label':'Use over the current window'});
  const X=t=>L+(W-L-R)*(t-w.start)/(w.resets-w.start),Y=v=>T+P*(1-Math.min(v,110)/100);
  yAxis(s,W-R,L,T,P,100,v=>v+'%');
  const span=w.resets-w.start,stepD=span>2*86400;
  if(stepD){const day=new Date(w.start*1000);day.setHours(24,0,0,0);
    for(let t=day.getTime()/1000;t<w.resets;t+=86400){const x=X(t);el('line',{x1:x,x2:x,y1:T,y2:T+P,class:'grid','stroke-dasharray':'2 4'},s);
      if(X(t+43200)<W-R&&span<=10*86400)el('text',{x:X(t+43200),y:H-8,'text-anchor':'middle'},s).textContent=new Date(t*1000).toLocaleDateString(LOC,{weekday:'short'});
      else if(span>10*86400&&new Date(t*1000).getDate()%5===1)el('text',{x:x,y:H-8,'text-anchor':'middle'},s).textContent=new Date(t*1000).toLocaleDateString(LOC,{day:'2-digit',month:'2-digit'})}}
  else{for(let t=Math.ceil(w.start/3600)*3600;t<w.resets;t+=3600){const x=X(t);el('line',{x1:x,x2:x,y1:T,y2:T+P,class:'grid','stroke-dasharray':'2 4'},s);
      el('text',{x:x,y:H-8,'text-anchor':'middle'},s).textContent=String(new Date(t*1000).getHours()).padStart(2,'0')+'h'}}
  const defs=el('defs',{},s),g=el('linearGradient',{id:'bg',x1:0,x2:0,y1:0,y2:1},defs);
  el('stop',{offset:0,'stop-color':'var(--use)','stop-opacity':.38},g);el('stop',{offset:1,'stop-color':'var(--use)','stop-opacity':0},g);
  el('line',{x1:X(w.start),y1:Y(0),x2:X(w.resets),y2:Y(100),stroke:'var(--time)','stroke-width':2,'stroke-dasharray':'6 6'},s);
  const fc=w.forecast;
  if(pts.length){
    let p='M'+X(pts[0][0]).toFixed(1)+','+Y(pts[0][1]).toFixed(1);pts.forEach(q=>p+='L'+X(q[0]).toFixed(1)+','+Y(q[1]).toFixed(1));
    const last=pts[pts.length-1];
    el('path',{d:p+'L'+X(last[0]).toFixed(1)+','+Y(0)+'L'+X(pts[0][0]).toFixed(1)+','+Y(0)+'Z',fill:'url(#bg)'},s);
    el('path',{d:p,fill:'none',stroke:'var(--use)','stroke-width':2.5,'stroke-linejoin':'round'},s);
    if(fc&&fc.curve&&fc.curve.length){
      const c=[[last[0],last[1],last[1],last[1]],...fc.curve.filter(q=>q[0]>last[0])],pt=(q,i)=>X(q[0]).toFixed(1)+','+Y(q[i]).toFixed(1);
      el('path',{d:'M'+c.map(q=>pt(q,3)).join('L')+'L'+c.slice().reverse().map(q=>pt(q,1)).join('L')+'Z',fill:'var(--use)','fill-opacity':.13},s);
      el('path',{d:'M'+c.map(q=>pt(q,2)).join('L'),fill:'none',stroke:'var(--use)','stroke-width':2,'stroke-dasharray':'1 5','stroke-linecap':'round'},s);
      if(fc.hit_prob>0)el('line',{x1:X(w.start),x2:X(w.resets),y1:Y(100),y2:Y(100),stroke:'var(--crit)','stroke-width':1,'stroke-dasharray':'3 4',opacity:.7},s);
    }else if(w.projected!=null)el('line',{x1:X(last[0]),y1:Y(last[1]),x2:X(w.resets),y2:Y(Math.min(w.projected,110)),stroke:'var(--use)','stroke-width':2,'stroke-dasharray':'1 5','stroke-linecap':'round'},s);
    if(w.projected!=null){const pv=Math.min(w.projected,110);
      el('circle',{cx:X(w.resets),cy:Y(pv),r:4.5,fill:'var(--surface)',stroke:'var(--use)','stroke-width':2},s);
      const t=el('text',{x:X(w.resets)+10,y:Y(pv)+4},s);t.textContent='→ '+Math.round(w.projected)+'%';t.style.fill='var(--t1)';
      if(fc){const r=el('text',{x:X(w.resets)+10,y:Y(pv)+20},s);r.textContent=Math.round(fc.p10)+'–'+Math.round(fc.p90)+'%'}}
    el('circle',{cx:X(last[0]),cy:Y(last[1]),r:5.5,fill:'var(--use)',stroke:'var(--surface)','stroke-width':2.5},s);
  }
  el('line',{x1:X(now),x2:X(now),y1:T,y2:T+P,stroke:'var(--t2)','stroke-width':1},s);
  const nt=el('text',{x:X(now),y:T-2,'text-anchor':'middle'},s);nt.textContent='now';nt.style.fill='var(--t2)';
  const cx=el('line',{y1:T,y2:T+P,stroke:'var(--t1)','stroke-width':1,opacity:0},s),cd=el('circle',{r:5,fill:'var(--use)',stroke:'var(--surface)','stroke-width':2,opacity:0},s);
  const hit=el('rect',{x:L,y:T,width:W-L-R,height:P,fill:'transparent'},s);
  const mark=(t,v)=>{const x=X(t);cx.setAttribute('x1',x);cx.setAttribute('x2',x);cx.setAttribute('opacity',.35);cd.setAttribute('cx',x);cd.setAttribute('cy',Y(v));cd.setAttribute('opacity',1)};
  hit.addEventListener('mousemove',ev=>{if(!pts.length)return;const r=s.getBoundingClientRect(),vx=(ev.clientX-r.left)*W/r.width,t=w.start+(vx-L)/(W-L-R)*(w.resets-w.start);
    const pace=x=>100*(x-w.start)/(w.resets-w.start);
    if(fc&&fc.curve&&fc.curve.length&&t>pts[pts.length-1][0]){let b=fc.curve[0];for(const q of fc.curve)if(Math.abs(q[0]-t)<Math.abs(b[0]-t))b=q;mark(b[0],b[2]);
      return showTip(ev,'<b>'+fmtT(b[0])+'</b><br>Forecast: <b>'+pc(b[2])+'</b><br>Likely: '+pc(b[1])+' – '+pc(b[3])+'<br>Even pace: '+pc(pace(b[0])))}
    let best=pts[0];for(const q of pts)if(Math.abs(q[0]-t)<Math.abs(best[0]-t))best=q;mark(best[0],best[1]);
    showTip(ev,'<b>'+fmtT(best[0])+'</b><br>Used: <b>'+pc(best[1])+'</b><br>Even pace: '+pc(pace(best[0])))});
  hit.addEventListener('mouseleave',()=>{hideTip();cx.setAttribute('opacity',0);cd.setAttribute('opacity',0)});
  box.replaceChildren(s);
}
function heat(box,rows,wl){
  const max=Math.max(0.01,...rows.flatMap(r=>r[1]));
  let h='<div></div>'+[...Array(24)].map((_,i)=>'<div class="cl">'+(i%3==0?String(i).padStart(2,'0'):'')+'</div>').join('');
  rows.forEach(([day,cells])=>{const dd=new Date(day+'T12:00');
    h+='<div class="rl">'+dd.toLocaleDateString(LOC,NARROW()?{day:'2-digit',month:'2-digit'}:{weekday:'short',day:'2-digit',month:'2-digit'})+'</div>';
    cells.forEach((v,i)=>{const a=v>0?Math.round(22+78*Math.sqrt(v/max)):0;
      h+='<div class="c" data-t="'+dd.toLocaleDateString(LOC,{weekday:'short',day:'2-digit',month:'2-digit'})+', '+String(i).padStart(2,'0')+':00" data-v="'+v+'"'+(a?' style="background:color-mix(in oklab,var(--use) '+a+'%,var(--surface-2))"':'')+'></div>'})});
  box.innerHTML=h;
  box.querySelectorAll('.c').forEach(c=>hover(c,()=>'<b>'+c.dataset.t+'</b><br>'+(+c.dataset.v>0?pc(+c.dataset.v)+' of the '+esc(wl)+' limit':'nothing used')));
}
function peaks(box,data,now){
  const W=NARROW()?560:1100,H=220,L=48,B=26,T=22,P=H-T-B,n=Math.max(data.length,1);
  const s=el('svg',{viewBox:`0 0 ${W} ${H}`,class:'chart',role:'img'});
  yAxis(s,W,L,T,P,100,v=>v+'%');
  const bw=Math.min((W-L)/n,110),inner=Math.min(bw*0.62,64);
  data.forEach((d,i)=>{const x=L+i*bw+(bw-inner)/2,h=Math.max(2,P*Math.min(d[1],100)/100),cur=d[0]>now;
    el('path',{d:roundTop(x,T+P-h,inner,h,4),fill:'var(--use)',opacity:cur?1:.55},s);
    const t=el('text',{x:x+inner/2,y:T+P-h-7,'text-anchor':'middle'},s);t.textContent=Math.round(d[1])+'%';t.style.fill='var(--t1)';
    el('text',{x:x+inner/2,y:H-6,'text-anchor':'middle'},s).textContent=(cur?'now · ':'')+dt(d[0],{day:'2-digit',month:'2-digit'});
    hover(el('rect',{x:L+i*bw,y:T,width:bw,height:P,fill:'transparent'},s),()=>'<b>Window until '+fmtT(d[0])+'</b><br>Peak: '+pc(d[1])+(cur?' (running)':''))});
  box.replaceChildren(s);
}
function story(w){
  const fc=w.forecast;let s='<b>'+pc(w.pct)+'</b> used';
  if(w.elapsed!=null){const gap=Math.abs(Math.round(w.diff));
    s+=' with <b>'+pc(w.elapsed)+'</b> of '+periodWord(w).replace('this ','the ').replace('today','the day')+' gone'+
      (gap<1?' — right on an even spread.':w.diff<0?' — <b>'+gap+(gap==1?' point':' points')+'</b> of headroom.':' — <b>'+gap+(gap==1?' point':' points')+'</b> ahead of an even spread.')}
  else s+='.';
  if(w.pct>=100)return s;
  if(fc){const pr=Math.round(fc.hit_prob*100);
    if(fc.hit_at)return s+' Going by your usual pattern you hit the limit around <b>'+fmtT(fc.hit_at)+'</b> ('+pr+' % of runs).';
    return s+' Going by your usual pattern you end '+periodWord(w)+' near <b>'+Math.round(fc.p50)+' %</b> (likely '+Math.round(fc.p10)+'–'+Math.round(fc.p90)+' %)'+
      (pr>=5?', with a <b>'+pr+' %</b> chance of hitting the limit'+(fc.hit_early?' (as early as '+fmtT(fc.hit_early)+')':'')+'.':'.')}
  if(w.projected!=null)return s+(w.projected>=100?' At this rate you reach the limit before the reset.':' At this rate you end '+periodWord(w)+' near <b>'+Math.round(w.projected)+' %</b>.');
  return s;
}

/* ---------- account page ---------- */
async function accountPage(id){
  let a;try{a=await api('/api/accounts/'+id)}catch(e){$('app').innerHTML=topbar()+'<div class="banner">'+ICON.crit+'<div>'+esc(e.message)+'</div></div>';return}
  document.title=a.label+' · '+(S.session.title||'Burnrate');
  KEYS=Object.keys(a.names||{});NAMES=Object.assign({_total:'Total'},a.names||{});
  const w=prim(a),[dot,stxt]=statusOf(a);
  let h=topbar('<button class="iconbtn" id="pollb" title="Poll now" aria-label="Poll now">'+ICON.refresh+'</button>')+
    '<a class="back" href="#/">'+ICON.back+'All accounts</a><div class="acchead">'+mono(a,'lg')+'<div><h1>'+esc(a.label)+'</h1><span class="sub">'+esc(a.provider_name)+(a.plan?' · '+esc(a.plan):'')+
    ' · <span class="dot '+(dot==='live'?'':dot)+'" style="display:inline-block"></span> '+esc(stxt)+(a.official?'':' · <span title="Read from the provider\'s internal endpoint; it may change without notice.">unofficial source</span>')+'</span></div></div>';
  if(!a.connected)h+='<div class="banner">'+ICON.crit+'<div>This account is not connected. <a href="#/settings">Connect it in Settings</a>.</div></div>';
  else if(a.error)h+='<div class="banner">'+ICON.crit+'<div>Polling fails since '+fmtT(a.error_at)+': '+esc(a.error)+' · <a href="#/settings">Settings</a></div></div>';
  if(w&&w.pct!=null){
    const fc=w.forecast,lvl=w.level||'good';
    h+='<section class="card hero"><div class="ring">'+ringSVG(300,w,22,5)+'<div class="center"><div class="pct num">'+Math.round(w.pct)+'<small>%</small></div><div class="lbl">of the '+esc(w.label.toLowerCase())+' limit</div></div></div><div>'+
      '<p class="eyebrow">'+esc(w.label)+(w.start?' · '+dt(w.start,{weekday:'short',day:'2-digit',month:'2-digit'})+' – '+dt(w.resets,{weekday:'short',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'')+'</p>'+
      '<div class="verdict">'+verdictHTML(w.state)+'</div>'+(w.diff!=null?'<span class="chip '+lvl+'">'+ICON[lvl]+(w.diff>0?'+':'')+Math.round(w.diff)+' pts vs. time</span>':'')+
      '<p class="story">'+story(w)+'</p><div class="tiles">'+
      '<div class="tile"><div class="k">Resets in</div><div class="v num" id="countdown">'+(w.resets?'':'–')+'</div></div>'+
      '<div class="tile"><div class="k">'+(fc?'Forecast at reset':'At this pace')+'</div><div class="v num">'+(w.projected!=null?Math.round(w.projected)+'<small>%'+(fc?' · '+Math.round(fc.p10)+'–'+Math.round(fc.p90):'')+'</small>':'–')+'</div></div>'+
      '<div class="tile"><div class="k">Budget / day left</div><div class="v num">'+(w.per_day_left!=null?f1(w.per_day_left)+'<small>%/day</small>':'–')+'</div></div>'+
      '<div class="tile"><div class="k">Used today</div><div class="v num">'+f1(w.today)+'<small>%</small></div></div></div></div></section>';
    if(w.start&&w.burn)h+='<section class="card"><div class="head"><div><p class="eyebrow">Burn-up</p><h2>'+esc(periodWord(w).replace(/^./,c=>c.toUpperCase()))+' so far</h2></div>'+
      '<div class="legend"><span><i style="background:var(--use)"></i>used</span><span><i class="dash"></i>even pace</span><span><i class="dots"></i>'+(fc?'forecast':'projection')+'</span>'+(fc?'<span><i class="band"></i>likely range</span>':'')+'</div></div><div id="burn"></div>'+
      '<p class="sub" style="margin:10px 0 0">'+(fc?'Forecast replays your '+fc.days+' recorded '+(fc.days==1?'day':'days')+' hour by hour (recent days and the same weekday count more), 400 simulated runs; the band holds 8 of 10. A typical day uses '+f1(fc.typical_total)+' %.'+(fc.days<7?' Gets sharper as more days are recorded.':''):
        (w.period>=86400?'Straight-line projection until one full day is recorded; then it forecasts from your own pattern.':'Straight-line projection.'))+'</p></section>';
  }
  const others=(a.windows||[]).filter(x=>x!==w),bals=a.balances||[],br=KEYS.length&&w;
  const side=[];
  if(br){const lw=(a.windows||[]).find(x=>x.id===a.primary);
    side.push('<section class="card"><p class="eyebrow">'+esc(lw.label)+'</p><h2>Where it went</h2><div class="seg" id="seg"></div><div class="rows" id="surf"></div></section>')}
  if(others.length)side.push('<section class="card"><p class="eyebrow">Your plan</p><h2>Other limits</h2><div class="wins" style="margin-top:12px">'+others.map(winRow).join('')+'</div></section>');
  if(bals.length)side.push('<section class="card"><p class="eyebrow">Money</p><h2>Balances</h2><div class="wins" style="margin-top:12px">'+bals.map(balRow).join('')+'</div></section>');
  if((a.info||[]).length)side.push('<section class="card"><p class="eyebrow">Account</p><h2>Details</h2><dl class="kv" style="margin-top:12px">'+a.info.map(i=>'<dt>'+esc(i.label)+'</dt><dd>'+esc(i.value)+'</dd>').join('')+'</dl></section>');
  for(let i=0;i<side.length;i+=2)h+=side[i+1]?'<div class="grid2" style="margin:14px 0">'+side[i]+side[i+1]+'</div>':side[i];
  if(w&&a.heat){
    h+='<section class="card"><div class="head"><div><p class="eyebrow">Rhythm</p><h2>When you use it</h2></div>'+
      '<div class="ramp">less <span style="background:var(--surface-2)"></span>'+[30,52,76,100].map(x=>'<span style="background:color-mix(in oklab,var(--use) '+x+'%,var(--surface-2))"></span>').join('')+' more</div></div>'+
      '<div class="heat" id="heat"></div><div class="sub" style="margin-top:8px">Last 14 days, % of the '+esc(w.label.toLowerCase())+' limit used per hour.</div></section>'+
      '<section class="card"><div class="head"><div><p class="eyebrow">Per hour</p><h2>Last 48 hours</h2></div><div class="legend" id="lg1"></div></div><div id="chour"></div></section>'+
      '<section class="card"><div class="head"><div><p class="eyebrow">Per day</p><h2>Last 30 days</h2></div><div class="legend" id="lg2"></div></div><div id="cday"></div></section>';
    if(a.peaks&&a.peaks.length>1)h+='<section class="card"><div class="head"><div><p class="eyebrow">History</p><h2>Peak of each window</h2></div><div class="sub">by reset date</div></div><div id="cpk"></div></section>';
  }
  bals.forEach(b=>{if(a.spend&&a.spend[b.id])h+='<section class="card"><div class="head"><div><p class="eyebrow">'+esc(b.label)+'</p><h2>Spend per day</h2></div><div class="sub">last 30 days, from balance changes</div></div><div id="sp_'+esc(b.id)+'"></div></section>'});
  h+='<footer><span>'+(a.samples||0)+' samples · every '+Math.round((a.interval||300)/60)+' min'+(a.last_ok?' · last '+fmtT(a.last_ok):'')+'</span><span><a href="#/settings">Settings</a></span></footer>';
  $('app').innerHTML=h;
  $('pollb').onclick=async()=>{$('pollb').disabled=true;try{const r=await api('/api/accounts/'+id+'/poll',{});toast(r.error?'Poll failed: '+r.error:'Updated',!!r.error)}catch(e){toast(e.message,true)}accountPage(id)};
  if(w&&w.start&&w.burn)burn($('burn'),w,Math.floor(Date.now()/1000));
  if(br){const rows=KEYS.map(k=>[k,NAMES[k],(a.breakdown_now||{})[k]]);
    const cur=lastBreak(a);const tot=cur.reduce((s,r)=>s+r[2],0);
    $('seg').innerHTML=tot>0?cur.filter(r=>r[2]>0).map(r=>'<div style="flex:'+r[2]+';background:'+col(r[0])+'"></div>').join(''):'';
    $('surf').innerHTML=cur.map(r=>'<div class="r"><i style="background:'+col(r[0])+'"></i><span'+(r[2]>0?'':' class="muted"')+'>'+esc(r[1])+'</span><span class="num'+(r[2]>0?'':' muted')+'">'+pc(r[2])+'</span></div>').join('')}
  if(w&&a.heat){
    heat($('heat'),a.heat,w.label.toLowerCase());
    const since='Collecting — bars appear as usage comes in.';
    stack($('chour'),a.hourly,(t,short)=>{const x=new Date(t*1000);return short?(x.getHours()==0?x.toLocaleDateString(LOC,{weekday:'short'}):String(x.getHours()).padStart(2,'0')+'h'):fmtT(t)},3,$('lg1'),since);
    stack($('cday'),a.daily,(k,short)=>{const x=new Date(k+'T12:00');return short?x.toLocaleDateString(LOC,{day:'2-digit',month:'2-digit'}):x.toLocaleDateString(LOC,{weekday:'long',day:'2-digit',month:'2-digit'})},3,$('lg2'),since);
    if($('cpk'))peaks($('cpk'),a.peaks,Date.now()/1000);
  }
  bals.forEach(b=>{const box=$('sp_'+b.id);if(box){const saveK=KEYS;KEYS=[];
    stack(box,a.spend[b.id].map(([d,v])=>[d,{_total:v}]),(k,short)=>{const x=new Date(k+'T12:00');return short?x.toLocaleDateString(LOC,{day:'2-digit',month:'2-digit'}):x.toLocaleDateString(LOC,{weekday:'long',day:'2-digit',month:'2-digit'})},3,null,'No spend recorded yet.',(v,ax)=>amount(v,b.currency));KEYS=saveK}});
  const cd=()=>{const e=$('countdown');if(!e||!w||!w.resets)return;let s=Math.max(0,w.resets-Date.now()/1000);const d=Math.floor(s/86400);s-=d*86400;const hh=Math.floor(s/3600);s-=hh*3600;const m=Math.floor(s/60),x=Math.floor(s-m*60);
    e.innerHTML=(d?d+'<small>d</small> ':'')+String(hh).padStart(2,'0')+':'+String(m).padStart(2,'0')+'<small>:'+String(x).padStart(2,'0')+'</small>'};
  cd();clearInterval(S.tick);S.tick=setInterval(cd,1000);
  S.timer=setInterval(()=>{if(!document.querySelector('#modal:not([hidden])'))accountPage(id)},60000);
}
function lastBreak(a){return KEYS.map(k=>[k,NAMES[k],(a.breakdown||[]).find(r=>r.key===k)?.pct||0])}

/* ---------- settings ---------- */
const INTERVALS=[[0,'default'],[60,'1 min'],[120,'2 min'],[300,'5 min'],[600,'10 min'],[900,'15 min'],[1800,'30 min'],[3600,'1 h']];
async function settingsPage(){
  document.title='Settings · '+(S.session.title||'Burnrate');
  let st,ov;try{[st,ov]=await Promise.all([api('/api/settings'),api('/api/overview')]);S.providers=S.providers||await api('/api/providers')}catch(e){return}
  const accs=ov.accounts;
  let h=topbar()+'<a class="back" href="#/">'+ICON.back+'Dashboard</a><div class="pagehead"><div><p class="eyebrow">Configuration</p><h1>Settings</h1></div></div>';
  h+='<section class="card set"><div class="head"><div><h2>Accounts</h2><p class="sub">Each account is polled on its own. Rename by clicking the name.</p></div><button id="adda">'+'+ Add account</button></div><div class="acclist">'+
    (accs.length?accs.map((a,i)=>{const [dot,stxt]=statusOf(a);return '<div class="arow" data-id="'+a.id+'"><div class="row" style="gap:8px;flex-wrap:nowrap"><div class="ord"><button data-mv="-1" aria-label="Move up"'+(i?'':' disabled')+'>▲</button><button data-mv="1" aria-label="Move down"'+(i<accs.length-1?'':' disabled')+'>▼</button></div>'+mono(a)+'</div>'+
      '<div class="meta"><input class="lbl" value="'+esc(a.label)+'" aria-label="Account name" maxlength="80"><span class="sub">'+esc(a.provider_name)+(a.plan?' · '+esc(a.plan):'')+' · <span class="dot '+(dot==='live'?'':dot)+'" style="display:inline-block"></span> '+esc(stxt)+'</span>'+
      (a.error?'<span class="sub danger-t">'+esc(a.error.slice(0,220))+'</span>':'')+'</div>'+
      '<div class="ctl"><label class="toggle" title="Enabled"><input type="checkbox" data-en'+(a.enabled?' checked':'')+' aria-label="Enabled"><span></span></label>'+
      '<select data-iv aria-label="Poll interval">'+INTERVALS.map(([v,l])=>'<option value="'+v+'"'+(((a.interval==st.interval&&!v)||(v&&v==a.interval&&a.interval!=st.interval))?' selected':'')+'>'+l+'</option>').join('')+'</select>'+
      '<button class="btn2 small" data-poll>Poll</button><button class="btn2 small" data-re>'+(a.connected?'Reconnect':'Connect')+'</button><button class="btn2 small danger-t" data-del>Delete</button></div></div>'}).join(''):'<p class="sub">No accounts yet.</p>')+'</div></section>';
  const zones=(Intl.supportedValuesOf?Intl.supportedValuesOf('timeZone'):[]);
  h+='<section class="card set"><h2>General</h2><p class="sub">Stored in the database; changes apply right away.</p><form id="gf" class="form">'+
    '<label for="s_title">Title</label><div><input id="s_title" value="'+esc(st.title)+'" maxlength="60"></div>'+
    '<label for="s_tz">Time zone</label><div><input id="s_tz" list="tzl" value="'+esc(st.timezone)+'"><datalist id="tzl">'+zones.map(z=>'<option value="'+z+'">').join('')+'</datalist><span class="hint">Used for hour and day buckets and the forecast. Your browser: '+esc(Intl.DateTimeFormat().resolvedOptions().timeZone)+'</span></div>'+
    '<label for="s_iv">Poll every</label><div><select id="s_iv">'+INTERVALS.slice(1).map(([v,l])=>'<option value="'+v+'"'+(v==st.interval?' selected':'')+'>'+l+'</option>').join('')+'</select><span class="hint">Default for accounts without their own interval. Most providers are fine with 5 min.</span></div>'+
    '<label for="s_th">Theme</label><div><select id="s_th">'+['auto','dark','light'].map(t=>'<option'+(t==(st.theme||'auto')?' selected':'')+'>'+t+'</option>').join('')+'</select></div>'+
    '<label for="s_pa">Main account</label><div><select id="s_pa"><option value="">none</option>'+accs.map(a=>'<option value="'+a.id+'"'+(a.id==st.primary_account?' selected':'')+'>'+esc(a.label)+'</option>').join('')+'</select><span class="hint">Served by <code>/api/wall</code> (a compact JSON for dashboards and wall displays).</span></div>'+
    '<label for="s_ret">Keep history</label><div><input id="s_ret" type="number" min="7" max="3650" value="'+esc(st.retention_days)+'" style="max-width:140px"> <span class="hint">days</span></div>'+
    '<span></span><div><button>Save</button></div></form></section>';
  h+='<section class="card set"><h2>Security</h2>';
  if(st.auth==='none')h+='<div class="note warn">Password login is off (<code>BURNRATE_AUTH=none</code>). Only run it like this behind a reverse proxy that does the authentication.</div>';
  else h+='<p class="sub">Change the password for this instance.</p><form id="pf" class="form"><label for="op">Current password</label><div><input type="password" id="op" autocomplete="current-password"></div>'+
    '<label for="np">New password</label><div><input type="password" id="np" autocomplete="new-password" minlength="8"></div><span></span><div class="row"><button>Change password</button><button type="button" class="btn2" id="lo">Sign out</button></div></form>';
  h+='<h2 style="margin-top:22px">API token</h2><p class="sub">Lets scripts read <code>/api/overview</code>, <code>/api/wall</code> and <code>/metrics</code> (Prometheus) without the password: header <code>Authorization: Bearer &lt;token&gt;</code> or <code>?token=</code>.</p>'+
    '<div class="row" id="tokrow">'+(st.api_token?'<span class="tag on">token set</span><button class="btn2 small" id="tnew">Replace</button><button class="btn2 small danger-t" id="tdel">Revoke</button>':'<button class="btn2" id="tnew">Create token</button>')+'</div><div id="tokshow"></div></section>';
  h+='<section class="card set"><h2>About</h2><dl class="kv" style="margin-top:10px"><dt>Version</dt><dd>'+esc(S.session.version)+'</dd><dt>Data directory</dt><dd><code>'+esc(st.data_dir)+'</code> (database + secrets.json, back it up)</dd>'+
    '<dt>Providers</dt><dd>'+S.providers.length+' built in</dd><dt>Endpoints</dt><dd><code>/healthz</code> · <code>/metrics</code> · <code>/api/overview</code> · <code>/api/wall?account=ID</code></dd></dl>'+
    '<p class="sub" style="margin-top:14px">Many providers are read from internal endpoints their own apps use. They can change without notice, and using them may be against a provider\'s terms. Credentials stay on this server in <code>secrets.json</code> (mode 0600) and are never sent to the browser.</p></section>';
  $('app').innerHTML=h;
  $('adda').onclick=()=>addAccount();
  document.querySelectorAll('.arow').forEach(r=>{const id=+r.dataset.id,a=accs.find(x=>x.id===id);
    const upd=async b=>{try{await api('/api/accounts/'+id,b);toast('Saved')}catch(e){toast(e.message,true)}};
    r.querySelector('.lbl').onchange=e=>upd({label:e.target.value});
    r.querySelector('[data-en]').onchange=e=>upd({enabled:e.target.checked});
    r.querySelector('[data-iv]').onchange=e=>upd({interval:+e.target.value||null});
    r.querySelector('[data-poll]').onclick=async e=>{e.target.disabled=true;e.target.innerHTML='<span class="spin"></span>';try{const x=await api('/api/accounts/'+id+'/poll',{});toast(x.error?'Failed: '+x.error:'Updated',!!x.error)}catch(x){toast(x.message,true)}settingsPage()};
    r.querySelector('[data-re]').onclick=()=>addAccount(a.provider,a);
    r.querySelector('[data-del]').onclick=async()=>{if(!confirm('Delete "'+a.label+'" with all its history and stored credentials?'))return;await api('/api/accounts/'+id+'/delete',{});toast('Deleted');settingsPage()};
    r.querySelectorAll('[data-mv]').forEach(b=>b.onclick=async()=>{const ids=accs.map(x=>x.id),i=ids.indexOf(id),j=i+(+b.dataset.mv);[ids[i],ids[j]]=[ids[j],ids[i]];await api('/api/accounts/order',{ids});settingsPage()});
  });
  $('gf').onsubmit=async e=>{e.preventDefault();try{await api('/api/settings',{title:$('s_title').value,timezone:$('s_tz').value,interval:+$('s_iv').value,theme:$('s_th').value,
    primary_account:$('s_pa').value?+$('s_pa').value:null,retention_days:+$('s_ret').value});theme($('s_th').value);S.session.title=$('s_title').value;toast('Saved')}catch(x){toast(x.message,true)}};
  if($('pf'))$('pf').onsubmit=async e=>{e.preventDefault();try{await api('/api/settings',{old_password:$('op').value,new_password:$('np').value});$('op').value=$('np').value='';toast('Password changed')}catch(x){toast(x.message,true)}};
  if($('lo'))$('lo').onclick=async()=>{await api('/api/logout',{});boot()};
  const tok=async v=>{try{const r=await api('/api/settings',{api_token:v});if(r.api_token){settingsPage().then(()=>{$('tokshow').innerHTML='<p class="sub" style="margin:12px 0 6px">Copy it now; it is not shown again:</p><div class="secret">'+esc(r.api_token)+'</div>'})}else{toast('Revoked');settingsPage()}}catch(x){toast(x.message,true)}};
  $('tnew').onclick=()=>tok('new');if($('tdel'))$('tdel').onclick=()=>{if(confirm('Revoke the API token? Scripts using it stop working.'))tok('delete')};
}

/* ---------- add / reconnect account ---------- */
function openModal(html){$('sheet').innerHTML=html;$('modal').hidden=false;document.body.style.overflow='hidden';const f=$('sheet').querySelector('input,button.ptile,button');if(f)f.focus()}
function closeModal(){$('modal').hidden=true;document.body.style.overflow='';clearInterval(S.devpoll)}
$('modal').addEventListener('click',e=>{if(e.target.id==='modal')closeModal()});
addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('modal').hidden)closeModal()});
const CATS=[['','All'],['subscription','Subscriptions'],['api','API & credits']];
async function addAccount(pid,existing){
  S.providers=S.providers||await api('/api/providers');
  if(pid)return providerForm(S.providers.find(p=>p.id===pid),existing);
  let cat='',q='';
  const render=()=>{
    const list=S.providers.filter(p=>(!cat||p.category===cat||(cat==='api'&&p.category==='credits'))&&(!q||(p.name+' '+p.vendor+' '+p.blurb).toLowerCase().includes(q)));
    $('pg').innerHTML=list.map(p=>'<button class="ptile" data-p="'+esc(p.id)+'">'+mono(p)+'<b>'+esc(p.name)+'</b><span>'+esc(p.vendor)+'</span>'+
      '<span style="grid-column:1/-1">'+esc(p.blurb)+'</span><span class="tags"><span class="tag" style="margin:0">'+(p.category==='subscription'?'subscription':'API / credits')+'</span>'+
      (p.official?'<span class="tag on" style="margin:0">official API</span>':'<span class="tag" style="margin:0">unofficial</span>')+'<span class="tag" style="margin:0">'+esc(p.auths.map(a=>({fields:'key',oauth_paste:'sign-in',device:'sign-in'}[a.kind]||a.kind)).filter((v,i,s)=>s.indexOf(v)===i).join(' / '))+'</span></span></button>').join('')||'<p class="sub">Nothing matches.</p>';
    $('pg').querySelectorAll('.ptile').forEach(b=>b.onclick=()=>providerForm(S.providers.find(p=>p.id===b.dataset.p)));
  };
  openModal('<div class="mhead"><div><p class="eyebrow">Add account</p><h2>Pick a provider</h2></div><button class="iconbtn" id="mx" aria-label="Close">'+ICON.x+'</button></div>'+
    '<div class="ptools"><input id="pq" placeholder="Search '+S.providers.length+' providers" aria-label="Search providers"><div class="seg2" role="group">'+CATS.map(([v,l])=>'<button data-c="'+v+'" aria-pressed="'+(v===cat)+'">'+l+'</button>').join('')+'</div></div><div class="pgrid" id="pg"></div>');
  $('mx').onclick=closeModal;
  $('pq').oninput=e=>{q=e.target.value.toLowerCase().trim();render()};
  document.querySelectorAll('.seg2 button').forEach(b=>b.onclick=()=>{cat=b.dataset.c;document.querySelectorAll('.seg2 button').forEach(x=>x.setAttribute('aria-pressed',x===b));render()});
  render();
}
function fieldHTML(f,prefix,val){
  const id=prefix+f.name,v=val??f.default??'';
  let inp;
  if(f.kind==='select')inp='<select id="'+id+'">'+(f.options||[]).map(o=>{const [ov,ol]=Array.isArray(o)?o:[o,o];return '<option value="'+esc(ov)+'"'+(ov==v?' selected':'')+'>'+esc(ol)+'</option>'}).join('')+'</select>';
  else if(f.kind==='textarea')inp='<textarea id="'+id+'" placeholder="'+esc(f.placeholder)+'" spellcheck="false" autocomplete="off">'+esc(v)+'</textarea>';
  else inp='<input id="'+id+'" type="'+(f.kind==='secret'?'password':'text')+'" placeholder="'+esc(f.placeholder)+'" value="'+esc(v)+'" autocomplete="off" spellcheck="false">';
  return '<label for="'+id+'">'+esc(f.label)+(f.required?'':' <span class="sub">(optional)</span>')+'</label><div>'+inp+(f.help?'<span class="hint">'+esc(f.help)+'</span>':'')+'</div>';
}
function providerForm(p,existing){
  let au=p.auths[0];
  if(existing){/* keep provider's first auth */}
  const opts=existing?(existing.options||{}):{};
  const render=()=>{
    let h='<div class="mhead"><div class="row" style="flex-wrap:nowrap;gap:14px">'+mono(p,'lg')+'<div><p class="eyebrow">'+(existing?'Reconnect':'Add account')+' · '+esc(p.vendor)+'</p><h2>'+esc(p.name)+'</h2></div></div><button class="iconbtn" id="mx" aria-label="Close">'+ICON.x+'</button></div>';
    if(p.help)h+='<p class="sub" style="color:var(--t2);font-size:14px;margin:0 0 12px">'+esc(p.help)+'</p>';
    if(!p.official)h+='<div class="note" style="margin-bottom:14px">Unofficial: read from an internal endpoint '+esc(p.vendor||p.name)+'\'s own apps use. It can break without notice.</div>';
    h+='<div class="form">';
    if(!existing)h+='<label for="f_label">Name</label><div><input id="f_label" value="'+esc(p.name)+'" maxlength="80"><span class="hint">Shown on the dashboard, e.g. "Work" or "Personal".</span></div>';
    p.options.forEach(f=>h+=fieldHTML(f,'o_',opts[f.name]));
    if(p.auths.length>1)h+='<label>Connect with</label><div><div class="seg2" role="group">'+p.auths.map(a=>'<button type="button" data-au="'+esc(a.id)+'" aria-pressed="'+(a===au)+'">'+esc(a.label)+'</button>').join('')+'</div></div>';
    if(au.help)h+='<span></span><div class="hint" style="margin-top:-6px">'+esc(au.help)+'</div>';
    if(au.kind==='fields')au.fields.forEach(f=>h+=fieldHTML(f,'k_'));
    h+='</div><div id="flow" style="margin-top:18px"></div><div class="row" style="margin-top:18px;justify-content:flex-end"><button class="btn2" id="cancel">Cancel</button><button id="go">'+(au.kind==='fields'?'Connect':'Continue')+'</button></div>';
    $('sheet').innerHTML=h;
    $('mx').onclick=$('cancel').onclick=closeModal;
    document.querySelectorAll('[data-au]').forEach(b=>b.onclick=()=>{au=p.auths.find(a=>a.id===b.dataset.au);render()});
    $('go').onclick=start;
    const f=$('sheet').querySelector('input');if(f)f.focus();
  };
  const body=()=>{const options={};p.options.forEach(f=>options[f.name]=$('o_'+f.name).value);
    const fields={};if(au.kind==='fields')au.fields.forEach(f=>fields[f.name]=$('k_'+f.name).value);
    return {provider:p.id,auth:au.id,label:existing?existing.label:$('f_label').value,options,fields,account:existing?existing.id:null}};
  const done=r=>{closeModal();toast((existing?'Reconnected ':'Connected ')+p.name);location.hash='#/a/'+r.account;route()};
  const fail=e=>{$('flow').innerHTML='<div class="note bad">'+esc(e.message)+'</div>';$('go').disabled=false;$('go').textContent='Try again'};
  async function start(){
    $('go').disabled=true;$('go').innerHTML='<span class="spin"></span> '+(au.kind==='fields'?'Checking…':'Starting…');
    let r;try{r=await api('/api/connect',body())}catch(e){return fail(e)}
    if(r.done)return done(r);
    $('go').remove();$('cancel').textContent='Close';
    if(r.kind==='oauth_paste'){
      $('flow').innerHTML='<div class="step"><i>1</i><div><b>Sign in at '+esc(new URL(r.url).host)+'</b><p>Opens in a new tab. You type your password there, never here.</p><a class="btn" href="'+esc(r.url)+'" target="_blank" rel="noopener noreferrer">Open sign-in →</a></div></div>'+
        '<div class="step"><i>2</i><div><b>Paste the result</b><p>'+esc(r.hint)+'</p><div class="row"><input id="paste" autocomplete="off" spellcheck="false" style="flex:1 1 300px" placeholder="code or address"><button id="fin">Finish</button></div><div id="perr" style="margin-top:10px"></div></div></div>';
      $('fin').onclick=async()=>{$('fin').disabled=true;$('fin').innerHTML='<span class="spin"></span>';
        try{done(await api('/api/connect/'+r.flow+'/finish',{pasted:$('paste').value}))}catch(e){$('perr').innerHTML='<div class="note bad">'+esc(e.message)+'</div>';$('fin').disabled=false;$('fin').textContent='Finish'}};
    }else if(r.kind==='device'){
      $('flow').innerHTML='<div class="step"><i>1</i><div><b>Open '+esc(new URL(r.url).host)+'</b><p>Sign in there and enter this code:</p><div class="row" style="gap:14px"><span class="ucode">'+esc(r.user_code)+'</span><button class="btn2" id="cpy">Copy</button></div>'+
        '<p style="margin-top:12px"><a class="btn" href="'+esc(r.url)+'" target="_blank" rel="noopener noreferrer">Open '+esc(new URL(r.url).host)+' →</a></p></div></div>'+
        '<div class="step"><i>2</i><div><b>Waiting for approval</b><p id="dst"><span class="spin"></span> This finishes by itself once you approve.</p></div></div>';
      $('cpy').onclick=()=>{navigator.clipboard&&navigator.clipboard.writeText(r.user_code);toast('Copied')};
      clearInterval(S.devpoll);
      S.devpoll=setInterval(async()=>{try{const x=await api('/api/connect/'+r.flow);if(x.done){clearInterval(S.devpoll);done(x)}else if(x.error){clearInterval(S.devpoll);$('dst').innerHTML='<span class="danger-t">'+esc(x.error)+'</span>'}}
        catch(e){clearInterval(S.devpoll);$('dst').innerHTML='<span class="danger-t">'+esc(e.message)+'</span>'}},3000);
    }
  }
  if($('modal').hidden)openModal('');
  render();
}
boot();
let RW=NARROW();addEventListener('resize',()=>{if(NARROW()!=RW){RW=NARROW();route()}});
