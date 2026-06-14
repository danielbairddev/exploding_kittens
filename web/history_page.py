HISTORY_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Win Rate History — EK Arena</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;padding:1.5rem}
h1{font-size:1rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#94a3b8;margin-bottom:1.5rem}
.nav{margin-bottom:1.5rem;font-size:0.8rem}
.nav a{color:#64748b;text-decoration:none}
.nav a:hover{color:#e2e8f0}
.controls{display:flex;gap:1rem;align-items:center;flex-wrap:wrap;margin-bottom:1rem}
.ctrl-label{font-size:0.72rem;color:#64748b;text-transform:uppercase;letter-spacing:.06em}
.btn-group{display:flex;gap:4px}
.btn{font-size:0.72rem;padding:4px 10px;border-radius:5px;border:1px solid #334155;background:transparent;color:#94a3b8;cursor:pointer}
.btn.on{background:#1e293b;color:#e2e8f0;border-color:#475569}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;margin-bottom:1rem}
.leg-item{display:flex;align-items:center;gap:5px;font-size:0.72rem;color:#94a3b8;cursor:pointer;user-select:none;padding:3px 6px;border-radius:4px;border:1px solid transparent}
.leg-item:hover{border-color:#334155}
.leg-item.off{opacity:0.3}
.leg-dot{width:10px;height:10px;border-radius:2px;flex-shrink:0}
.chart-wrap{position:relative;width:100%;height:420px}
.hint{font-size:0.68rem;color:#475569;margin-top:.5rem}
.status{font-size:0.75rem;color:#64748b;margin-top:.5rem}
</style>
</head>
<body>
<h2 class="sr-only">Bot win rate history over time</h2>
<div class="nav"><a href="/">← back to arena</a></div>
<h1>Win rate history</h1>
<div class="controls">
  <span class="ctrl-label">Metric</span>
  <div class="btn-group">
    <button class="btn on" id="btn-wr" onclick="setMetric('wr')">Win rate %</button>
    <button class="btn" id="btn-nwr" onclick="setMetric('nwr')">No-Win %</button>
    <button class="btn" id="btn-elo" onclick="setMetric('elo')">ELO</button>
  </div>
  <span class="ctrl-label" style="margin-left:.5rem">Show</span>
  <div class="btn-group">
    <button class="btn on" id="btn-all" onclick="toggleAll(true)">All</button>
    <button class="btn" id="btn-none" onclick="toggleAll(false)">None</button>
  </div>
  <button class="btn" style="margin-left:auto" onclick="resetZoom()">Reset zoom</button>
</div>
<div class="legend" id="legend"></div>
<div class="chart-wrap"><canvas id="chart" role="img" aria-label="Line chart of bot win rates over time"></canvas></div>
<div class="hint">Scroll to zoom · drag to pan</div>
<div class="status" id="status">Loading…</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script src="https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>
<script>if(typeof ChartZoom!=='undefined') Chart.register(ChartZoom);</script>
<script>
const BOT_COLORS = {
  'Professor':'#818cf8','Maverick':'#f97316','Gremlin':'#4ade80',
  'Sly':'#22d3ee','Lucky':'#a78bfa','Sly2':'#38bdf8','Coyote':'#fb923c',
  'Orangutan':'#f59e0b','Ian1':'#e879f9','Ian2':'#34d399',
  'Ian The Bomb':'#f43f5e','Perdition 2':'#ef4444',
  'Rhino':'#60a5fa','Elephant':'#a3e635',
  'Gabriel':'#d4af37','Orpheus':'#c084fc','Cassandra':'#fb7185',
  'Hades':'#94a3b8','Abaddon':'#f472b6',
};

let chart = null;
let metric = 'wr';
let hidden = new Set();
let parsed = null;

function norm(name){
  if(name==='Perdition2'||name==='Perdition 2.1') return 'Perdition 2';
  return name;
}

async function load(){
  const [winRes, loseRes] = await Promise.all([
    fetch('/api/winrate_history'),
    fetch('/api/loser_winrate_history').catch(()=>null),
  ]);
  const winText = await winRes.text();
  const loseText = loseRes ? await loseRes.text().catch(()=>'') : '';

  function parseTsv(text){
    const lines = text.trim().split('\\n').slice(1);
    const rows = [];
    for(let i=0;i<lines.length;i+=3){
      const parts = lines[i].split('\\t');
      if(parts.length<3) continue;
      const ts = parts[0].replace('T',' ').replace('Z','').slice(5,16);
      const bots={};
      for(const b of parts[2].split('|')){
        const p=b.split(':'); if(p.length<4) continue;
        bots[norm(p[0])]={rate:parseFloat(p[3])*100, elo:parseFloat(p[4]||1200)};
      }
      rows.push({ts,bots});
    }
    return rows;
  }

  const winRows = parseTsv(winText);
  const loseRows = parseTsv(loseText);
  // build loser lookup by timestamp for merging
  const loseByTs = {};
  for(const r of loseRows) loseByTs[r.ts] = r.bots;

  const allNames=new Set();
  for(const r of winRows) for(const n of Object.keys(r.bots)) allNames.add(n);

  const datasets=[];
  for(const name of [...allNames].sort()){
    const color=BOT_COLORS[name]||'#888';
    datasets.push({
      label:name, color,
      wr:  winRows.map(r=>r.bots[name]?Math.round(r.bots[name].rate*100)/100:null),
      elo: winRows.map(r=>r.bots[name]?Math.round(r.bots[name].elo):null),
      nwr: winRows.map(r=>{const lb=loseByTs[r.ts]; return lb&&lb[name]?Math.round(lb[name].rate*100)/100:null;}),
    });
  }

  parsed={labels:winRows.map(r=>r.ts),datasets};
  buildLegend();
  buildChart();
  document.getElementById('status').textContent=`${winRows.length} snapshots · last updated ${winRows[winRows.length-1]?.ts||''}`;
}

function buildLegend(){
  const el=document.getElementById('legend');
  el.innerHTML=parsed.datasets.map(d=>`
    <div class="leg-item${hidden.has(d.label)?' off':''}" id="leg-${CSS.escape(d.label)}" onclick="toggleBot('${d.label.replace(/'/g,"\\\\'")}')">
      <span class="leg-dot" style="background:${d.color}"></span>
      <span>${d.label}</span>
    </div>`).join('');
}

function buildChart(){
  if(chart) chart.destroy();
  const ds=parsed.datasets.filter(d=>!hidden.has(d.label)).map(d=>({
    label:d.label,
    data:metric==='wr'?d.wr:metric==='nwr'?d.nwr:d.elo,
    borderColor:d.color,
    backgroundColor:'transparent',
    borderWidth:1.5,
    pointRadius:0,
    spanGaps:true,
    tension:0.2,
  }));
  chart=new Chart(document.getElementById('chart'),{
    type:'line',
    data:{labels:parsed.labels,datasets:ds},
    options:{
      responsive:true,maintainAspectRatio:false,
      animation:false,
      interaction:{mode:'index',intersect:false},
      plugins:{
        legend:{display:false},
        tooltip:{
          backgroundColor:'#1e293b',borderColor:'#334155',borderWidth:1,
          titleColor:'#94a3b8',bodyColor:'#e2e8f0',
          callbacks:{label:ctx=>`${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(metric==='elo'?0:1)??'—'}${metric!=='elo'?'%':''}`}
        },
        zoom:{
          pan:{enabled:true,mode:'x'},
          zoom:{wheel:{enabled:true},pinch:{enabled:true},mode:'x'},
        }
      },
      scales:{
        x:{ticks:{color:'#475569',maxTicksLimit:12,font:{size:11}},grid:{color:'rgba(255,255,255,0.04)'}},
        y:{ticks:{color:'#475569',font:{size:11},callback:v=>metric!=='elo'?v+'%':v},grid:{color:'rgba(255,255,255,0.04)'}}
      }
    }
  });
}

function resetZoom(){ chart?.resetZoom(); }

function setMetric(m){
  metric=m;
  ['wr','nwr','elo'].forEach(k=>document.getElementById('btn-'+k)?.classList.toggle('on',m===k));
  if(parsed) buildChart();
}

function toggleBot(name){
  if(hidden.has(name)) hidden.delete(name); else hidden.add(name);
  document.getElementById('leg-'+CSS.escape(name))?.classList.toggle('off',hidden.has(name));
  if(parsed) buildChart();
}

function toggleAll(show){
  if(show) hidden.clear();
  else parsed.datasets.forEach(d=>hidden.add(d.label));
  buildLegend();
  if(parsed) buildChart();
}

load().catch(e=>{document.getElementById('status').textContent='Failed to load: '+e;});
</script>
</body>
</html>
"""
