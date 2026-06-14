"""HTML/CSS/JS for the Skull arena dashboard. Imported by dashboard_server.py.

Mirrors the Exploding Kittens dashboard layout (full-width counters row, live
game on the left, leaderboard on the right, recent-results feed below) but drives
it from the Skull engine's event stream — placing discs, bidding, and flipping.
"""

SKULL_PAGE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Skull — Live Arena</title>
<style>
  :root {
    --bg:#0b0f17; --surface:#131a26; --surface2:#0f1521; --border:#223049;
    --accent:#eab308; --accent2:#38bdf8;
    --text:#e7edf6; --muted:#8b9bb4;
    --green:#34d399; --red:#fb7185; --rose:#f472b6; --yellow:#fbbf24;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body {
    background: radial-gradient(1200px 600px at 50% -200px, #16203288 0%, var(--bg) 60%);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size:15px; line-height:1.5; padding:0 1rem 4rem; min-height:100vh;
  }
  .page { max-width:1340px; margin:0 auto; }
  a { color:var(--accent2); text-decoration:none; }

  header { padding:2.2rem 0 1.2rem; display:flex; flex-wrap:wrap; align-items:flex-start; gap:1rem; justify-content:space-between;}
  header h1 { font-size:1.9rem; color:var(--accent); letter-spacing:-0.5px; }
  header h1 .spark { animation:pulse 2.4s ease-in-out infinite; display:inline-block; filter:drop-shadow(0 0 10px #eab30855);}
  header p { color:var(--muted); font-size:0.9rem; margin-top:0.25rem; max-width:640px;}
  .build { font-size:0.66rem; color:#64748b; font-family:"JetBrains Mono",monospace; text-align:right; flex-shrink:0; max-width:min(100%,520px); }
  .build a { color:var(--accent2); }

  /* full-width counter bar (matches EK) */
  .counters { display:flex; gap:0.6rem; flex-wrap:wrap; margin:0.4rem 0 1.6rem; }
  .counter { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:0.6rem 1rem; min-width:120px; flex:1; }
  .counter .val { font-size:1.5rem; font-weight:700; font-variant-numeric:tabular-nums; }
  .counter .lab { font-size:0.7rem; text-transform:uppercase; letter-spacing:0.07em; color:var(--muted); }
  .counter .val.live::after{ content:""; display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--green); margin-left:8px; vertical-align:middle; animation:pulse 1.3s infinite;}

  .grid { display:grid; grid-template-columns:1fr 360px; gap:1rem; align-items:start; }
  @media (max-width:900px){ .grid{ grid-template-columns:1fr; } }
  .section-title { font-size:1.05rem; color:var(--accent); margin:1.9rem 0 0.8rem; display:flex; flex-wrap:wrap; align-items:baseline; gap:0.6rem; }
  .section-title .section-sub { font-size:0.78rem; color:var(--muted); font-weight:400; }
  .card { background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:1rem 1.1rem; }
  .card h2 { font-size:0.78rem; text-transform:uppercase; letter-spacing:0.08em; color:var(--accent2); margin-bottom:0.8rem; display:flex; justify-content:space-between; align-items:center;}

  /* ---- live game ---- */
  .stage { height:130px; display:flex; flex-direction:column; align-items:center; justify-content:center;
           background:var(--surface2); border:1px solid var(--border); border-radius:12px; margin-bottom:0.9rem;
           text-align:center; overflow:hidden; position:relative; }
  .stage .big { font-size:2.7rem; line-height:1; }
  .stage .msg { color:var(--text); font-size:0.95rem; margin-top:0.4rem; padding:0 1rem; }
  .stage .turn-tag{ position:absolute; top:8px; left:12px; font-size:0.72rem; color:var(--muted); }
  .stage .bid-tag{ position:absolute; top:8px; right:12px; font-size:0.72rem; color:var(--muted); }
  .stage.flash-red { animation:flashRed .5s; } .stage.flash-green { animation:flashGreen .5s; }
  .stage.shake .big { animation:shake .5s; }

  .players { display:grid; grid-template-columns:repeat(4,1fr); gap:0.5rem; }
  @media (max-width:560px){ .players{ grid-template-columns:repeat(2,1fr);} }
  .player { background:var(--surface2); border:1px solid var(--border); border-radius:12px; padding:0.7rem 0.45rem; text-align:center; position:relative; transition:all .25s;}
  .player .av { font-size:1.6rem; line-height:1; }
  .player .nm { font-weight:600; font-size:0.82rem; margin-top:0.15rem; }
  .player .pts { margin-top:3px; letter-spacing:2px; font-size:0.7rem; color:var(--accent); }
  .player .discs { display:flex; flex-wrap:wrap; justify-content:center; gap:3px; margin-top:0.5rem; min-height:30px; align-content:flex-start;}
  .player .disc { width:22px; height:22px; border-radius:5px; display:grid; place-items:center; font-size:13px; background:#1b2434; border:1px solid #2a3a55; }
  .player .disc.down { color:#46587a; }
  .player .disc.rose { background:#3a1330; border-color:#f472b655; }
  .player .disc.skull { background:#3a1320; border-color:#fb718577; }
  .player .disc.pop { animation:discPop .35s ease; }
  .player .owned { display:flex; justify-content:center; gap:3px; margin-top:6px; }
  .player .owned i { width:6px; height:6px; border-radius:50%; background:#2a3a55; }
  .player .owned i.on { background:var(--rose); }
  .player.current { border-color:var(--accent); box-shadow:0 0 0 1px var(--accent), 0 0 22px -6px var(--accent); transform:translateY(-3px); }
  .player.current::before{ content:"▶ TURN"; position:absolute; top:-9px; left:50%; transform:translateX(-50%); font-size:0.6rem; background:var(--accent); color:#1a1d27; padding:1px 7px; border-radius:6px; font-weight:700; letter-spacing:.05em;}
  .player.dead { opacity:0.4; filter:grayscale(0.85); }
  .player.winner { border-color:var(--yellow); box-shadow:0 0 24px -4px var(--yellow); }
  .player.winner::after{ content:"\1F451"; position:absolute; top:-16px; left:50%; transform:translateX(-50%); font-size:1.2rem; }
  .player .pop2 { position:absolute; top:-6px; right:-4px; font-size:1.1rem; animation:popUp .9s ease-out forwards; pointer-events:none;}

  .ticker { margin-top:0.9rem; height:150px; overflow:hidden; border-top:1px solid var(--border); padding-top:0.6rem; }
  .ticker .line { font-size:0.8rem; color:var(--muted); padding:1px 0; opacity:0; animation:slideIn .3s forwards; }
  .ticker .line b { color:var(--text); font-weight:600; }
  .ticker .line.hot b { color:var(--accent); }

  .speed { display:flex; gap:4px; }
  .speed button { background:var(--surface2); border:1px solid var(--border); color:var(--muted); font-size:0.72rem; padding:2px 8px; border-radius:6px; cursor:pointer; }
  .speed button.on { background:var(--accent2); color:#0b0f17; border-color:var(--accent2); font-weight:700; }
  .legend { font-size:0.7rem; color:var(--muted); margin-top:0.5rem; }

  /* ---- leaderboard ---- */
  .lb-sub { font-size:0.68rem; color:var(--muted); margin:-0.3rem 0 0.7rem; }
  .lb-row { display:flex; align-items:center; gap:0.6rem; padding:0.55rem 0; border-bottom:1px solid var(--border); }
  .lb-row:last-child{ border-bottom:none; }
  .lb-rank { font-size:0.8rem; color:var(--muted); width:18px; text-align:center; font-weight:700;}
  .lb-av { font-size:1.4rem; }
  .lb-main { flex:1; min-width:0; }
  .lb-name { font-weight:600; font-size:0.86rem; }
  .lb-blurb{ font-size:0.66rem; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .lb-author{ color:#64748b; font-style:italic; }
  .lb-bar { height:7px; background:var(--surface2); border-radius:4px; overflow:hidden; margin-top:4px; }
  .lb-bar i { display:block; height:100%; border-radius:4px; transition:width .6s; }
  .lb-right { text-align:right; }
  .lb-elo { font-weight:800; font-size:1.25rem; font-variant-numeric:tabular-nums; line-height:1.15; }
  .lb-wr { font-weight:700; font-size:1.0rem; color:#cbd5e1; font-variant-numeric:tabular-nums; line-height:1.2; margin-top:1px; }
  .lb-unit{ font-size:0.56rem; color:var(--muted); font-weight:700; letter-spacing:0.05em; margin-left:3px; }
  .lb-prov{ font-size:0.6rem; color:var(--yellow); border:1px solid var(--yellow); border-radius:3px; padding:0 3px; margin-left:3px; vertical-align:middle; font-weight:700;}
  .lb-games{ font-size:0.64rem; color:var(--muted); text-align:right; margin-top:2px; }
  .spark { display:flex; gap:2px; margin-top:4px; }
  .spark i { width:5px; height:5px; border-radius:1px; background:#333a52; }
  .spark i.w { background:var(--green); }

  /* ---- row 2 ---- */
  .row2 { display:grid; grid-template-columns:1fr 1fr; gap:1rem; margin-top:1rem; }
  @media (max-width:900px){ .row2{ grid-template-columns:1fr; } }
  .row3 { display:grid; grid-template-columns:2fr 1fr; gap:1rem; margin-top:1rem; align-items:start; }
  @media (max-width:900px){ .row3{ grid-template-columns:1fr; } }
  .ladtabs { display:inline-flex; gap:4px; }
  .ladtabs button { background:var(--surface2); border:1px solid var(--border); color:var(--muted); font-size:0.7rem; padding:2px 9px; border-radius:6px; cursor:pointer; font-weight:600; }
  .ladtabs button.on { background:var(--accent2); color:#0b0f17; border-color:var(--accent2); font-weight:700; }
  .feed-row { display:flex; align-items:center; gap:0.6rem; padding:0.4rem 0; border-bottom:1px solid var(--border); font-size:0.82rem;}
  .feed-row:last-child{border-bottom:none;}
  .feed-row .w { font-weight:600; }
  .feed-row .meta { margin-left:auto; color:var(--muted); font-size:0.74rem; }
  .how { font-size:0.82rem; color:var(--muted); line-height:1.9; }
  .how b { color:var(--text); }
  .footer{ text-align:center; color:var(--muted); font-size:0.74rem; margin-top:2rem;}

  @keyframes pulse { 0%,100%{opacity:1;} 50%{opacity:0.35;} }
  @keyframes slideIn { from{opacity:0; transform:translateX(-6px);} to{opacity:1; transform:none;} }
  @keyframes shake { 0%,100%{transform:none;} 20%{transform:translateX(-7px) rotate(-4deg);} 40%{transform:translateX(7px) rotate(4deg);} 60%{transform:translateX(-5px);} 80%{transform:translateX(5px);} }
  @keyframes flashRed { 0%{background:#3a1d22;} 100%{background:var(--surface2);} }
  @keyframes flashGreen { 0%{background:#16321f;} 100%{background:var(--surface2);} }
  @keyframes popUp { 0%{opacity:0; transform:translateY(4px) scale(.6);} 30%{opacity:1; transform:translateY(-6px) scale(1.1);} 100%{opacity:0; transform:translateY(-22px) scale(1);} }
  @keyframes discPop { from{transform:scale(.4); opacity:0;} to{transform:scale(1); opacity:1;} }

  /* ---- deploy-change notification ---- */
  #deploy-banner{
    position:fixed; top:0; left:0; right:0; z-index:9999;
    background:linear-gradient(90deg,#7f1d1d,#991b1b); border-bottom:2px solid #ef4444;
    color:#fef2f2; padding:.75rem 1.2rem;
    display:flex; align-items:center; justify-content:space-between; gap:1rem;
    font-size:.9rem; font-weight:600; box-shadow:0 4px 24px rgba(239,68,68,.4);
    animation:deploySlideIn .35s cubic-bezier(.17,.67,.36,1.2) forwards;
  }
  @keyframes deploySlideIn{ from{transform:translateY(-100%);} to{transform:translateY(0);} }
  #deploy-banner .db-msg{ display:flex; align-items:center; gap:.6rem; }
  #deploy-banner .db-icon{ font-size:1.3rem; animation:deploySpinIcon 2s linear infinite; }
  @keyframes deploySpinIcon{ to{transform:rotate(360deg);} }
  #deploy-banner button{
    background:#ef4444; color:#fff; border:none; border-radius:8px;
    padding:.45rem 1rem; font-size:.85rem; font-weight:700; cursor:pointer;
    white-space:nowrap; transition:background .15s; flex-shrink:0;
  }
  #deploy-banner button:hover{ background:#dc2626; }
</style>
</head>
<body>
<div class="page">
  <header>
    <div>
      <h1><span class="spark">💀</span> Skull — Live Arena</h1>
      <p>Bluffing bots place discs, bid, and flip — first to two safe challenges wins. The randoms are the baseline; add a bot to beat them.</p>
    </div>
    <div class="build" id="build" title="which code is deployed, and who shipped it"></div>
  </header>

  <div class="counters">
    <div class="counter"><div class="val live" id="c-games">—</div><div class="lab">Games played</div></div>
    <div class="counter"><div class="val" id="c-gps">—</div><div class="lab">Games / sec</div></div>
    <div class="counter"><div class="val" id="c-rounds">—</div><div class="lab">Avg rounds / game</div></div>
    <div class="counter"><div class="val" id="c-up">—</div><div class="lab">Uptime</div></div>
  </div>

  <h2 class="section-title">🏆 Main Arena <span class="section-sub">first to two safe challenges wins</span></h2>
  <div class="grid">
    <!-- LIVE GAME -->
    <div class="card">
      <h2>Live Game
        <span class="speed" id="main-speed">
          <button data-s="1.6">0.5×</button>
          <button data-s="1" class="on">1×</button>
          <button data-s="0.5">2×</button>
          <button data-s="0.22">4×</button>
        </span>
      </h2>
      <div class="stage" id="stage">
        <div class="turn-tag" id="turntag"></div>
        <div class="bid-tag" id="bidtag"></div>
        <div class="big" id="stage-big">💀</div>
        <div class="msg" id="stage-msg">Dealing the next game…</div>
      </div>
      <div class="players" id="players"></div>
      <div class="legend">🌹 rose (safe) · 💀 skull (bust) · ▢ face-down · ● point · pips = discs left</div>
      <div class="ticker" id="ticker"></div>
    </div>

    <!-- LEADERBOARD -->
    <div class="card">
      <h2>Leaderboard</h2>
      <div class="lb-sub">ranked by win rate · ELO once the roster has 4+ distinct bots</div>
      <div id="leaderboard"></div>
    </div>
  </div>

  <div class="row2">
    <div class="card">
      <h2>Recent Results</h2>
      <div id="feed"></div>
    </div>
    <div class="card">
      <h2>How Skull works</h2>
      <div class="how">
        <p>Each bot has four discs: <b>three roses</b> and <b>one skull</b>.</p>
        <p style="margin-top:0.5rem">Players lay discs face-down, then <b>bid</b> how many they can flip without hitting a skull. The high bidder must flip that many — their own discs first, then opponents' tops.</p>
        <p style="margin-top:0.5rem">All roses up to the bid = a <b>point</b>. A skull = the bidder <b>loses a disc</b>. First to two points, or last bot with discs, wins.</p>
      </div>
    </div>
  </div>

  <h2 class="section-title">💀 Biggest Loser Arena <span class="section-sub">the goal here is to lose — bots ranked by how consistently they avoid winning · finish order is inverted</span></h2>
  <div class="grid">
    <!-- LOSER LIVE GAME -->
    <div class="card">
      <h2>Live Game
        <span class="speed" id="loser-speed">
          <button data-s="1.6">0.5×</button>
          <button data-s="1" class="on">1×</button>
          <button data-s="0.5">2×</button>
          <button data-s="0.22">4×</button>
        </span>
      </h2>
      <div class="stage" id="lstage">
        <div class="turn-tag" id="lturntag"></div>
        <div class="bid-tag" id="lbidtag"></div>
        <div class="big" id="lstage-big">💀</div>
        <div class="msg" id="lstage-msg">Dealing the next game…</div>
      </div>
      <div class="players" id="lplayers"></div>
      <div class="legend">🌹 rose (safe) · 💀 skull (bust) · ▢ face-down · ● point · pips = discs left</div>
      <div class="ticker" id="lticker"></div>
    </div>

    <!-- LOSER LEADERBOARD -->
    <div class="card">
      <h2>Loser Leaderboard
        <span class="ladtabs" id="loser-tabs">
          <button data-lm="no_win" class="on">No-Win %</button>
          <button data-lm="elo">Loser ELO</button>
        </span>
      </h2>
      <div class="lb-sub" id="loser-lb-sub"></div>
      <div id="loser-leaderboard"><div class="lb-blurb">Loading…</div></div>
      <div class="how" style="margin-top:0.9rem;border-top:1px solid var(--border);padding-top:0.7rem">
        <p><b>No-Win %</b> — share of games this bot did <b>not</b> win.</p>
        <p style="margin-top:0.4rem"><b>Loser ELO</b> — finish order is inverted, so the worst finisher scores best.</p>
        <p style="margin-top:0.4rem;font-size:0.72rem">Lineup: the biggest losers plus a random challenger each game.</p>
      </div>
    </div>
  </div>

  <div class="footer">Continuously simulated · stats persist across restarts</div>
</div>

<script>
const $ = id => document.getElementById(id);

function fmtUptime(s){
  const h=Math.floor(s/3600), m=Math.floor(s%3600/60);
  if(h>0) return `${h}h ${m}m`;
  return `${m}m ${s%60}s`;
}

/* ---------------- stats polling ---------------- */
let LAST_STATS = null;
async function pollStats(){
  try{
    const s = await (await fetch('/api/stats')).json();
    renderStats(s);
  }catch(e){}
  setTimeout(pollStats, 2000);
}
function renderStats(s){
  $('c-games').textContent = (s.total_games||0).toLocaleString();
  $('c-gps').textContent = (s.games_per_sec||0).toFixed(1);
  $('c-rounds').textContent = s.avg_turns;
  $('c-up').textContent = fmtUptime(s.uptime_secs||0);
  if(s.build){
    const sha = s.build.sha;
    const repo = 'https://github.com/danielbairddev/exploding_kittens';
    const url = (sha && sha!=='dev') ? (repo+'/commit/'+sha) : repo;
    $('build').innerHTML = `⚙ <a href="${url}" target="_blank" rel="noopener">${sha}</a> · deployed by ${s.build.by}`
      + (s.build.at?(' · '+s.build.at):'') + ` &nbsp;·&nbsp; <a href="${repo}" target="_blank" rel="noopener">repo</a>`;
  }
  LAST_STATS = s;
  renderLeaderboard(s.leaderboard||[]);
  renderFeed(s.recent_results||[]);
}
function renderLeaderboard(rows){
  rows = [...rows].sort((a,b)=> b.win_rate-a.win_rate || b.elo-a.elo);
  const wmax = Math.max(0.001, ...rows.map(b=>b.win_rate));
  $('leaderboard').innerHTML = rows.map((b,i)=>{
    const prov = b.provisional ? `<span class="lb-prov" title="provisional (<10 rated games)">?</span>` : '';
    const gl = b.games >= 1000 ? `${(b.games/1000).toFixed(1)}k` : `${b.games}`;
    const form = (b.recent||[]).slice(-12).map(w=>`<i class="${w?'w':''}"></i>`).join('');
    return `<div class="lb-row">
      <div class="lb-rank">${i+1}</div>
      <div class="lb-av">${b.emoji}</div>
      <div class="lb-main">
        <div class="lb-name" style="color:${b.color}">${b.name}</div>
        <div class="lb-blurb" title="${b.blurb}">${b.blurb} <span class="lb-author">· by ${b.author||'—'}</span></div>
        <div class="lb-bar"><i style="width:${(8+b.win_rate/wmax*92).toFixed(1)}%;background:${b.color}"></i></div>
        <div class="spark">${form}</div>
      </div>
      <div class="lb-right">
        <div class="lb-elo" style="color:${b.color}">${(b.win_rate*100).toFixed(1)}<span class="lb-unit">% WIN</span></div>
        <div class="lb-wr">${b.elo}${prov}<span class="lb-unit">ELO · ${b.avg_place??'–'} PLACE</span></div>
        <div class="lb-games">${gl} games</div>
      </div>
    </div>`;
  }).join('') || '<div class="lb-blurb">waiting for the first game…</div>';
}
function renderFeed(results){
  $('feed').innerHTML = results.map(g=>{
    const deaths = (g.deaths&&g.deaths.length)? ('💀 '+g.deaths.join(' → ')) : 'no eliminations';
    return `<div class="feed-row">
      <span style="font-size:1.1rem">${g.winner_emoji||'🏆'}</span>
      <span class="w">${g.winner}</span>
      <span class="meta">${deaths} · ${g.turns} rounds</span>
    </div>`;
  }).join('') || '<div class="lb-blurb">waiting for the first game…</div>';
}

/* ---------------- replay engine (one instance per arena) ---------------- */
function makeReplay(cfg){
  const E = id => document.getElementById(id);
  let SPEED = 1, table = null, tickerLines = [];
  document.querySelectorAll(cfg.speed+' button').forEach(btn=>{
    btn.onclick = ()=>{
      document.querySelectorAll(cfg.speed+' button').forEach(b=>b.classList.remove('on'));
      btn.classList.add('on'); SPEED = parseFloat(btn.dataset.s);
    };
  });
  const sleep = ms => new Promise(r=>setTimeout(r, ms*SPEED));
  const nm = seat => table.seats[seat] ? `<b style="color:${table.seats[seat].color}">${table.seats[seat].name}</b>` : '?';

  function renderTable(highlightWinner=-1){
    E(cfg.players).innerHTML = table.seats.map((p,seat)=>{
      let cls = 'player';
      if(seat===table.current && p.alive) cls+=' current';
      if(!p.alive) cls+=' dead';
      if(seat===highlightWinner) cls+=' winner';
      const pts = '●'.repeat(p.points)+'○'.repeat(Math.max(0,2-p.points));
      const owned = Array.from({length:4},(_,k)=>`<i class="${k<p.owned?'on':''}"></i>`).join('');
      const discs = p.revealed.map(d=>`<div class="disc pop ${d==='SKULL'?'skull':'rose'}">${d==='SKULL'?'💀':'🌹'}</div>`).join('')
                  + Array.from({length:p.faceDown},()=>`<div class="disc down">▢</div>`).join('');
      return `<div class="${cls}" id="${cfg.players}seat${seat}">
        <div class="av">${p.alive? p.emoji : '💀'}</div>
        <div class="nm" style="color:${p.color}">${p.name}</div>
        <div class="pts">${pts}</div>
        <div class="discs">${discs||'<span style="color:var(--muted);font-size:0.7rem">—</span>'}</div>
        <div class="owned">${owned}</div>
      </div>`;
    }).join('');
  }
  function pop(seat, emoji){
    const el = E(cfg.players+'seat'+seat); if(!el) return;
    const s = document.createElement('div'); s.className='pop2'; s.textContent=emoji;
    el.appendChild(s); setTimeout(()=>s.remove(), 900);
  }
  function setStage(big, msg, cls){
    E(cfg.big).textContent = big;
    E(cfg.msg).innerHTML = msg;
    const cur = table.current>=0 && table.seats[table.current] ? `${table.seats[table.current].emoji} ${table.seats[table.current].name}` : '';
    E(cfg.turntag).textContent = cur;
    E(cfg.bidtag).textContent = table.bid>0 ? `bid: ${table.bid}` : '';
    const st = E(cfg.stage);
    if(cls){ st.classList.add(cls); setTimeout(()=>st.classList.remove(cls), 520); }
  }
  function tick(html, hot){
    tickerLines.unshift(`<div class="line${hot?' hot':''}">${html}</div>`);
    tickerLines = tickerLines.slice(0,9);
    E(cfg.ticker).innerHTML = tickerLines.join('');
  }

  async function playGame(game){
    table = {
      seats: game.seats.map(s=>({...s, points:0, owned:4, faceDown:0, revealed:[], alive:true})),
      bid:0, current:-1
    };
    tickerLines = [];
    renderTable();
    setStage('🎴', `New game — <b>${game.seats.map(s=>s.emoji).join(' ')}</b> take their seats`);
    await sleep(900);
    for(const e of game.events){ await applyEvent(e); }
  }

  async function applyEvent(e){
    const p = e.player;
    switch(e.type){
      case 'round_start':
        table.seats.forEach(s=>{ s.faceDown=0; s.revealed=[]; });
        table.bid=0; table.current=e.starting_player;
        renderTable();
        setStage('🎴', `Round ${e.turn} — ${nm(e.starting_player)} leads`);
        await sleep(620); break;
      case 'place':
        table.seats[p].faceDown++; table.current=p; renderTable();
        setStage('🪙', `${nm(p)} places a disc face-down`);
        await sleep(360); break;
      case 'bid':
        table.current=p; table.bid=e.amount; renderTable();
        setStage('💰', `${nm(p)} ${e.opening?'opens the bidding at':'bids'} <b>${e.amount}</b>`);
        tick(`${nm(p)} bids ${e.amount}`, e.opening); await sleep(520); break;
      case 'pass':
        table.current=p; renderTable();
        setStage('🙅', `${nm(p)} passes`); await sleep(360); break;
      case 'challenge':
        table.current=p; table.bid=e.bid; renderTable();
        setStage('🎯', `${nm(p)} must flip <b>${e.bid}</b> without a skull`);
        tick(`${nm(p)} takes the challenge — must flip ${e.bid}`, true); await sleep(720); break;
      case 'reveal': {
        const o = table.seats[e.owner];
        if(o){ o.faceDown=Math.max(0,o.faceDown-1); o.revealed.push(e.disc); }
        table.current=p; renderTable();
        if(e.disc==='SKULL'){
          pop(e.owner,'💀');
          setStage('💀', `${nm(p)} flips ${nm(e.owner)}'s <b style="color:var(--red)">SKULL!</b>`, 'shake');
          const st=E(cfg.stage); st.classList.add('flash-red'); setTimeout(()=>st.classList.remove('flash-red'),520);
          tick(`💀 ${nm(p)} hits ${nm(e.owner)}'s skull!`, true); await sleep(1200);
        } else {
          setStage('🌹', `${nm(p)} flips a rose from ${nm(e.owner)}`);
          tick(`${nm(p)} flips 🌹 from ${nm(e.owner)}`); await sleep(740);
        }
        break;
      }
      case 'success':
        table.seats[p].points=e.points; table.current=p; renderTable(); pop(p,'🏆');
        setStage('🏆', `${nm(p)} <b style="color:var(--green)">SUCCEEDS!</b> ${e.points} point${e.points>1?'s':''}`, 'flash-green');
        tick(`🏆 ${nm(p)} succeeds — ${e.points} point${e.points>1?'s':''}`, true); await sleep(1200); break;
      case 'fail':
        table.seats[p].owned=e.discs_left; table.current=p; renderTable(); pop(p,'💥');
        setStage('💥', `${nm(p)} <b style="color:var(--red)">busts</b> — loses a disc (${e.discs_left} left)`);
        tick(`💥 ${nm(p)} busts and loses a disc`, true); await sleep(1100); break;
      case 'explode':
        table.seats[p].alive=false; if(table.current===p) table.current=-1; renderTable(); pop(p,'☠️');
        setStage('☠️', `${nm(p)} is <b style="color:var(--red)">eliminated!</b>`, 'shake');
        tick(`☠️ ${nm(p)} is eliminated`, true); await sleep(1400); break;
      case 'game_over': {
        table.current=-1; renderTable(e.winner);
        const w = table.seats[e.winner];
        if(w){ pop(e.winner,'👑'); setStage('👑', `<b style="color:var(--yellow)">${w.name} wins!</b>`, 'flash-green'); }
        tick(`👑 ${w? '<b>'+w.name+'</b> takes the game!' : 'game over'}`, true);
        await sleep(2600); break;
      }
      default: break;
    }
  }

  async function loop(){
    while(true){
      let game = null;
      try{ game = await (await fetch(cfg.url)).json(); }catch(e){}
      if(!game || !game.events){ await new Promise(r=>setTimeout(r,1500)); continue; }
      await playGame(game);
      await new Promise(r=>setTimeout(r,400));
    }
  }
  return { loop };
}

/* ---------------- biggest loser arena ---------------- */
let LAST_LOSER = null, LOSER_MODE = 'no_win';
const LOSER_DESC = {
  no_win: 'no-win rate · share of games this bot did not win — the primary losing metric',
  elo:    'loser ELO · rated skill at losing; finish order is inverted vs the main arena',
};
document.querySelectorAll('#loser-tabs button').forEach(btn=>{
  btn.onclick = ()=>{
    document.querySelectorAll('#loser-tabs button').forEach(b=>b.classList.remove('on'));
    btn.classList.add('on'); LOSER_MODE = btn.dataset.lm; renderLoserLadder();
  };
});
function renderLoserLadder(){
  if(!LAST_LOSER) return;
  const m = LOSER_MODE;
  const rows = [...(LAST_LOSER.leaderboard||[])];
  if(m==='elo') rows.sort((a,b)=>b.elo-a.elo);
  else          rows.sort((a,b)=>b.no_win_rate-a.no_win_rate);
  $('loser-lb-sub').textContent = LOSER_DESC[m];
  const vals = rows.map(x=> m==='elo'?x.elo : x.no_win_rate);
  const vmax = Math.max(0.001,...vals), vmin = Math.min(...vals), vspan = (vmax-vmin)||1;
  const barOf = b => { const v = m==='elo'?b.elo : b.no_win_rate;
    return m==='elo' ? 8+(v-vmin)/vspan*92 : 8+(v/vmax)*92; };
  $('loser-leaderboard').innerHTML = rows.map((b,i)=>{
    const prov = b.provisional ? `<span class="lb-prov" title="provisional (<10 rated games)">?</span>` : '';
    const gl = b.games >= 1000 ? `${(b.games/1000).toFixed(1)}k` : `${b.games}`;
    const big = m==='elo'
      ? `<div class="lb-elo" style="color:${b.color}">${b.elo}${prov}<span class="lb-unit">LOSER ELO</span></div>
         <div class="lb-wr">${(b.no_win_rate*100).toFixed(1)}<span class="lb-unit">% NO-WIN · ${b.avg_place??'–'} PLACE</span></div>`
      : `<div class="lb-elo" style="color:${b.color}">${(b.no_win_rate*100).toFixed(1)}<span class="lb-unit">% NO-WIN</span></div>
         <div class="lb-wr">${b.elo}<span class="lb-unit">LOSER ELO · ${b.avg_place??'–'} PLACE</span></div>`;
    return `<div class="lb-row">
      <div class="lb-rank">${i+1}</div>
      <div class="lb-av">${b.emoji}</div>
      <div class="lb-main">
        <div class="lb-name" style="color:${b.color}">${b.name}</div>
        <div class="lb-blurb" title="${b.blurb}">${b.blurb}</div>
        <div class="lb-bar"><i style="width:${barOf(b).toFixed(1)}%;background:${b.color}"></i></div>
      </div>
      <div class="lb-right">${big}<div class="lb-games">${gl} games</div></div>
    </div>`;
  }).join('') || '<div class="lb-blurb">waiting for the first game…</div>';
}
async function pollLoser(){
  try{ const s = await (await fetch('/api/loser_stats')).json(); LAST_LOSER = s; renderLoserLadder(); }catch(e){}
  setTimeout(pollLoser, 3000);
}

const MAIN_REPLAY = makeReplay({ stage:'stage', big:'stage-big', msg:'stage-msg',
  turntag:'turntag', bidtag:'bidtag', players:'players', ticker:'ticker',
  speed:'#main-speed', url:'/api/showcase' });
const LOSER_REPLAY = makeReplay({ stage:'lstage', big:'lstage-big', msg:'lstage-msg',
  turntag:'lturntag', bidtag:'lbidtag', players:'lplayers', ticker:'lticker',
  speed:'#loser-speed', url:'/api/loser_showcase' });

pollStats();
pollLoser();
MAIN_REPLAY.loop();
LOSER_REPLAY.loop();

// ---- Deploy-change notification ----
(function() {
  let _knownBuild = null;
  function showDeployBanner() {
    if (document.getElementById('deploy-banner')) return;
    const b = document.createElement('div');
    b.id = 'deploy-banner';
    b.innerHTML = `
      <div class="db-msg">
        <span class="db-icon">🔄</span>
        <span>A new version was deployed — refresh to get the latest</span>
      </div>
      <button onclick="location.reload()">Refresh now</button>`;
    document.body.insertBefore(b, document.body.firstChild);
  }
  async function checkVersion() {
    try {
      const {build} = await (await fetch('/api/version')).json();
      if (_knownBuild === null) { _knownBuild = build; return; }
      if (build !== _knownBuild) { _knownBuild = build; showDeployBanner(); }
    } catch(e) {}
  }
  checkVersion();
  setInterval(checkVersion, 30000);
})();
</script>
</body>
</html>'''
