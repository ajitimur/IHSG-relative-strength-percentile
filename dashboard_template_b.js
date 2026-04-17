
const SECTOR_COLORS={
  'Basic Materials':        ['#cd853f','rgba(205,133,63,0.12)'],
  'Communication Services': ['#7b68ee','rgba(123,104,238,0.12)'],
  'Consumer Cyclical':      ['#20b2aa','rgba(32,178,170,0.12)'],
  'Consumer Defensive':     ['#3cb371','rgba(60,179,113,0.12)'],
  'Energy':                 ['#ff8c00','rgba(255,140,0,0.12)'],
  'Financial Services':     ['#4f8ef7','rgba(79,142,247,0.12)'],
  'Healthcare':             ['#ff69b4','rgba(255,105,180,0.12)'],
  'Industrials':            ['#87ceeb','rgba(135,206,235,0.12)'],
  'Real Estate':            ['#dda0dd','rgba(221,160,221,0.12)'],
  'Technology':             ['#00ced1','rgba(0,206,209,0.12)'],
  'Utilities':              ['#f0e68c','rgba(240,230,140,0.12)'],
};

// ── STATE ──────────────────────────────────────────────────
let ACTIVE = EMBEDDED;
const state = {
  activeTab: 'rs',
  topN: { rs:'ALL', m1:'ALL', m3:'ALL' },
  minTf: 2,
  filters: { rs:{}, m1:{}, m3:{}, cross:{}, mom:{} },
  sorts: {
    rs:    [{col:'rs_score',  dir:-1}],
    m1:    [{col:'pct_1m',   dir:-1}],
    m3:    [{col:'pct_3m',   dir:-1}],
    cross: [{col:'tf_count_10',dir:-1},{col:'avg_pct',dir:-1}],
    mom:   [{col:'accel',    dir:-1}],
  }
};

// ── TOP% PILL CONFIG ───────────────────────────────────────
const TOP_PILLS = [
  {label:'ALL', val:'ALL'},
  {label:'1%',  val:0.01},
  {label:'2%',  val:0.02},
  {label:'5%',  val:0.05},
  {label:'10%', val:0.10},
  {label:'20%', val:0.20},
];
const TF_PILLS = [
  {label:'2 TFs', val:2},
  {label:'3 TFs', val:3},
  {label:'4 TFs', val:4},
];

function buildTopPills(tab) {
  const el = document.getElementById('pills-'+tab);
  if (!el) return;
  el.innerHTML = TOP_PILLS.map(p => {
    const active = state.topN[tab] === p.val ? (p.val==='ALL'?'active':'active') : '';
    const cls = p.val==='ALL'?'top-pill pill-all':'top-pill';
    return `<button class="${cls}${active?' active':''}" onclick="setTopN('${tab}','${p.val === 'ALL' ? 'ALL' : p.val}')">${p.label}</button>`;
  }).join('');
}

function buildTfPills() {
  const el = document.getElementById('pills-cross-tf');
  if (!el) return;
  el.innerHTML = TF_PILLS.map(p =>
    `<button class="top-pill${state.minTf===p.val?' active-purple active':''}" onclick="setMinTf(${p.val})">${p.label}</button>`
  ).join('');
}

function setTopN(tab, val) {
  state.topN[tab] = val === 'ALL' ? 'ALL' : parseFloat(val);
  buildTopPills(tab);
  renderTable(tab);
}

function setMinTf(val) {
  state.minTf = val;
  buildTfPills();
  renderTable('cross');
}

function applyTopN(data, tab, sortCol) {
  const n = state.topN[tab];
  if (n === 'ALL') return data;
  const count = Math.max(1, Math.round(ACTIVE.meta.liquid_count * n));
  // Sort by primary sort col desc, take top N, then re-apply user sort later
  const sorted = [...data].sort((a,b) => (b[sortCol]??-Infinity) - (a[sortCol]??-Infinity));
  return sorted.slice(0, count);
}

// ── CSV PARSER ─────────────────────────────────────────────
function parseCSV(text) {
  const lines = text.trim().split('\n');
  const headers = lines[0].split(',').map(h=>h.trim());
  return { headers, rows: lines.slice(1).map(line => {
    const vals = line.split(',');
    const row = {};
    headers.forEach((h,j) => {
      const v = (vals[j]||'').trim();
      row[h] = (v===''||v==='None'||v==='nan'||v==='NaN') ? null : (!isNaN(v) ? parseFloat(v) : v);
    });
    return row;
  })};
}

function buildDataFromCSV(rows, headers) {
  const has = k => headers.includes(k);
  const liq = rows.filter(r => r.avg_vol_30d != null && r.avg_vol_30d >= 1000000);

  // Cross-TF metrics
  liq.forEach(r => {
    r.tf_count_10 = ['pct_1m','pct_3m','pct_6m','pct_12m'].filter(c => r[c]!=null && r[c]>=90).length;
    const vals = ['pct_1m','pct_3m','pct_6m','pct_12m'].map(c=>r[c]).filter(v=>v!=null);
    r.avg_pct = vals.length ? +(vals.reduce((a,b)=>a+b,0)/vals.length).toFixed(1) : null;
    r.shape_score = +((
      (r.pct_1m - r.pct_12m)*0.5 +
      (r.pct_1m - r.pct_3m)*0.3 +
      (r.pct_3m - r.pct_6m)*0.2
    ).toFixed(1));
  });

  const momentum = liq.filter(r =>
    r.pct_1m > r.pct_3m && r.pct_3m > r.pct_12m &&
    r.pct_1m >= 60 && (r.pct_1m - r.pct_3m) >= 10
  ).map(r => ({...r, accel: r.pct_1m - r.pct_3m}))
   .sort((a,b) => b.accel - a.accel);

  const cross = [...liq].filter(r => r.tf_count_10 >= 2)
    .sort((a,b) => b.tf_count_10 - a.tf_count_10 || b.avg_pct - a.avg_pct);

  const sMap = {};
  liq.forEach(r => { const s=r.sector||'Unknown'; (sMap[s]=sMap[s]||[]).push(r); });
  const sectors = Object.entries(sMap).filter(([,g])=>g.length>=3).map(([sector,grp])=>{
    const brd = col => grp.filter(r=>r[col]>=70).length/grp.length*100;
    const b1=brd('pct_1m'),b3=brd('pct_3m'),b6=brd('pct_6m');
    const mb=b1*.5+b3*.3+b6*.2;
    const t5=[...grp].sort((a,b)=>b.pct_1m-a.pct_1m).slice(0,5);
    const meds=t5.map(r=>r.pct_1m).sort((a,b)=>a-b);
    const ceiling=meds[Math.floor(meds.length/2)];
    const avg=grp.reduce((s,r)=>s+(r.pct_1m||0),0)/grp.length;
    return {sector,count:grp.length,
      composite:+(mb*.4+ceiling*.4+avg*.2).toFixed(1),
      multi_breadth:+mb.toFixed(1),breadth_1m:+b1.toFixed(1),breadth_3m:+b3.toFixed(1),breadth_6m:+b6.toFixed(1),
      ceiling:+ceiling.toFixed(1),avg:+avg.toFixed(1),top5:t5.map(r=>r.ticker)};
  }).sort((a,b)=>b.composite-a.composite);

  return { stocks:liq, momentum, cross, sectors, meta:{
    date: liq[0]?.date||'—', liquid_count:liq.length, total_count:rows.length,
    has_rs_delta:has('rs_delta'), has_rs_delta_momentum:has('rs_delta_momentum'),
    has_pct_52w:has('pct_from_52w_high'), has_sma10:has('price_vs_sma10'), has_sma20:has('price_vs_sma20'),
  }};
}

document.getElementById('csv-input').addEventListener('change', function(e) {
  const file = e.target.files[0]; if (!file) return;
  const btn=document.getElementById('upload-btn'), st=document.getElementById('upload-status');
  st.textContent='reading…';
  const reader = new FileReader();
  reader.onload = ev => {
    try {
      const {headers,rows} = parseCSV(ev.target.result);
      if (!headers.includes('ticker')||!headers.includes('rs_score')) throw new Error('not a valid IDX RS CSV');
      ACTIVE = buildDataFromCSV(rows, headers);
      Object.keys(state.filters).forEach(t=>state.filters[t]={});
      document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
      Object.keys(state.topN).forEach(t=>state.topN[t]='ALL');
      state.minTf=2;
      state.sorts={rs:[{col:'rs_score',dir:-1}],m1:[{col:'pct_1m',dir:-1}],m3:[{col:'pct_3m',dir:-1}],cross:[{col:'tf_count_10',dir:-1},{col:'avg_pct',dir:-1}],mom:[{col:'accel',dir:-1}]};
      updateHeader(); initPills(); renderAll();
      btn.className='upload-btn success';
      st.textContent=file.name.replace('idx_rs_rankings_','').replace('.csv','');
    } catch(err) { btn.className='upload-btn error'; st.textContent='error: '+err.message; }
    e.target.value='';
  };
  reader.readAsText(file);
});

// ── FORMATTERS ─────────────────────────────────────────────
const N=()=>'<span class="null-val">—</span>';
const fmtVol=v=>{ if(v==null)return N(); if(v>=1e9)return(v/1e9).toFixed(1)+'B'; if(v>=1e6)return(v/1e6).toFixed(1)+'M'; return(v/1e3).toFixed(0)+'K'; };
const fmtPct=v=>{ if(v==null)return N(); const c=v>=80?'pct-green':v>=50?'pct-neutral':'pct-red'; return`<span class="${c}">${v}</span>`; };
const fmtDelta=v=>{ if(v==null)return N(); const c=v>5?'delta-green':v<-5?'delta-red':'delta-neutral'; return`<span class="${c}">${v>0?'+':''}${v.toFixed(1)}</span>`; };
const fmtDMom=v=>{ if(v==null)return N(); const c=v>2?'delta-green':v<-2?'delta-red':'delta-neutral'; return`<span class="${c}">${v>0?'+':''}${v.toFixed(1)}</span>`; };
const fmt52w=v=>{ if(v==null)return N(); const c=v>=-10?'hi-green':v>=-25?'hi-amber':'hi-red'; return`<span class="${c}">${v>0?'+':''}${v.toFixed(1)}%</span>`; };
const fmtSma=v=>{ if(v==null)return N(); const c=v>0?'sma-pos':v<0?'sma-neg':'sma-neu'; return`<span class="${c}">${v>0?'+':''}${v.toFixed(1)}%</span>`; };
const fmtSector=s=>{ const[fg,bg]=SECTOR_COLORS[s]||['#8892b0','rgba(136,146,176,0.12)']; return`<span class="sector-badge" style="color:${fg};background:${bg}">${s||'—'}</span>`; };

function fmtShape(v) {
  if (v==null) return N();
  if (v > 5)  return `<span class="shape-up">▲ ${v.toFixed(1)}</span>`;
  if (v < -5) return `<span class="shape-dn">▼ ${v.toFixed(1)}</span>`;
  return `<span class="shape-neu">→ ${v.toFixed(1)}</span>`;
}
function fmtTfDiamonds(v) {
  if (v==null) return N();
  return '<div class="tf-diamonds">' +
    [0,1,2,3].map(i=>`<div class="tf-diamond ${i<v?'on':'off'}"></div>`).join('') +
  '</div>';
}

// ── COLUMN DEFINITIONS ─────────────────────────────────────
function makeCols(meta, mode) {
  // mode: 'rs'|'m1'|'m3'|'cross'|'mom'
  const base = [
    {k:'rank',    lbl:'#',       left:false, fmt:v=>`<span class="rank-cell">${v??'—'}</span>`},
    {k:'ticker',  lbl:'TICKER',  left:true,  fmt:v=>`<span class="ticker">${v}</span>`},
    {k:'sector',  lbl:'SECTOR',  left:true,  fmt:fmtSector, sk:'sector'},
    {k:'rs_score',lbl:'RS SCORE',left:false, fmt:v=>v!=null?v.toFixed(2):'—'},
  ];
  if (mode==='mom') base.splice(3,0,{k:'accel',lbl:'ACCEL+',left:false,fmt:v=>{
    if(v==null)return'—'; const c=v>=25?'accel-high':'accel-mid';
    return`<span class="accel-badge ${c}">+${v}</span>`;
  }});
  if (mode==='cross') {
    base.splice(3,0,
      {k:'tf_count_10',lbl:'# TFs (top 10%)',left:false,fmt:fmtTfDiamonds},
      {k:'avg_pct',    lbl:'AVG PCTILE',      left:false,fmt:v=>v!=null?`<span class="avg-cell">${v.toFixed(0)}</span>`:N()},
      {k:'shape_score',lbl:'SHAPE SCORE',     left:false,fmt:fmtShape},
    );
  }
  if (meta.has_rs_delta)          base.push({k:'rs_delta',          lbl:'RS Δ 4W<span class="badge-new">NEW</span>',  left:false,fmt:fmtDelta});
  if (meta.has_rs_delta_momentum) base.push({k:'rs_delta_momentum', lbl:'Δ MOM<span class="badge-new">NEW</span>',    left:false,fmt:fmtDMom});
  if (meta.has_pct_52w)           base.push({k:'pct_from_52w_high', lbl:'52W HI%<span class="badge-new">NEW</span>', left:false,fmt:fmt52w});
  base.push(
    {k:'percentile',lbl:'RS %ILE',left:false,fmt:fmtPct},
    {k:'pct_1m',    lbl:'1M %',   left:false,fmt:fmtPct},
    {k:'pct_3m',    lbl:'3M %',   left:false,fmt:fmtPct},
    {k:'pct_6m',    lbl:'6M %',   left:false,fmt:fmtPct},
    {k:'pct_12m',   lbl:'12M %',  left:false,fmt:fmtPct},
  );
  if (meta.has_sma10) base.push({k:'price_vs_sma10', lbl:'SMA10<span class="badge-new">NEW</span>', left:false,fmt:fmtSma});
  if (meta.has_sma20) base.push({k:'price_vs_sma20', lbl:'SMA20<span class="badge-new">NEW</span>', left:false,fmt:fmtSma});
  base.push(
    {k:'price_vs_sma50',  lbl:'SMA50',  left:false,fmt:fmtSma},
    {k:'price_vs_sma200', lbl:'SMA200', left:false,fmt:fmtSma},
    {k:'avg_vol_30d',     lbl:'VOL 30D',left:false,fmt:fmtVol},
  );
  return base;
}

// ── FILTER & SORT ──────────────────────────────────────────
function applyFilters(tab, data) {
  const f = state.filters[tab];
  if (f.rising) data=data.filter(r=>r.rs_delta!=null&&r.rs_delta>0);
  if (f.near52) data=data.filter(r=>r.pct_from_52w_high!=null&&r.pct_from_52w_high>=-15);
  if (f.sma10)  data=data.filter(r=>r.price_vs_sma10!=null&&r.price_vs_sma10>0);
  if (f.sma20)  data=data.filter(r=>r.price_vs_sma20!=null&&r.price_vs_sma20>0);
  if (f.sma50)  data=data.filter(r=>r.price_vs_sma50!=null&&r.price_vs_sma50>0);
  if (f.sma200) data=data.filter(r=>r.price_vs_sma200!=null&&r.price_vs_sma200>0);
  if (f.accel)  data=data.filter(r=>r.shape_score!=null&&r.shape_score>0);
  return data;
}

function sortData(data, sorts) {
  return [...data].sort((a,b)=>{
    for(const {col,dir} of sorts){
      const va=col==='sector'?(a.sector||''):(a[col]??-Infinity);
      const vb=col==='sector'?(b.sector||''):(b[col]??-Infinity);
      if(va<vb)return dir; if(va>vb)return -dir;
    }
    return 0;
  });
}

function toggleFilter(tab, key) {
  state.filters[tab][key]=!state.filters[tab][key];
  const btn=document.getElementById(`${tab}-${key}`);
  if(btn) btn.classList.toggle('active', state.filters[tab][key]);
  renderTable(tab);
}

function handleSort(tab, col) {
  const sorts=state.sorts[tab];
  const idx=sorts.findIndex(s=>s.col===col);
  if(idx===0){sorts[0].dir*=-1;}
  else if(idx>0){const[s]=sorts.splice(idx,1);s.dir=-1;sorts.unshift(s);}
  else{sorts.unshift({col,dir:-1});if(sorts.length>3)sorts.pop();}
  renderTable(tab);
}

// ── RENDER TABLE ───────────────────────────────────────────
const TAB_SORT_COL = {rs:'rs_score', m1:'pct_1m', m3:'pct_3m'};

function renderTable(tab) {
  const cols = makeCols(ACTIVE.meta, tab);
  let data;
  if (tab==='mom')   data = ACTIVE.momentum.map(r=>({...r}));
  else if (tab==='cross') {
    data = ACTIVE.cross.filter(r=>r.tf_count_10>=state.minTf).map(r=>({...r}));
  } else {
    data = [...ACTIVE.stocks];
    // Apply TOP N before other filters (against full liquid universe)
    const primaryCol = TAB_SORT_COL[tab];
    data = applyTopN(data, tab, primaryCol);
  }
  data = applyFilters(tab, data);
  const sorted = sortData(data, state.sorts[tab]);
  const total  = sorted.length;

  const tbl   = document.getElementById('tbl-'+tab);
  const sorts = state.sorts[tab];

  tbl.querySelector('thead').innerHTML = '<tr>' + cols.map(c => {
    const sk=c.sk||c.k; const si=sorts.findIndex(s=>s.col===sk);
    let cls=c.left?'left':'';
    if(si===0) cls+=sorts[0].dir===-1?' sorted-desc':' sorted-asc';
    return `<th class="${cls.trim()}" onclick="handleSort('${tab}','${sk}')">${c.lbl}</th>`;
  }).join('')+'</tr>';

  tbl.querySelector('tbody').innerHTML = sorted.map((row,i)=>{
    const p=i/total;
    const tier=p<0.01?'tier-gold':p<0.02?'tier-silver':p<0.05?'tier-blue':'';
    return `<tr class="${tier}">${cols.map(c=>{
      const v=row[c.sk||c.k]!==undefined?row[c.sk||c.k]:row[c.k];
      return `<td${c.left?' class="left"':''}>${c.fmt(v,row)}</td>`;
    }).join('')}</tr>`;
  }).join('');

  const ce=document.getElementById(tab+'-count');
  if(ce) ce.textContent=total+' stocks';
}

// ── RENDER SECTORS ─────────────────────────────────────────
function renderSectors() {
  document.getElementById('sector-grid').innerHTML = ACTIVE.sectors.map((s,i)=>{
    const [fg]=SECTOR_COLORS[s.sector]||['#8892b0'];
    const mc=v=>v>=50?'var(--green)':v>=30?'var(--amber)':'var(--red)';
    const bar=(lbl,val)=>`<div class="bar-row"><span class="bar-label">${lbl}</span><div class="bar-track"><div class="bar-fill" style="width:${Math.min(val,100)}%;background:${fg};opacity:.7"></div></div><span class="bar-val">${(+val).toFixed(0)}</span></div>`;
    const chips=(s.top5||[]).map((t,ti)=>`<span class="sector-chip${ti===0?' leader':''}">${t}</span>`).join('');
    return `<div class="sector-card">
      <div class="sector-card-header"><span class="sector-card-name" style="color:${fg}">${s.sector}</span><span class="sector-card-rank">#${i+1} · ${s.count} stocks</span></div>
      <div class="sector-composite">${s.composite.toFixed(1)}</div>
      <div class="sector-metrics">
        <div class="sector-metric"><div class="sector-metric-label">BREADTH 1M</div><div class="sector-metric-val" style="color:${mc(s.breadth_1m)}">${s.breadth_1m.toFixed(0)}%</div></div>
        <div class="sector-metric"><div class="sector-metric-label">BREADTH 3M</div><div class="sector-metric-val" style="color:${mc(s.breadth_3m)}">${s.breadth_3m.toFixed(0)}%</div></div>
        <div class="sector-metric"><div class="sector-metric-label">BREADTH 6M</div><div class="sector-metric-val" style="color:${mc(s.breadth_6m)}">${s.breadth_6m.toFixed(0)}%</div></div>
        <div class="sector-metric"><div class="sector-metric-label">CEILING</div><div class="sector-metric-val">${s.ceiling.toFixed(0)}</div></div>
        <div class="sector-metric"><div class="sector-metric-label">AVG 1M</div><div class="sector-metric-val">${s.avg.toFixed(0)}</div></div>
        <div class="sector-metric"><div class="sector-metric-label">MULTI BRD</div><div class="sector-metric-val">${s.multi_breadth.toFixed(0)}</div></div>
      </div>
      ${bar('BREADTH 1M',s.breadth_1m)}${bar('BREADTH 3M',s.breadth_3m)}${bar('BREADTH 6M',s.breadth_6m)}${bar('CEILING',s.ceiling)}${bar('AVG 1M',s.avg)}
      <div class="sector-tickers">${chips}</div>
    </div>`;
  }).join('');
}

// ── TAB SWITCH ─────────────────────────────────────────────
function switchTab(tab, el, color) {
  document.querySelectorAll('.tab').forEach(t=>t.className='tab');
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  el.classList.add('active-'+color);
  document.getElementById('panel-'+tab).classList.add('active');
  state.activeTab=tab;
  if(tab==='sec') renderSectors();
  else renderTable(tab);
}

// ── HEADER ─────────────────────────────────────────────────
function updateHeader() {
  const m=ACTIVE.meta;
  document.getElementById('hDate').textContent  = m.date;
  document.getElementById('hLiq').textContent   = m.liquid_count;
  document.getElementById('hTotal').textContent = m.total_count;
  const badges=[];
  if(m.has_rs_delta)          badges.push('RS Δ');
  if(m.has_rs_delta_momentum) badges.push('Δ MOM');
  if(m.has_pct_52w)           badges.push('52W HI%');
  if(m.has_sma10)             badges.push('SMA10');
  if(m.has_sma20)             badges.push('SMA20');
  document.getElementById('newBadgeWrap').innerHTML=badges.map(b=>`<span class="badge-new">${b}</span>`).join(' ');
}

function initPills() {
  ['rs','m1','m3'].forEach(buildTopPills);
  buildTfPills();
}

function renderAll() {
  renderTable('rs');
  if(['m1','m3','cross','mom'].includes(state.activeTab)) renderTable(state.activeTab);
  else if(state.activeTab==='sec') renderSectors();
}

// ── INIT ───────────────────────────────────────────────────
EMBEDDED.momentum.forEach(r=>{ if(r.accel==null) r.accel=r.pct_1m-r.pct_3m; });
updateHeader();
initPills();
renderTable('rs');

// ── HELP MODAL ─────────────────────────────────────────────
function openHelp()  { document.getElementById('help-modal').classList.add('open'); }
function closeHelp() { document.getElementById('help-modal').classList.remove('open'); }
function switchHelpTab(id, el) {
  document.querySelectorAll('.modal-tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.modal-section').forEach(s=>s.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('help-'+id).classList.add('active');
}
document.addEventListener('keydown', e => { if(e.key==='Escape') closeHelp(); });
