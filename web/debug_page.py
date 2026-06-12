"""Secret debug page — /daniel — for monitoring training progress."""

DEBUG_PAGE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Daniel's Training Lab</title>
<style>
  :root {
    --bg:#0f1117; --surface:#1a1d27; --surface2:#20232f; --border:#2e3146;
    --accent:#f97316; --accent2:#818cf8; --text:#e2e8f0; --muted:#94a3b8;
    --green:#4ade80; --red:#f87171; --yellow:#fbbf24; --purple:#7c3aed;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; font-size:14px; padding:2rem; }
  h1 { color:var(--accent); font-size:1.6rem; margin-bottom:0.3rem; }
  .sub { color:var(--muted); font-size:0.82rem; margin-bottom:2rem; }
  .bots { display:grid; grid-template-columns:repeat(auto-fit,minmax(380px,1fr)); gap:1.5rem; }
  .bot { background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:1.2rem; }
  .bot-head { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:1rem; }
  .bot-name { font-size:1.1rem; font-weight:700; }
  .bot-stat { font-size:0.78rem; color:var(--muted); }
  .bot-stat b { color:var(--text); }
  svg.chart { width:100%; height:80px; display:block; margin-bottom:1rem; }
  h3 { font-size:0.7rem; text-transform:uppercase; letter-spacing:0.07em; color:var(--accent2); margin-bottom:0.5rem; }
  table { width:100%; border-collapse:collapse; font-size:0.8rem; }
  th { text-align:left; color:var(--muted); font-weight:600; font-size:0.68rem; text-transform:uppercase; letter-spacing:0.05em; padding:0 0 0.4rem; border-bottom:1px solid var(--border); }
  td { padding:0.4rem 0; border-bottom:1px solid var(--border); font-variant-numeric:tabular-nums; }
  tr:last-child td { border-bottom:none; }
  .win { font-weight:700; }
  .new { color:var(--green); font-size:0.65rem; font-weight:700; margin-left:4px; }
  .ago { color:var(--muted); }
  .no-data { color:var(--muted); font-style:italic; font-size:0.82rem; padding:0.5rem 0; }
  .log-section { margin-top:1rem; }
  .log-line { font-family:"JetBrains Mono",monospace; font-size:0.68rem; color:var(--muted); padding:2px 0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .log-line.best { color:var(--green); }
  .section { margin-top:2rem; }
  .deploy-log { font-family:"JetBrains Mono",monospace; font-size:0.7rem; color:var(--muted); background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:0.8rem 1rem; max-height:200px; overflow-y:auto; }
  .deploy-log .ok { color:var(--green); }
  .deploy-log .err { color:var(--red); }
  .refresh { font-size:0.72rem; color:var(--muted); float:right; }
  .status-row { display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:1.5rem; }
  .pill { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:0.4rem 0.9rem; font-size:0.78rem; }
  .pill .val { font-weight:700; }
  .pill .val.good { color:var(--green); }
  .pill .val.bad  { color:var(--red); }
</style>
</head>
<body>
<h1>🔬 Daniel's Training Lab</h1>
<p class="sub">Secret page — <a href="/" style="color:var(--accent2)">← back to arena</a> <span class="refresh" id="age"></span></p>

<div class="status-row" id="status-row"></div>

<div class="bots" id="bots"><p style="color:var(--muted)">Loading…</p></div>

<div class="section">
  <h3>Deploy log</h3>
  <div class="deploy-log" id="deploy-log">Loading…</div>
</div>

<script>
const COLORS = { Rhino:'#6b7280', Gorilla:'#f97316', Elephant:'#7c3aed' };
const EMOJI  = { Rhino:'🦏', Gorilla:'🦍', Elephant:'🐘' };
const LABEL  = { Rhino:'Rhino', Gorilla:'Orangutan2 (Gorilla trainer)', Elephant:'Elephant' };

function fmtTime(t){
  const d = new Date(t*1000);
  return d.toLocaleString('en-US',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:true});
}
function fmtAgo(t){
  const s = Math.floor(Date.now()/1000 - t);
  if(s < 90) return `${s}s ago`;
  if(s < 3600) return `${Math.floor(s/60)}m ago`;
  if(s < 86400) return `${Math.floor(s/3600)}h ${Math.floor(s%3600/60)}m ago`;
  return `${Math.floor(s/86400)}d ago`;
}

function makeChart(pts, color){
  const W=400, H=80, pad=6;
  if(!pts.length) return `<svg class="chart" viewBox="0 0 ${W} ${H}"><text x="${W/2}" y="${H/2+5}" text-anchor="middle" fill="#64748b" font-size="12">no data yet — waiting for iter 10</text></svg>`;
  const wins = pts.map(p=>p.win), bests = pts.map(p=>p.best);
  const minV = Math.min(...wins,...bests), maxV = Math.max(...wins,...bests);
  const span = (maxV-minV)||1;
  const x = i => (pad + i/(pts.length-1||1)*(W-pad*2)).toFixed(1);
  const y = v => (H-pad-((v-minV)/span)*(H-pad*2)).toFixed(1);
  const wl = pts.map((p,i)=>`${x(i)},${y(p.win)}`).join(' ');
  const bl = pts.map((p,i)=>`${x(i)},${y(p.best)}`).join(' ');
  const area = `${x(0)},${H-pad} ${wl} ${x(pts.length-1)},${H-pad}`;
  // y-axis labels
  const labels = [minV, (minV+maxV)/2, maxV].map((v,i)=>{
    const yy = [H-pad-2, H/2, pad+4][i];
    return `<text x="2" y="${yy}" fill="#64748b" font-size="9" dominant-baseline="middle">${v.toFixed(1)}%</text>`;
  }).join('');
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    ${labels}
    <polygon points="${area}" fill="${color}" opacity="0.1"/>
    <polyline points="${bl}" fill="none" stroke="${color}" stroke-width="1" stroke-dasharray="4,3" opacity="0.5" vector-effect="non-scaling-stroke"/>
    <polyline points="${wl}" fill="none" stroke="${color}" stroke-width="2.5" vector-effect="non-scaling-stroke"/>
    <circle cx="${x(pts.length-1)}" cy="${y(pts[pts.length-1].win)}" r="3" fill="${color}" vector-effect="non-scaling-stroke"/>
  </svg>`;
}

function renderBot(name, entry){
  const pts = entry.points || [], bests = entry.bests || [];
  const color = COLORS[name], emoji = EMOJI[name], label = LABEL[name];
  const last = pts.length ? pts[pts.length-1] : null;
  const statHtml = last
    ? `win <b>${last.win.toFixed(2)}%</b> · best <b>${last.best.toFixed(2)}%</b> · place <b>${last.place.toFixed(3)}</b> · iter <b>${last.iter}</b>`
    : `<i>baseline only — first eval at iter 10</i>`;

  const bestsHtml = bests.length ? `
    <table>
      <tr><th>#</th><th>Win %</th><th>Place</th><th>Iter</th><th>When</th><th></th></tr>
      ${[...bests].reverse().map((b,i)=>`
        <tr>
          <td style="color:var(--muted)">${bests.length-i}</td>
          <td class="win" style="color:${color}">${b.win.toFixed(2)}%</td>
          <td>${b.place.toFixed(3)}</td>
          <td>${b.iter}</td>
          <td>${fmtTime(b.t)}</td>
          <td class="ago">${fmtAgo(b.t)}</td>
        </tr>`).join('')}
    </table>` : `<p class="no-data">No bests recorded yet (starts writing on next training session restart)</p>`;

  return `<div class="bot">
    <div class="bot-head">
      <span class="bot-name">${emoji} ${label}</span>
      <span class="bot-stat">${statHtml}</span>
    </div>
    ${makeChart(pts, color)}
    <h3>New best milestones</h3>
    ${bestsHtml}
  </div>`;
}

async function load(){
  const [train, deploy] = await Promise.all([
    fetch('/api/training').then(r=>r.json()).catch(()=>({})),
    fetch('/api/debug/deploy_log').then(r=>r.text()).catch(()=>'unavailable'),
  ]);

  // status pills
  const bots = ['Rhino','Gorilla','Elephant'];
  const pills = bots.map(n=>{
    const pts = (train[n]||{}).points||[];
    const last = pts[pts.length-1];
    const val = last ? `${last.win.toFixed(1)}%` : '—';
    const cls = last ? 'good' : '';
    return `<div class="pill">${EMOJI[n]} ${n} <span class="val ${cls}">${val}</span></div>`;
  }).join('');
  document.getElementById('status-row').innerHTML = pills;

  document.getElementById('bots').innerHTML = bots.map(n=>renderBot(n, train[n]||{})).join('');

  // deploy log
  const lines = deploy.split('\n').filter(Boolean);
  document.getElementById('deploy-log').innerHTML = lines.slice(-40).reverse().map(l=>{
    const cls = l.includes('ERROR')||l.includes('WARN') ? 'err' : l.includes('live @') ? 'ok' : '';
    return `<div class="log-line ${cls}">${l}</div>`;
  }).join('');

  document.getElementById('age').textContent = `refreshed ${new Date().toLocaleTimeString()}`;
}

load();
setInterval(load, 30000);
</script>
</body>
</html>'''
