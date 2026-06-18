"""HTML/CSS/JS for the Live Arena dashboard. Imported by dashboard_server.py."""

PAGE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Exploding Kittens — Live Arena</title>
<style>
  :root {
    --bg: #0f1117; --surface: #1a1d27; --surface2:#20232f; --border: #2e3146;
    --accent: #f97316; --accent2: #818cf8;
    --text: #e2e8f0; --muted: #94a3b8;
    --green: #4ade80; --red: #f87171; --pink:#f472b6; --yellow:#fbbf24;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: radial-gradient(1200px 600px at 50% -200px, #181b27 0%, var(--bg) 60%);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 15px; line-height: 1.5; padding: 0 1rem 4rem;
    min-height: 100vh;
  }
  .page { max-width: 1340px; margin: 0 auto; }
  a { color: var(--accent2); text-decoration: none; }
  a:hover { text-decoration: underline; }

  header { padding: 2.2rem 0 1.4rem; display:flex; flex-wrap:wrap; align-items:flex-start; gap:1rem; justify-content:space-between;}
  header h1 { font-size: 1.9rem; color: var(--accent); letter-spacing: -0.5px; }
  header h1 .spark { animation: pulse 2.4s ease-in-out infinite; display:inline-block;}
  header p { color: var(--muted); font-size: 0.9rem; margin-top: 0.25rem; }
  .toplinks { font-size:0.82rem; color:var(--muted); margin-top:0.35rem; }
  .build { font-size:0.66rem; color:#64748b; font-family:"JetBrains Mono",monospace; text-align:right; flex-shrink:0; max-width:min(100%,520px); }

  /* arena counter bar */
  .counters { display:flex; gap:0.6rem; flex-wrap:wrap; margin: 0.4rem 0 1.6rem; }
  .counter {
    background: var(--surface); border:1px solid var(--border); border-radius:10px;
    padding:0.6rem 1rem; min-width:120px; flex:1;
  }
  .counter .val { font-size:1.5rem; font-weight:700; font-variant-numeric: tabular-nums; }
  .counter .lab { font-size:0.7rem; text-transform:uppercase; letter-spacing:0.07em; color:var(--muted); }
  .counter .val.live::after{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--green);margin-left:8px;vertical-align:middle;animation:pulse 1.3s infinite;}

  .grid { display:grid; grid-template-columns: 1fr 360px; gap:1rem; align-items:start; }
  @media (max-width: 900px){ .grid{ grid-template-columns:1fr; } }

  .card { background: var(--surface); border:1px solid var(--border); border-radius:14px; padding:1rem 1.1rem; }
  .card h2 { font-size:0.78rem; text-transform:uppercase; letter-spacing:0.08em; color:var(--accent2); margin-bottom:0.8rem; display:flex; justify-content:space-between; align-items:center;}
  .card h2 .sub { color:var(--muted); font-weight:400; text-transform:none; letter-spacing:0; font-size:0.74rem;}

  /* ---------------- live table ---------------- */
  .table-wrap { position:relative; }
  .stage {
    height:120px; display:flex; flex-direction:column; align-items:center; justify-content:center;
    background: var(--surface2); border:1px solid var(--border); border-radius:12px; margin-bottom:0.9rem;
    text-align:center; overflow:hidden; position:relative;
  }
  .stage .big { font-size:2.6rem; line-height:1; transition: transform .2s; }
  .stage .msg { color:var(--text); font-size:0.95rem; margin-top:0.4rem; padding:0 1rem;}
  .stage .turn-tag{ position:absolute; top:8px; left:12px; font-size:0.72rem; color:var(--muted); }
  .stage .deck-tag{ position:absolute; top:8px; right:12px; font-size:0.72rem; color:var(--muted); }
  .stage.flash-red { animation: flashRed .5s; }
  .stage.flash-green { animation: flashGreen .5s; }
  .stage.shake .big { animation: shake .5s; }

  .players { display:grid; grid-template-columns: repeat(5,1fr); gap:0.45rem; }
  @media (max-width:560px){ .players{ grid-template-columns:repeat(3,1fr);} }
  .player {
    background: var(--surface2); border:1px solid var(--border); border-radius:12px;
    padding:0.7rem 0.45rem; text-align:center; position:relative; transition: all .25s;
  }
  .player .av { font-size:1.6rem; line-height:1; }
  .player .nm { font-weight:600; font-size:0.8rem; margin-top:0.15rem; }
  .player .ty { font-size:0.64rem; color:var(--muted); }
  .player .hand { display:flex; justify-content:center; gap:2px; margin-top:0.5rem; height:26px; align-items:flex-end; overflow:hidden; }
  .player .hand i {
    display:block; width:10px; height:20px; border-radius:3px; flex:none;
    background: linear-gradient(160deg,#3b3f57,#262a3c); border:1px solid #454a66;
  }
  .player .hcount{ font-size:0.66rem; color:var(--muted); margin-top:2px;}
  .player.current { border-color: var(--accent); box-shadow:0 0 0 1px var(--accent), 0 0 22px -6px var(--accent); transform: translateY(-3px); }
  .player.current::before{ content:"▶ TURN"; position:absolute; top:-9px; left:50%; transform:translateX(-50%); font-size:0.6rem; background:var(--accent); color:#1a1d27; padding:1px 7px; border-radius:6px; font-weight:700; letter-spacing:.05em;}
  .player.dead { opacity:0.4; filter: grayscale(0.85); }
  .player.winner { border-color: var(--yellow); box-shadow:0 0 24px -4px var(--yellow); }
  .player.winner::after{ content:"\1F451"; position:absolute; top:-16px; left:50%; transform:translateX(-50%); font-size:1.2rem; }
  .player .pop { position:absolute; top:-6px; right:-4px; font-size:1.1rem; animation: popUp .9s ease-out forwards; pointer-events:none;}

  .ticker { margin-top:0.9rem; height:150px; overflow:hidden; border-top:1px solid var(--border); padding-top:0.6rem; }
  .ticker .line { font-size:0.8rem; color:var(--muted); padding:1px 0; opacity:0; animation: slideIn .3s forwards; }
  .ticker .line b { color: var(--text); font-weight:600; }
  .ticker .line.hot b { color: var(--accent); }

  .speed { display:flex; gap:4px; }
  .speed button { background:var(--surface2); border:1px solid var(--border); color:var(--muted); font-size:0.72rem; padding:2px 8px; border-radius:6px; cursor:pointer; }
  .speed button.on { background:var(--accent2); color:#1a1d27; border-color:var(--accent2); font-weight:700; }
  .ladtabs { display:inline-flex; gap:4px; }
  .ladtabs button { background:var(--surface2); border:1px solid var(--border); color:var(--muted); font-size:0.7rem; padding:2px 9px; border-radius:6px; cursor:pointer; font-weight:600; }
  .ladtabs button.on { background:var(--accent2); color:#1a1d27; border-color:var(--accent2); font-weight:700; }
  .lb-sub { font-size:0.68rem; color:var(--muted); margin:-0.3rem 0 0.7rem; }

  /* ---------------- leaderboard ---------------- */
  .lb-row { display:flex; align-items:center; gap:0.6rem; padding:0.55rem 0; border-bottom:1px solid var(--border); }
  .lb-row:last-child{ border-bottom:none; }
  .lb-row.disabled { opacity:0.5; }
  .lb-row.disabled .lb-name, .lb-row.disabled .lb-blurb { text-decoration:line-through; }
  .lb-crashed { display:inline-block; margin-left:0.35rem; padding:0 0.3rem; border-radius:4px;
    background:#7f1d1d; color:#fecaca; font-size:0.6rem; font-weight:700; vertical-align:middle;
    text-decoration:none; letter-spacing:0.03em; }
  .lb-rank { font-size:0.8rem; color:var(--muted); width:18px; text-align:center; font-weight:700;}
  .lb-av { font-size:1.4rem; }
  .lb-main { flex:1; min-width:0; }
  .lb-name { font-weight:600; font-size:0.86rem; display:flex; align-items:center; gap:6px; }
  .lb-blurb{ font-size:0.66rem; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; cursor:default; position:relative; }
  .lb-blurb:hover{ white-space:normal; overflow:visible; background:var(--surface); border-radius:4px; padding:2px 5px; margin:-2px -5px; z-index:10; box-shadow:0 2px 8px rgba(0,0,0,0.4); }
  .lb-author{ color:#64748b; font-style:italic; }
  .lb-bar { height:7px; background:var(--surface2); border-radius:4px; overflow:hidden; margin-top:4px; }
  .lb-bar i { display:block; height:100%; border-radius:4px; transition: width .6s; }
  .lb-right { text-align:right; }
  /* pairwise matrix */
  .pw-table { border-collapse:collapse; font-size:0.6rem; width:100%; }
  .pw-table th { font-size:0.58rem; color:var(--muted); padding:2px 3px; text-align:center; font-weight:500; white-space:nowrap; }
  .pw-table td { padding:2px 3px; text-align:center; border-radius:3px; font-variant-numeric:tabular-nums; font-size:0.62rem; cursor:default; }
  .pw-table .pw-label { text-align:right; color:var(--muted); padding-right:5px; white-space:nowrap; font-size:0.58rem; }
  .pw-diag { background:var(--surface2); color:var(--muted); }
  .pw-empty { color:var(--muted); }
  /* history charts */
  .hist-legend{display:flex;flex-wrap:wrap;gap:3px 10px;margin-bottom:6px}
  .hist-leg-item{display:flex;align-items:center;gap:4px;font-size:0.62rem;color:var(--muted);cursor:pointer;user-select:none;padding:2px 4px;border-radius:3px;border:1px solid transparent}
  .hist-leg-item:hover{border-color:var(--border)}
  .hist-leg-item.off{opacity:0.3}
  .hist-leg-dot{width:8px;height:8px;border-radius:2px;flex-shrink:0}
  .hist-ctrl{font-size:0.68rem;padding:3px 8px;border-radius:5px;border:1px solid var(--border);background:transparent;color:var(--muted);cursor:pointer}
  .hist-ctrl.on{background:var(--surface2);color:var(--text);border-color:#475569}
  .lb-rate { font-weight:700; font-size:0.95rem; font-variant-numeric:tabular-nums; }
  .lb-games{ font-size:0.64rem; color:var(--muted); text-align:right; margin-top:2px; }
  .lb-elo { font-weight:800; font-size:1.25rem; font-variant-numeric:tabular-nums; line-height:1.15; }
  .lb-wr { font-weight:700; font-size:1.0rem; color:#cbd5e1; font-variant-numeric:tabular-nums; line-height:1.2; margin-top:1px; }
  .lb-unit{ font-size:0.56rem; color:var(--muted); font-weight:700; letter-spacing:0.05em; margin-left:3px; }
  .lb-prov{ font-size:0.6rem; color:var(--yellow); border:1px solid var(--yellow); border-radius:3px; padding:0 3px; margin-left:3px; vertical-align:middle; font-weight:700;}
  .elo-spark { width:84px; height:20px; margin-top:5px; display:block; opacity:0.85; }
  .elo-spark-empty { height:25px; }
  .streak { font-size:0.64rem; color:var(--yellow); }
  .spark { display:flex; gap:2px; margin-top:4px; }
  .spark i { width:5px; height:5px; border-radius:1px; background:#333a52; }
  .spark i.w { background: var(--green); }

  /* ---------------- stats row ---------------- */
  .row2 { display:grid; grid-template-columns: 1fr 1fr; gap:1rem; margin-top:1rem; }
  @media (max-width:900px){ .row2{ grid-template-columns:1fr; } }
  .tiles { display:grid; grid-template-columns: repeat(5,1fr); gap:0.5rem; }
  @media (max-width:560px){ .tiles{ grid-template-columns:repeat(3,1fr);} }
  .tile { background:var(--surface2); border:1px solid var(--border); border-radius:10px; padding:0.6rem 0.4rem; text-align:center;}
  .tile .e { font-size:1.2rem; }
  .tile .v { font-weight:700; font-size:1.05rem; font-variant-numeric:tabular-nums; }
  .tile .l { font-size:0.6rem; color:var(--muted); text-transform:uppercase; letter-spacing:.04em;}
  .records { font-size:0.82rem; }
  .records div { padding:0.35rem 0; border-bottom:1px solid var(--border); display:flex; justify-content:space-between; gap:0.5rem;}
  .records div:last-child{border-bottom:none;}
  .records .k { color:var(--muted); }
  .records .v { color:var(--text); text-align:right; }

  .feed { margin-top:1rem; }
  .feed-row { display:flex; align-items:center; gap:0.6rem; padding:0.4rem 0; border-bottom:1px solid var(--border); font-size:0.82rem;}
  .feed-row:last-child{border-bottom:none;}
  .feed-row .w { font-weight:600; }
  .feed-row .meta { margin-left:auto; color:var(--muted); font-size:0.74rem; }

@keyframes pulse { 0%,100%{opacity:1;} 50%{opacity:0.35;} }
  @keyframes slideIn { from{opacity:0; transform:translateX(-6px);} to{opacity:1; transform:none;} }
  @keyframes shake { 0%,100%{transform:none;} 20%{transform:translateX(-7px) rotate(-4deg);} 40%{transform:translateX(7px) rotate(4deg);} 60%{transform:translateX(-5px);} 80%{transform:translateX(5px);} }
  @keyframes flashRed { 0%{background:#3a1d22;} 100%{background:var(--surface2);} }
  @keyframes flashGreen { 0%{background:#16321f;} 100%{background:var(--surface2);} }
  @keyframes popUp { 0%{opacity:0; transform:translateY(4px) scale(.6);} 30%{opacity:1; transform:translateY(-6px) scale(1.1);} 100%{opacity:0; transform:translateY(-22px) scale(1);} }
  .footer{ text-align:center; color:var(--muted); font-size:0.74rem; margin-top:2rem;}
/* ---- DEPLOY NOTIFICATION ---- */
#deploy-banner{
  position:fixed;top:0;left:0;right:0;z-index:9999;
  background:linear-gradient(90deg,#7f1d1d,#991b1b);
  border-bottom:2px solid #ef4444;
  color:#fef2f2;padding:.75rem 1.2rem;
  display:flex;align-items:center;justify-content:space-between;gap:1rem;
  font-size:.9rem;font-weight:600;
  box-shadow:0 4px 24px rgba(239,68,68,.4);
  animation:deploySlideIn .35s cubic-bezier(.17,.67,.36,1.2) forwards;
}
@keyframes deploySlideIn{from{transform:translateY(-100%);}to{transform:translateY(0);}}
#deploy-banner .db-msg{display:flex;align-items:center;gap:.6rem;}
#deploy-banner .db-icon{font-size:1.3rem;animation:deploySpinIcon 2s linear infinite;}
@keyframes deploySpinIcon{to{transform:rotate(360deg);}}
#deploy-banner button{
  background:#ef4444;color:#fff;border:none;border-radius:8px;
  padding:.45rem 1rem;font-size:.85rem;font-weight:700;cursor:pointer;
  white-space:nowrap;transition:background .15s;flex-shrink:0;
}
#deploy-banner button:hover{background:#dc2626;}
</style>
</head>
<body>
<div class="page">
  <header>
    <div>
      <h1><span class="spark">🐱</span> Exploding Kittens — Live Arena</h1>
      <p>Bots battling it out — ranked by win rate &amp; average placement. Top performers plus a challenger every game. The simulation never sleeps.</p>
      <div class="toplinks">🎮 <a href="/play">Play vs the bots</a> &nbsp;·&nbsp; 📈 <a href="/history">Win rate history</a> &nbsp;·&nbsp; 📖 <a id="protolink" href="#">Agent protocol docs</a></div>
    </div>
    <div class="build" id="build" title="which code is deployed, and who shipped it"></div>
  </header>

  <div class="counters">
    <div class="counter"><div class="val live" id="c-games">—</div><div class="lab">Games played</div></div>
    <div class="counter"><div class="val" id="c-gps">—</div><div class="lab">Games / sec</div></div>
    <div class="counter"><div class="val" id="c-turns">—</div><div class="lab">Avg turns / game</div></div>
    <div class="counter"><div class="val" id="c-boom">—</div><div class="lab">💥 Explosions</div></div>
    <div class="counter"><div class="val" id="c-up">—</div><div class="lab">Uptime</div></div>
  </div>

  <div class="grid">
    <!-- LIVE TABLE -->
    <div class="card table-wrap">
      <h2>Live Table
        <span class="speed">
          <button data-s="1.6" id="sp0">0.5×</button>
          <button data-s="1" class="on" id="sp1">1×</button>
          <button data-s="0.5" id="sp2">2×</button>
          <button data-s="0.22" id="sp3">4×</button>
        </span>
      </h2>
      <div class="stage" id="stage">
        <div class="turn-tag" id="turntag"></div>
        <div class="deck-tag" id="decktag"></div>
        <div class="big" id="stage-big">🂠</div>
        <div class="msg" id="stage-msg">Dealing the next game…</div>
      </div>
      <div class="players" id="players"></div>
      <div class="ticker" id="ticker"></div>
    </div>

    <!-- LEADERBOARD -->
    <div class="card">
      <h2>Ladders
        <span class="ladtabs">
          <button data-m="win" class="on">Win %</button>
          <button data-m="place">Avg Place</button>
          <button data-m="elo">ELO</button>
        </span>
      </h2>
      <div class="lb-sub" id="lb-sub"></div>
      <div id="leaderboard"></div>
    </div>
  </div>

  <div class="row2">
    <div class="card">
      <h2>Mayhem Meter</h2>
      <div class="tiles" id="tiles"></div>
      <h2 style="margin-top:1.1rem">Hall of Records</h2>
      <div class="records" id="records"></div>
    </div>
    <div class="card feed">
      <h2>Recent Results</h2>
      <div id="feed"></div>
    </div>
  </div>

  <div style="margin-top:1rem;display:grid;grid-template-columns:2fr 1fr;gap:1rem;align-items:start;">
    <div class="card">
      <h2>💀 Biggest Loser Arena
        <span class="ladtabs" id="loser-tabs">
          <button data-lm="no_win" class="on">No-Win %</button>
          <button data-lm="first_out">First Out %</button>
          <button data-lm="elo">ELO</button>
        </span>
      </h2>
      <div class="lb-sub" id="loser-lb-sub"></div>
      <div id="loser-leaderboard"><div class="lb-blurb">Loading…</div></div>
    </div>
    <div class="card">
      <h2>How it works</h2>
      <div style="font-size:0.82rem;color:var(--muted);line-height:1.9;">
        <p>The goal is to <b style="color:var(--text)">lose</b> — bots are ranked by how consistently they avoid winning.</p>
        <p style="margin-top:0.5rem"><b style="color:var(--text)">No-Win %</b> — fraction of games where this bot was not the last survivor. The primary metric.</p>
        <p style="margin-top:0.5rem"><b style="color:var(--text)">First Out %</b> — fraction of games where this bot exploded first. A secondary signal.</p>
        <p style="margin-top:0.5rem"><b style="color:var(--text)">ELO</b> — rated skill at losing; finish order is inverted vs the main arena.</p>
        <p style="margin-top:0.5rem;font-size:0.7rem">Lineup: top 4 biggest losers + 1 random challenger each game.</p>
      </div>
    </div>
  </div>

  <div style="margin-top:1rem;display:grid;grid-template-columns:1fr 1fr;gap:1rem;align-items:start;">
    <div class="card">
      <h2>🏆 Winner Head-to-Head</h2>
      <div class="lb-sub">Row bot's win rate when sharing a game with col bot</div>
      <div id="pw-winner" style="overflow-x:auto"><div class="lb-blurb">Loading…</div></div>
    </div>
    <div class="card">
      <h2>💀 Loser Head-to-Head</h2>
      <div class="lb-sub">Row bot's loser-win rate (died earlier) vs col bot</div>
      <div id="pw-loser" style="overflow-x:auto"><div class="lb-blurb">Loading…</div></div>
    </div>
  </div>

<div style="margin-top:1rem">
  <div class="card">
    <h2>📈 Win Rate History
      <span style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
        <button class="hist-ctrl on" id="hist-btn-wr" onclick="setHistMetric('wr')">Win %</button>
        <button class="hist-ctrl" id="hist-btn-nwr" onclick="setHistMetric('nwr')">No-Win %</button>
        <button class="hist-ctrl" id="hist-btn-elo" onclick="setHistMetric('elo')">ELO</button>
        <button class="hist-ctrl" style="margin-left:4px" onclick="resetHistZoom()">Reset zoom</button>
      </span>
    </h2>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.2rem;align-items:start">
      <div>
        <div style="font-size:0.63rem;color:var(--muted);margin-bottom:5px;font-weight:600;letter-spacing:.06em;text-transform:uppercase">🏆 Winner Arena</div>
        <div class="hist-legend" id="hist-leg-win"></div>
        <div style="position:relative;height:240px"><canvas id="hist-chart-win" role="img" aria-label="Winner win rate history"></canvas></div>
      </div>
      <div>
        <div style="font-size:0.63rem;color:var(--muted);margin-bottom:5px;font-weight:600;letter-spacing:.06em;text-transform:uppercase">💀 Loser Arena</div>
        <div class="hist-legend" id="hist-leg-lose"></div>
        <div style="position:relative;height:240px"><canvas id="hist-chart-lose" role="img" aria-label="Loser no-win rate history"></canvas></div>
      </div>
    </div>
    <div style="font-size:0.62rem;color:#475569;margin-top:6px">Scroll to zoom · drag to pan &nbsp;·&nbsp; click legend to toggle bots &nbsp;·&nbsp; <a href="/history" style="color:#475569">open full-screen →</a></div>
    <div style="font-size:0.62rem;color:#475569;margin-top:2px" id="hist-status"></div>
  </div>
</div>

<div class="footer">Continuously simulated · stats persist across restarts · logs auto-pruned</div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script src="https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>
<script>if(typeof ChartZoom!=='undefined') Chart.register(ChartZoom);</script>
<script>
const CARD_EMOJI = {
  EXPLODING_KITTEN:"💣", DEFUSE:"🛡️", ATTACK:"⚔️", SKIP:"⏭️", FAVOR:"🙏",
  SHUFFLE:"🔀", SEE_THE_FUTURE:"🔮", NOPE:"⛔",
  TACO_CAT:"🌮", HAIRY_POTATO_CAT:"🥔", BEARD_CAT:"🧔", RAINBOW_CAT:"🌈", CATTERMELON:"🍉"
};
const TILE_DEFS = [
  ["explosions","💥","Booms"],["defuses","🛡️","Defuses"],["nopes","⛔","Nopes"],
  ["cat_steals","🐱","Cat steals"],["attacks","⚔️","Attacks"],["skips","⏭️","Skips"],
  ["favors","🙏","Favors"],["shuffles","🔀","Shuffles"],["see_futures","🔮","Peeks"],["draws","🃏","Draws"]
];
const $ = id => document.getElementById(id);
document.getElementById('protolink').href = `http://${location.hostname}:8766`;

function fmtUptime(s){
  const h=Math.floor(s/3600), m=Math.floor(s%3600/60);
  if(h>0) return `${h}h ${m}m`;
  return `${m}m ${s%60}s`;
}
function eloSpark(vals, color){
  if(!vals || vals.length<2) return '<div class="elo-spark-empty"></div>';
  const w=84, h=20, min=Math.min(...vals), max=Math.max(...vals), span=(max-min)||1;
  const pts = vals.map((v,i)=>`${(i/(vals.length-1)*w).toFixed(1)},${(h-2-((v-min)/span)*(h-4)).toFixed(1)}`).join(' ');
  return `<svg class="elo-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>`;
}

/* ---------------- ladders (ELO / Win% / Avg Place) ---------------- */
let LAST_STATS = null;
let LADDER = 'win';
const LAD_DESC = {
  win: 'win rate · share of games finished 1st',
  place: 'average finishing place · lower is better, the steadiest signal',
  elo: 'rated ELO · noisy in a high-luck game, shown for reference',
};
document.querySelectorAll('.ladtabs button').forEach(btn=>{
  btn.onclick = ()=>{
    document.querySelectorAll('.ladtabs button').forEach(b=>b.classList.remove('on'));
    btn.classList.add('on'); LADDER = btn.dataset.m; renderLadder();
  };
});
function renderLadder(){
  if(!LAST_STATS) return;
  const m = LADDER, rows = [...LAST_STATS.leaderboard];
  const place = b => (b.avg_place==null ? 99 : b.avg_place);
  if(m==='elo') rows.sort((a,b)=>b.elo-a.elo);
  else if(m==='win') rows.sort((a,b)=>b.win_rate-a.win_rate);
  else rows.sort((a,b)=>place(a)-place(b));
  $('lb-sub').textContent = LAD_DESC[m];

  // bar scale for the active metric
  const elos=rows.map(x=>x.elo), wins=rows.map(x=>x.win_rate), places=rows.map(place);
  const emin=Math.min(...elos), espan=(Math.max(...elos)-emin)||1;
  const wmax=Math.max(0.001,...wins);
  const pmin=Math.min(...places), pmax=Math.max(...places), pspan=(pmax-pmin)||1;
  const barOf = b => m==='elo' ? 8+(b.elo-emin)/espan*92
                   : m==='win' ? 8+(b.win_rate/wmax)*92
                   : 8+(pmax-place(b))/pspan*92;   // lower place -> fuller bar

  const big = b => {
    const prov = b.provisional ? `<span class="lb-prov" title="provisional (<10 rated games)">?</span>` : '';
    const er=b.elo_recent||[]; let trend='';
    if(er.length>=2){const d=er[er.length-1]-er[0];
      trend = d>=0?`<span style="color:var(--green)">▲${Math.round(d)}</span>`:`<span style="color:var(--red)">▼${Math.round(-d)}</span>`;}
    if(m==='elo') return `<div class="lb-elo" style="color:${b.color}">${b.elo}${prov}<span class="lb-unit">ELO ${trend}</span></div>
        <div class="lb-wr">${(b.win_rate*100).toFixed(1)}<span class="lb-unit">% WIN · ${b.avg_place??'–'} PLACE</span></div>`;
    if(m==='win') return `<div class="lb-elo" style="color:${b.color}">${(b.win_rate*100).toFixed(1)}<span class="lb-unit">% WIN</span></div>
        <div class="lb-wr">${b.elo}<span class="lb-unit">ELO · ${b.avg_place??'–'} PLACE</span></div>`;
    return `<div class="lb-elo" style="color:${b.color}">${b.avg_place??'–'}<span class="lb-unit">AVG PLACE</span></div>
        <div class="lb-wr">${b.elo}<span class="lb-unit">ELO · ${(b.win_rate*100).toFixed(1)}% WIN</span></div>`;
  };
  $('leaderboard').innerHTML = rows.map((b,i)=>{
    const streak = b.streak>=2 ? `<span class="streak">🔥${b.streak}</span>` : '';
    const gamesLabel = b.games >= 1000 ? `${(b.games/1000).toFixed(1)}k` : `${b.games}`;
    const crashed = b.disabled ? `<span class="lb-crashed" title="${(b.disabled_reason||'crashed during a game').replace(/"/g,"'")}">CRASHED</span>` : '';
    return `<div class="lb-row${b.disabled?' disabled':''}">
      <div class="lb-rank">${i+1}</div>
      <div class="lb-av">${b.emoji}</div>
      <div class="lb-main">
        <div class="lb-name" style="color:${b.color}">${b.name} ${streak}${crashed}</div>
        <div class="lb-blurb" title="${b.blurb}">${b.blurb} <span class="lb-author">· by ${b.author||'—'}</span></div>
        <div class="lb-bar"><i style="width:${barOf(b).toFixed(1)}%;background:${b.color}"></i></div>
        ${m==='elo' ? eloSpark(b.elo_recent, b.color) : ''}
      </div>
      <div class="lb-right">${big(b)}<div class="lb-games">${gamesLabel} games</div></div>
    </div>`;
  }).join('');
}

/* ---------------- stats polling ---------------- */
async function pollStats(){
  try{
    const s = await (await fetch('/api/stats')).json();
    renderStats(s);
  }catch(e){}
  setTimeout(pollStats, 2000);
}
function renderStats(s){
  $('c-games').textContent = s.total_games.toLocaleString();
  $('c-gps').textContent = s.games_per_sec.toFixed(1);
  $('c-turns').textContent = s.avg_turns;
  $('c-boom').textContent = (s.tallies.explosions||0).toLocaleString();
  $('c-up').textContent = fmtUptime(s.uptime_secs);
  if(s.build){ const sha=s.build.sha;
    const repo='https://github.com/danielbairddev/exploding_kittens';
    const url = (sha && sha!=='dev') ? (repo+'/commit/'+sha) : repo;
    $('build').innerHTML = `⚙ <a href="${url}" target="_blank" rel="noopener">${sha}</a> · deployed by ${s.build.by}`
      + (s.build.at?(' · '+s.build.at):'') + ` &nbsp;·&nbsp; <a href="${repo}" target="_blank" rel="noopener">repo</a>`; }

  LAST_STATS = s;
  renderLadder();
  renderPairwise('pw-winner', s, false);

  // tiles
  $('tiles').innerHTML = TILE_DEFS.map(([k,e,l])=>`
    <div class="tile"><div class="e">${e}</div><div class="v">${(s.tallies[k]||0).toLocaleString()}</div><div class="l">${l}</div></div>`
  ).join('');

  // records
  const r = s.records;
  $('records').innerHTML = `
    <div><span class="k">🏆 Longest game</span><span class="v">${r.longest.turns} turns · ${r.longest.winner||'—'}</span></div>
    <div><span class="k">⚡ Fastest win</span><span class="v">${r.shortest.turns<1e8? r.shortest.turns+' turns · '+(r.shortest.winner||'—') : '—'}</span></div>
    <div><span class="k">⛔ Biggest Nope war</span><span class="v">${r.nope_war.count} nopes · ${r.nope_war.winner||'—'}</span></div>`;

  // feed
  $('feed').innerHTML = s.recent_results.map(g=>{
    const deaths = g.deaths.length? g.deaths.join(' → ') : 'flawless';
    return `<div class="feed-row">
      <span style="font-size:1.1rem">${g.winner_emoji}</span>
      <span class="w">${g.winner}</span>
      <span class="meta">💀 ${deaths} · ${g.turns} turns</span>
    </div>`;
  }).join('') || '<div class="lb-blurb">waiting for the first game…</div>';
}

/* ---------------- replay engine ---------------- */
let SPEED = 1;
document.querySelectorAll('.speed button').forEach(btn=>{
  btn.onclick = ()=>{
    document.querySelectorAll('.speed button').forEach(b=>b.classList.remove('on'));
    btn.classList.add('on'); SPEED = parseFloat(btn.dataset.s);
  };
});
const sleep = ms => new Promise(r=>setTimeout(r, ms*SPEED));

let table = null;
function renderTable(highlightWinner=-1){
  $('players').innerHTML = table.seats.map((p,seat)=>{
    const n = Math.min(p.hand, 9);
    const cards = '<i></i>'.repeat(Math.max(0,n));
    let cls = 'player';
    if(seat===table.current && p.alive) cls+=' current';
    if(!p.alive) cls+=' dead';
    if(seat===highlightWinner) cls+=' winner';
    return `<div class="${cls}" id="seat${seat}">
      <div class="av">${p.alive? p.emoji : '💀'}</div>
      <div class="nm" style="color:${p.color}">${p.name}</div>
      <div class="ty">${p.type.replace('Agent','')}</div>
      <div class="hand">${cards}</div>
      <div class="hcount">${p.hand} cards</div>
    </div>`;
  }).join('');
}
function pop(seat, emoji){
  const el = $('seat'+seat); if(!el) return;
  const s = document.createElement('div'); s.className='pop'; s.textContent=emoji;
  el.appendChild(s); setTimeout(()=>s.remove(), 900);
}
function setStage(big, msg, cls){
  $('stage-big').textContent = big;
  $('stage-msg').innerHTML = msg;
  $('turntag').textContent = table.current>=0 && table.seats[table.current] ? `${table.seats[table.current].emoji} ${table.seats[table.current].name}` : '';
  $('decktag').textContent = `🂠 deck: ${table.deck}`;
  const st = $('stage');
  if(cls){ st.classList.add(cls); setTimeout(()=>st.classList.remove(cls), 520); }
}
let tickerLines = [];
function tick(html, hot){
  tickerLines.unshift(`<div class="line${hot?' hot':''}">${html}</div>`);
  tickerLines = tickerLines.slice(0,9);
  $('ticker').innerHTML = tickerLines.join('');
}
const nm = seat => table.seats[seat] ? `<b style="color:${table.seats[seat].color}">${table.seats[seat].name}</b>` : '?';

async function playGame(game){
  table = {
    seats: game.seats.map(s=>({...s, hand:8, alive:true})),
    deck: 0, current: -1
  };
  tickerLines = [];
  // try to seed deck/hand sizes from first turn_start
  const firstTS = game.events.find(e=>e.type==='turn_start');
  if(firstTS){
    table.deck = firstTS.deck_size + 1;
    if(firstTS.hand_sizes) for(const k in firstTS.hand_sizes) if(table.seats[k]) table.seats[k].hand = firstTS.hand_sizes[k];
  }
  renderTable();
  setStage('🃏', `New game — <b>${game.seats.map(s=>s.emoji).join(' ')}</b> take their seats`);
  await sleep(900);

  for(const e of game.events){
    await applyEvent(e);
  }
}

async function applyEvent(e){
  const p = e.player;
  switch(e.type){
    case 'turn_start':
      table.current = p; table.deck = e.deck_size;
      if(e.hand_sizes) for(const k in e.hand_sizes) if(table.seats[k]) table.seats[k].hand = e.hand_sizes[k];
      renderTable();
      setStage(table.seats[p].emoji, `${nm(p)} steps up`);
      await sleep(420); break;

    case 'draw': {
      table.deck = Math.max(0, table.deck-1); table.seats[p].hand++;
      const ce = CARD_EMOJI[e.card]||'🃏';
      renderTable(); setStage(ce, `${nm(p)} draws ${ce} ${e.card.replace(/_/g,' ').toLowerCase()}`);
      tick(`${nm(p)} draws ${ce}`); await sleep(560); break;
    }
    case 'defuse':
      table.seats[p].hand = Math.max(0,table.seats[p].hand-1); table.deck = e.deck_size;
      renderTable('defuse'); pop(p,'🛡️');
      setStage('🛡️', `${nm(p)} <b style="color:var(--green)">DEFUSES</b> the kitten!`, 'flash-green');
      tick(`${nm(p)} defuses the kitten 🛡️`, true); await sleep(1050); break;

    case 'explode':
      table.seats[p].alive = false; table.seats[p].hand = 0; if(table.current===p) table.current=-1;
      renderTable(); pop(p,'💥');
      setStage('💥', `${nm(p)} <b style="color:var(--red)">EXPLODES!</b>`, 'shake');
      $('stage').classList.add('flash-red'); setTimeout(()=>$('stage').classList.remove('flash-red'),520);
      tick(`💥 ${nm(p)} explodes!`, true); await sleep(1500); break;

    case 'nope': {
      const restored = e.result==='restored';
      table.seats[p].hand = Math.max(0,table.seats[p].hand-1); renderTable(); pop(p,'⛔');
      setStage('⛔', restored? `${nm(p)} <b>YES!</b> (counter-nope)` : `${nm(p)} plays <b>NOPE</b>`);
      tick(`${nm(p)} ${restored?'counter-nopes ✅':'NOPEs ⛔'}`); await sleep(500); break;
    }
    case 'attack':
      table.seats[p].hand = Math.max(0,table.seats[p].hand-1); renderTable(); pop(e.target,'⚔️');
      setStage('⚔️', `${nm(p)} <b style="color:var(--accent)">ATTACKS</b> ${nm(e.target)}!`);
      tick(`${nm(p)} attacks ${nm(e.target)} ⚔️`, true); await sleep(640); break;

    case 'skip':
      table.seats[p].hand = Math.max(0,table.seats[p].hand-1); renderTable();
      setStage('⏭️', `${nm(p)} skips the draw`); tick(`${nm(p)} skips ⏭️`); await sleep(420); break;

    case 'shuffle':
      table.seats[p].hand = Math.max(0,table.seats[p].hand-1); renderTable();
      setStage('🔀', `${nm(p)} shuffles the deck`); tick(`${nm(p)} shuffles 🔀`); await sleep(500); break;

    case 'see_future':
      table.seats[p].hand = Math.max(0,table.seats[p].hand-1); renderTable();
      setStage('🔮', `${nm(p)} peeks at the future`); tick(`${nm(p)} sees the future 🔮`); await sleep(520); break;

    case 'favor':
      if(table.seats[e.from_player]) table.seats[e.from_player].hand = Math.max(0,table.seats[e.from_player].hand-1);
      table.seats[p].hand++; renderTable(); pop(e.from_player,'🙏');
      setStage('🙏', `${nm(p)} demands a favor from ${nm(e.from_player)}`);
      tick(`${nm(p)} takes a favor from ${nm(e.from_player)} 🙏`); await sleep(680); break;

    case 'cat_steal': {
      if(table.seats[e.from_player]) table.seats[e.from_player].hand = Math.max(0,table.seats[e.from_player].hand-1);
      table.seats[p].hand++; renderTable(); pop(e.from_player,'🐱');
      const how = e.method==='triple'? 'demands a card from' : 'swipes from';
      setStage('🐱', `${nm(p)} ${how} ${nm(e.from_player)}`);
      tick(`${nm(p)} ${how} ${nm(e.from_player)} 🐱`, true); await sleep(700); break;
    }
    case 'game_over': {
      table.current = -1; renderTable(e.winner);
      const w = table.seats[e.winner];
      if(w){ pop(e.winner,'👑'); setStage('👑', `<b style="color:var(--yellow)">${w.name} wins!</b> Last cat standing.`, 'flash-green'); }
      tick(`👑 ${w? '<b>'+w.name+'</b> takes the game!' : 'game over'}`, true);
      await sleep(2600); break;
    }
    default: break;
  }
}

async function replayLoop(){
  while(true){
    let game = null;
    try{ game = await (await fetch('/api/showcase')).json(); }catch(e){}
    if(!game){ await new Promise(r=>setTimeout(r,1500)); continue; }
    await playGame(game);
    await new Promise(r=>setTimeout(r,400));
  }
}

/* ---------------- biggest loser arena ---------------- */
let LAST_LOSER = null;
let LOSER_MODE = 'no_win';
const LOSER_DESC = {
  no_win:    'no-win rate · fraction of games where this bot was not the last survivor — the primary losing metric',
  first_out: 'first out rate · fraction of games where this bot exploded first — a secondary signal',
  elo:       'rated ELO · skill at losing; finish order is inverted vs the main arena',
};
document.querySelectorAll('#loser-tabs button').forEach(btn=>{
  btn.onclick = ()=>{
    document.querySelectorAll('#loser-tabs button').forEach(b=>b.classList.remove('on'));
    btn.classList.add('on'); LOSER_MODE = btn.dataset.lm; renderLoserLadder();
  };
});
function renderLoserLadder(){
  if(!LAST_LOSER) return;
  const m = LOSER_MODE, rows = [...LAST_LOSER.leaderboard];
  if(m==='elo')        rows.sort((a,b)=>b.elo-a.elo);
  else if(m==='no_win') rows.sort((a,b)=>b.no_win_rate-a.no_win_rate);
  else                  rows.sort((a,b)=>b.win_rate-a.win_rate);
  $('loser-lb-sub').textContent = LOSER_DESC[m];

  const vals = rows.map(x=> m==='elo'?x.elo : m==='no_win'?x.no_win_rate : x.win_rate);
  const vmin=Math.min(...vals), vmax=Math.max(...vals), vspan=(vmax-vmin)||1;
  const barOf = b => {
    const v = m==='elo'?b.elo : m==='no_win'?b.no_win_rate : b.win_rate;
    return m==='elo' ? 8+(v-vmin)/vspan*92 : 8+(v/Math.max(0.001,vmax))*92;
  };
  const big = b => {
    const prov = b.provisional ? `<span class="lb-prov" title="provisional (<10 games)">?</span>` : '';
    if(m==='elo') return `<div class="lb-elo" style="color:${b.color}">${b.elo}${prov}<span class="lb-unit">ELO</span></div>
      <div class="lb-wr">${(b.no_win_rate*100).toFixed(1)}<span class="lb-unit">% NO-WIN · ${(b.win_rate*100).toFixed(1)}% FIRST OUT</span></div>`;
    if(m==='no_win') return `<div class="lb-elo" style="color:${b.color}">${(b.no_win_rate*100).toFixed(1)}<span class="lb-unit">% NO-WIN</span></div>
      <div class="lb-wr">${b.elo}<span class="lb-unit">ELO · ${(b.win_rate*100).toFixed(1)}% FIRST OUT</span></div>`;
    return `<div class="lb-elo" style="color:${b.color}">${(b.win_rate*100).toFixed(1)}<span class="lb-unit">% FIRST OUT</span></div>
      <div class="lb-wr">${b.elo}<span class="lb-unit">ELO · ${(b.no_win_rate*100).toFixed(1)}% NO-WIN</span></div>`;
  };
  $('loser-leaderboard').innerHTML = rows.map((b,i)=>{
    const streak = b.streak>=2 ? `<span class="streak">💀${b.streak}</span>` : '';
    const gl = b.games >= 1000 ? `${(b.games/1000).toFixed(1)}k` : `${b.games}`;
    const crashed = b.disabled ? `<span class="lb-crashed" title="${(b.disabled_reason||'crashed during a game').replace(/"/g,"'")}">CRASHED</span>` : '';
    return `<div class="lb-row${b.disabled?' disabled':''}">
      <div class="lb-rank">${i+1}</div>
      <div class="lb-av">${b.emoji}</div>
      <div class="lb-main">
        <div class="lb-name" style="color:${b.color}">${b.name} ${streak}${crashed}</div>
        <div class="lb-blurb" title="${b.blurb}">${b.blurb}</div>
        <div class="lb-bar"><i style="width:${barOf(b).toFixed(1)}%;background:${b.color}"></i></div>
      </div>
      <div class="lb-right">${big(b)}<div class="lb-games">${gl} games</div></div>
    </div>`;
  }).join('');
}
async function pollLoser(){
  try{
    const s = await (await fetch('/api/loser_stats')).json();
    LAST_LOSER = s; renderLoserLadder(); renderPairwise('pw-loser', s, true);
  }catch(e){}
  setTimeout(pollLoser, 3000);
}
pollLoser();

/* -------------- pairwise head-to-head matrix -------------- */
function renderPairwise(divId, stats, loserMode){
  if(!stats || !stats.pairwise || !stats.leaderboard) return;
  // Build lookup: "minid:maxid" -> {a_wins, b_wins, shared}
  const pw = {};
  for(const e of stats.pairwise) pw[e.a+':'+e.b] = e;

  // Sort by primary metric: win_rate for winner arena, no_win_rate for loser arena.
  const bots = [...stats.leaderboard].sort((a,b)=>
    loserMode ? (b.no_win_rate-a.no_win_rate) : (b.win_rate-a.win_rate));
  const ids = bots.map(b=>b.bot_id);
  const byId = {};
  for(const b of bots) byId[b.bot_id]=b;

  function winRate(rowId, colId){
    if(rowId===colId) return null;
    const lo=Math.min(rowId,colId), hi=Math.max(rowId,colId);
    const e = pw[lo+':'+hi];
    if(!e || e.shared===0) return null;
    const rowWins = rowId===lo ? e.a_wins : e.b_wins;
    return {rate: rowWins/e.shared, shared: e.shared};
  }

  function cellColor(rate){
    // green >50%, red <50%, neutral at 50%
    if(rate>0.5){
      const t=(rate-0.5)*2;
      return `rgba(34,197,94,${(0.15+t*0.55).toFixed(2)})`;
    } else {
      const t=(0.5-rate)*2;
      return `rgba(239,68,68,${(0.15+t*0.55).toFixed(2)})`;
    }
  }

  let html='<table class="pw-table"><thead><tr><th></th>';
  for(const id of ids) html+=`<th title="${byId[id].name}">${byId[id].emoji}</th>`;
  html+='</tr></thead><tbody>';
  for(const rowId of ids){
    const rb=byId[rowId];
    html+=`<tr><td class="pw-label" title="${rb.name}">${rb.emoji} ${rb.name.split(' ')[0]}</td>`;
    for(const colId of ids){
      if(rowId===colId){html+='<td class="pw-diag">—</td>'; continue;}
      const r=winRate(rowId,colId);
      if(!r){html+='<td class="pw-empty">·</td>'; continue;}
      const pct=(r.rate*100).toFixed(0);
      const bg=cellColor(r.rate);
      html+=`<td style="background:${bg}" title="${rb.name} vs ${byId[colId].name}: ${pct}% (${r.shared} games)">${pct}%</td>`;
    }
    html+='</tr>';
  }
  html+='</tbody></table>';
  $(divId).innerHTML=html;
}

/* -------- history charts -------- */
const HIST_BOT_COLORS = {
  'Professor':'#818cf8','Maverick':'#f97316','Gremlin':'#4ade80',
  'Sly':'#22d3ee','Lucky':'#a78bfa','Sly2':'#38bdf8','Coyote':'#fb923c',
  'Orangutan':'#f59e0b','Ian1':'#e879f9','Ian2':'#34d399',
  'Ian The Bomb':'#f43f5e','Perdition 2':'#ef4444',
  'Rhino':'#60a5fa','Elephant':'#a3e635',
  'Gabriel':'#d4af37','Orpheus':'#c084fc','Cassandra':'#fb7185',
  'Hades':'#94a3b8','Abaddon':'#f472b6',
};
let histMetric = 'wr';
let histChartWin = null, histChartLose = null;
let histHiddenWin = new Set(), histHiddenLose = new Set();
let histDataWin = null, histDataLose = null;

function histNorm(n){ return n==='Perdition2'||n==='Perdition 2.1'?'Perdition 2':n; }

async function parseTsvHist(url, field){
  // field 3 = the main rate, field 4 = elo (same format for both files)
  const res = await fetch(url);
  const text = await res.text();
  const lines = text.trim().split('\n').slice(1);
  const rows = [];
  for(let i=0;i<lines.length;i+=3){
    const parts = lines[i].split('\t');
    if(parts.length<3) continue;
    const ts = parts[0].replace('T',' ').replace('Z','').slice(5,16);
    const bots={};
    for(const b of parts[2].split('|')){
      const p=b.split(':'); if(p.length<4) continue;
      bots[histNorm(p[0])]={rate:parseFloat(p[3])*100, elo:parseFloat(p[4]||1200)};
    }
    rows.push({ts,bots});
  }
  const allNames=new Set();
  for(const r of rows) for(const n of Object.keys(r.bots)) allNames.add(n);
  const datasets=[];
  for(const name of [...allNames].sort()){
    const color=HIST_BOT_COLORS[name]||'#888';
    datasets.push({
      label:name, color,
      rate: rows.map(r=>r.bots[name]?Math.round(r.bots[name].rate*100)/100:null),
      elo:  rows.map(r=>r.bots[name]?Math.round(r.bots[name].elo):null),
    });
  }
  return {labels:rows.map(r=>r.ts), datasets};
}

function buildHistChartInst(canvasId, data, hidden, isLoser){
  const isElo = histMetric==='elo';
  const isNwr = histMetric==='nwr';
  const ds = data.datasets.filter(d=>!hidden.has(d.label)).map(d=>({
    label:d.label, data:isElo?d.elo:d.rate,
    borderColor:d.color, backgroundColor:'transparent',
    borderWidth:1.5, pointRadius:0, spanGaps:true, tension:0.2,
  }));
  return new Chart(document.getElementById(canvasId),{
    type:'line',
    data:{labels:data.labels,datasets:ds},
    options:{
      responsive:true, maintainAspectRatio:false, animation:false,
      interaction:{mode:'index',intersect:false},
      plugins:{
        legend:{display:false},
        tooltip:{
          backgroundColor:'#1e293b',borderColor:'#334155',borderWidth:1,
          titleColor:'#94a3b8',bodyColor:'#e2e8f0',
          callbacks:{label:ctx=>`${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(isElo?0:1)??'—'}${isElo?'':'%'}`}
        },
        zoom:{pan:{enabled:true,mode:'x'},zoom:{wheel:{enabled:true},pinch:{enabled:true},mode:'x'}},
      },
      scales:{
        x:{ticks:{color:'#475569',maxTicksLimit:10,font:{size:10}},grid:{color:'rgba(255,255,255,0.04)'}},
        y:{ticks:{color:'#475569',font:{size:10},callback:v=>isElo?v:v+'%'},grid:{color:'rgba(255,255,255,0.04)'}},
      }
    }
  });
}

function buildHistLegend(legId, data, hidden){
  const el=document.getElementById(legId); if(!el) return;
  el.innerHTML=data.datasets.map(d=>`
    <div class="hist-leg-item${hidden.has(d.label)?' off':''}" id="hleg-${CSS.escape(legId+'-'+d.label)}"
         onclick="toggleHistBot('${legId}','${d.label.replace(/\\/g,'\\\\').replace(/'/g,"\\'")}')">
      <span class="hist-leg-dot" style="background:${d.color}"></span><span>${d.label}</span>
    </div>`).join('');
}

function toggleHistBot(legId, name){
  const isWin=legId.includes('-win');
  const hidden=isWin?histHiddenWin:histHiddenLose;
  if(hidden.has(name)) hidden.delete(name); else hidden.add(name);
  const item=document.getElementById('hleg-'+CSS.escape(legId+'-'+name));
  if(item) item.classList.toggle('off',hidden.has(name));
  rebuildHistChart(isWin?'win':'lose');
}

function rebuildHistChart(which){
  if(which==='win'&&histDataWin){
    if(histChartWin) histChartWin.destroy();
    histChartWin=buildHistChartInst('hist-chart-win',histDataWin,histHiddenWin,false);
  }
  if(which==='lose'&&histDataLose){
    if(histChartLose) histChartLose.destroy();
    histChartLose=buildHistChartInst('hist-chart-lose',histDataLose,histHiddenLose,true);
  }
}

function setHistMetric(m){
  histMetric=m;
  ['wr','nwr','elo'].forEach(k=>document.getElementById('hist-btn-'+k)?.classList.toggle('on',m===k));
  rebuildHistChart('win'); rebuildHistChart('lose');
}

function resetHistZoom(){ histChartWin?.resetZoom(); histChartLose?.resetZoom(); }

async function loadHistCharts(){
  try{
    const [win, lose] = await Promise.all([
      parseTsvHist('/api/winrate_history'),
      parseTsvHist('/api/loser_winrate_history'),
    ]);
    histDataWin=win; histDataLose=lose;
    buildHistLegend('hist-leg-win',win,histHiddenWin);
    buildHistLegend('hist-leg-lose',lose,histHiddenLose);
    if(histChartWin) histChartWin.destroy();
    if(histChartLose) histChartLose.destroy();
    histChartWin=buildHistChartInst('hist-chart-win',win,histHiddenWin,false);
    histChartLose=buildHistChartInst('hist-chart-lose',lose,histHiddenLose,true);
    const el=$('hist-status');
    if(el) el.textContent=`${win.labels.length} win snapshots · ${lose.labels.length} loser snapshots · last ${win.labels[win.labels.length-1]||''}`;
  }catch(e){
    const el=$('hist-status'); if(el) el.textContent='History not yet available — data accumulates over time';
  }
}
loadHistCharts();

pollStats();
replayLoop();

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
  setInterval(checkVersion, 30_000);
})();

</script>
</body>
</html>'''
