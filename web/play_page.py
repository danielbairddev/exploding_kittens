"""HTML for the play-vs-bots page. Served at /play by dashboard_server."""

PLAY_PAGE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Exploding Kittens — Play vs the Bots</title>
<style>
:root {
  --bg:#0f1117; --surface:#1a1d27; --surface2:#20232f; --border:#2e3146;
  --accent:#f97316; --accent2:#818cf8;
  --text:#e2e8f0; --muted:#94a3b8;
  --green:#4ade80; --red:#f87171; --yellow:#fbbf24; --pink:#f472b6;
}
*{box-sizing:border-box;margin:0;padding:0;}
html,body{height:100%;}
body{
  background: radial-gradient(1200px 600px at 50% -200px,#181b27 0%,var(--bg) 60%);
  color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size:15px;line-height:1.5;padding:0 1rem 5rem;min-height:100vh;
}
.page{max-width:960px;margin:0 auto;}
a{color:var(--accent2);text-decoration:none;}
a:hover{text-decoration:underline;}

header{padding:2rem 0 1.2rem;display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:.5rem;}
header h1{font-size:1.8rem;color:var(--accent);letter-spacing:-0.5px;}
header h1 .spark{animation:pulse 2.4s ease-in-out infinite;display:inline-block;}
.toplinks{font-size:.82rem;color:var(--muted);}

/* cards */
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1.1rem 1.2rem;margin-bottom:1rem;}
.card h2{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;color:var(--accent2);margin-bottom:.8rem;display:flex;justify-content:space-between;align-items:center;}

/* ---- BOT PICKER ---- */
.bot-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:.6rem;}
@media(max-width:560px){.bot-grid{grid-template-columns:repeat(2,1fr);}}
.botcard{
  background:var(--surface2);border:1.5px solid var(--border);border-radius:12px;
  padding:.7rem .5rem;text-align:center;position:relative;transition:border-color .15s,box-shadow .15s;
  user-select:none;
}
.botcard .e{font-size:1.8rem;line-height:1;}
.botcard .n{font-size:.78rem;font-weight:600;margin-top:.25rem;}
.botcard .blurb{font-size:.62rem;color:var(--muted);margin-top:.15rem;min-height:1.4em;}
.botcard .ctrls{display:flex;align-items:center;justify-content:center;gap:.4rem;margin-top:.5rem;}
.botcard .ctrls button{
  background:var(--border);border:none;border-radius:6px;width:26px;height:26px;
  font-size:.95rem;cursor:pointer;color:var(--text);display:flex;align-items:center;justify-content:center;
  transition:background .12s;
}
.botcard .ctrls button:hover{background:var(--accent2);}
.botcard .cnt{font-size:.85rem;font-weight:700;min-width:18px;text-align:center;color:var(--text);}
.botcard.picked{border-color:var(--accent2);box-shadow:0 0 0 1px var(--accent2);}
.botcard.gabriel{border-color:#d4af37;box-shadow:0 0 12px -2px #d4af37;}

/* lineup preview */
.lineup{display:flex;gap:.5rem;flex-wrap:wrap;margin:.8rem 0;}
.lineup-slot{
  background:var(--surface2);border:1px solid var(--border);border-radius:10px;
  padding:.4rem .7rem;font-size:.78rem;display:flex;align-items:center;gap:.3rem;
}
.lineup-slot .rm{cursor:pointer;color:var(--muted);font-size:.8rem;margin-left:.2rem;}
.lineup-slot .rm:hover{color:var(--red);}

.row{display:flex;gap:.8rem;align-items:center;flex-wrap:wrap;margin-top:.9rem;}
button.primary{background:var(--accent2);color:#1a1d27;border:none;border-radius:8px;padding:.55rem 1.3rem;font-weight:700;cursor:pointer;font-size:.92rem;transition:opacity .15s;}
button.primary:hover{opacity:.85;}
button.primary:disabled{opacity:.4;cursor:default;}
button.ghost{background:var(--surface2);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:.5rem 1rem;font-weight:600;cursor:pointer;font-size:.88rem;}
button.ghost:hover{border-color:var(--accent2);}
.muted{color:var(--muted);font-size:.82rem;}

/* ---- GAME SCREEN ---- */
/* Turn banner */
#turn-banner{
  border-radius:14px;padding:1rem 1.2rem;margin-bottom:.9rem;
  display:flex;align-items:center;gap:.8rem;
  background:var(--surface);border:1.5px solid var(--border);
  transition:border-color .3s,box-shadow .3s;
}
#turn-banner.your-turn{border-color:var(--accent);box-shadow:0 0 28px -6px var(--accent);}
#turn-banner.bot-turn{border-color:var(--border);}
#turn-banner.prompt-turn{border-color:var(--accent2);box-shadow:0 0 20px -6px var(--accent2);}
.banner-icon{font-size:2rem;line-height:1;}
.banner-text .who{font-size:1.05rem;font-weight:700;}
.banner-text .sub{font-size:.8rem;color:var(--muted);margin-top:.1rem;}
.banner-deck{margin-left:auto;text-align:right;font-size:.82rem;color:var(--muted);}
.banner-deck b{color:var(--text);font-size:.95rem;}

/* Players row */
.players{display:grid;grid-template-columns:repeat(5,1fr);gap:.45rem;margin-bottom:.9rem;}
@media(max-width:600px){.players{grid-template-columns:repeat(3,1fr);}}
.player{
  background:var(--surface2);border:1.5px solid var(--border);border-radius:12px;
  padding:.65rem .4rem;text-align:center;position:relative;transition:all .25s;
}
.player .av{font-size:1.5rem;line-height:1;}
.player .nm{font-weight:600;font-size:.75rem;margin-top:.1rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.player .hs{font-size:.66rem;color:var(--muted);margin-top:.1rem;}
.player .mini-hand{display:flex;justify-content:center;gap:2px;margin-top:.4rem;height:22px;align-items:flex-end;overflow:hidden;}
.player .mini-hand i{display:block;width:8px;height:18px;border-radius:2px;flex:none;background:linear-gradient(160deg,#3b3f57,#262a3c);border:1px solid #454a66;}
.player.current{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent),0 0 22px -6px var(--accent);transform:translateY(-3px);}
.player.current::before{content:"▶ TURN";position:absolute;top:-9px;left:50%;transform:translateX(-50%);font-size:.58rem;background:var(--accent);color:#1a1d27;padding:1px 6px;border-radius:5px;font-weight:700;letter-spacing:.05em;}
.player.dead{opacity:.35;filter:grayscale(.85);}
.player.hero{border-color:var(--accent2);}
.player.winner{border-color:var(--yellow);box-shadow:0 0 24px -4px var(--yellow);}
.player.winner::after{content:"👑";position:absolute;top:-16px;left:50%;transform:translateX(-50%);font-size:1.1rem;}
.player .pop{position:absolute;top:-6px;right:-4px;font-size:1rem;animation:popUp .9s ease-out forwards;pointer-events:none;}

/* ---- PLAYING CARDS (hand) ---- */
.hand-wrap{display:flex;flex-wrap:wrap;gap:.5rem;margin:.5rem 0 .2rem;}
.pcard{
  width:60px;height:84px;border-radius:8px;
  background:linear-gradient(145deg,#1e2235,#252839);
  border:1.5px solid var(--border);
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  position:relative;cursor:default;
  transition:transform .18s,box-shadow .18s;
  flex-shrink:0;
}
.pcard:hover{transform:translateY(-10px);box-shadow:0 12px 24px rgba(0,0,0,.5);}
.pcard .emo{font-size:1.5rem;line-height:1;}
.pcard .lbl{font-size:.46rem;color:var(--muted);margin-top:.25rem;text-align:center;line-height:1.25;padding:0 3px;}
.pcard .cnt{
  position:absolute;top:4px;right:5px;
  background:var(--accent2);color:#1a1d27;border-radius:10px;
  font-size:.58rem;font-weight:700;padding:0 4px;min-width:14px;text-align:center;
}
/* card type border tints */
.pcard[data-t="DEFUSE"]{border-color:var(--green);box-shadow:0 0 8px -2px var(--green);}
.pcard[data-t="NOPE"]{border-color:var(--red);}
.pcard[data-t="ATTACK"]{border-color:#f97316;}
.pcard[data-t="SKIP"]{border-color:#60a5fa;}
.pcard[data-t="FAVOR"]{border-color:#c084fc;}
.pcard[data-t="SHUFFLE"]{border-color:#2dd4bf;}
.pcard[data-t="SEE_THE_FUTURE"]{border-color:var(--accent2);}
.pcard[data-t="EXPLODING_KITTEN"]{border-color:var(--red);box-shadow:0 0 12px -2px #ef4444;}

/* ---- DISCARD PILE ---- */
.discard-row{display:flex;gap:.35rem;flex-wrap:wrap;margin:.4rem 0;}
.dcard{
  width:40px;height:56px;border-radius:6px;
  background:linear-gradient(145deg,#1a1d2a,#1f2233);
  border:1px solid var(--border);
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  font-size:1rem;
  flex-shrink:0;opacity:.6;
}
.dcard:first-child{opacity:1;border-color:var(--muted);}

/* ---- ACTIONS ---- */
.actions-section{margin:.5rem 0;}
.actions-section .prompt{font-size:.82rem;color:var(--muted);margin-bottom:.55rem;}
.act-grid{display:flex;flex-direction:column;gap:.4rem;}
.act-btn{
  background:var(--surface2);border:1.5px solid var(--border);border-radius:10px;
  padding:.6rem .9rem;text-align:left;cursor:pointer;color:var(--text);
  font-size:.88rem;font-weight:600;transition:border-color .15s,background .15s,transform .1s;
  display:flex;align-items:center;gap:.5rem;
}
.act-btn:hover{border-color:var(--accent2);background:#24283a;transform:translateX(2px);}
.act-btn:disabled{opacity:.4;cursor:default;transform:none;}
.act-btn.draw{border-color:#60a5fa;background:rgba(96,165,250,.07);}
.act-btn.danger{border-color:var(--red);}
.act-btn .act-emo{font-size:1.1rem;flex-shrink:0;}

/* ---- GAME LOG ---- */
.log-wrap{max-height:200px;overflow-y:auto;margin-top:.3rem;}
.log-line{font-size:.78rem;color:var(--muted);padding:2px 0;opacity:0;animation:slideIn .3s forwards;}
.log-line b{color:var(--text);}
.log-line.hot b{color:var(--accent);}

/* ---- GAMEOVER ---- */
.gameover{font-size:1.3rem;font-weight:700;text-align:center;padding:1.5rem;color:var(--yellow);}

/* animations */
@keyframes pulse{0%,100%{transform:scale(1);}50%{transform:scale(1.08);}}
@keyframes slideIn{from{opacity:0;transform:translateY(-4px);}to{opacity:1;transform:none;}}
@keyframes popUp{0%{opacity:1;transform:translateY(0);}100%{opacity:0;transform:translateY(-28px);}}
@keyframes flashRed{0%,100%{background:transparent;}50%{background:rgba(248,113,113,.15);}}
@keyframes fadeIn{from{opacity:0;}to{opacity:1;}}
.fadein{animation:fadeIn .35s forwards;}
</style>
</head>
<body>
<div class="page">
  <header>
    <div>
      <h1>🃏 Play vs the Bots</h1>
      <div class="toplinks"><a id="arena-link" href="#">📊 Live arena</a></div>
    </div>
  </header>

  <!-- ========== SETUP ========== -->
  <div id="setup">
    <div class="card">
      <h2>Build your table <span class="muted" id="seat-count" style="font-weight:400;text-transform:none;letter-spacing:0">— pick up to 4 opponents</span></h2>
      <div class="bot-grid" id="bot-grid"></div>
    </div>
    <div class="card" id="lineup-card" style="display:none">
      <h2>Your lineup</h2>
      <div class="lineup" id="lineup"></div>
      <div class="row">
        <button class="primary" id="start-btn">Start Game ▶</button>
        <button class="ghost" id="clear-btn">Clear all</button>
      </div>
    </div>
    <div class="card" style="background:none;border-color:var(--border);padding:.5rem .7rem;">
      <span class="muted" style="font-size:.72rem">💡 Tip: you can pick the same bot multiple times for an extra challenge. All bots play at full strength here.</span>
    </div>
  </div>

  <!-- ========== GAME ========== -->
  <div id="game" style="display:none">

    <!-- Turn banner -->
    <div id="turn-banner" class="bot-turn">
      <div class="banner-icon" id="banner-icon">⏳</div>
      <div class="banner-text">
        <div class="who" id="banner-who">Starting game…</div>
        <div class="sub" id="banner-sub"></div>
      </div>
      <div class="banner-deck">
        <div>Deck <b id="deck-count">–</b> cards</div>
        <div id="atk-line" style="display:none;color:var(--red)">⚔️ <b id="atk-count">1</b> turns left</div>
      </div>
    </div>

    <!-- Players -->
    <div class="players" id="players"></div>

    <!-- Main area: hand + actions side by side on wide, stacked on narrow -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:.9rem;align-items:start;">
      <div>
        <div class="card" style="min-height:140px;">
          <h2>Your hand</h2>
          <div class="hand-wrap" id="hand"></div>
        </div>
        <div class="card">
          <h2>Discard pile <span class="muted" style="font-weight:400;text-transform:none;letter-spacing:0;font-size:.7rem">(recent)</span></h2>
          <div class="discard-row" id="discard"></div>
        </div>
      </div>
      <div class="card">
        <div class="actions-section">
          <div class="prompt" id="act-prompt">Waiting for bots…</div>
          <div class="act-grid" id="act-grid"></div>
        </div>
      </div>
    </div>

    <!-- Game log -->
    <div class="card">
      <h2>Game log</h2>
      <div class="log-wrap" id="log"></div>
      <div style="margin-top:.7rem;display:none" id="again-wrap">
        <button class="ghost" id="again-btn">New game</button>
      </div>
    </div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
$('arena-link').href = location.origin.replace(/:\d+$/, ':8767');

// ---- card data ----
const CARD_DATA = {
  EXPLODING_KITTEN: {e:'💣',l:'Exploding\nKitten',c:'#ef4444'},
  DEFUSE:           {e:'🛡️',l:'Defuse',c:'#4ade80'},
  ATTACK:           {e:'⚔️',l:'Attack',c:'#f97316'},
  SKIP:             {e:'⏭️',l:'Skip',c:'#60a5fa'},
  FAVOR:            {e:'🙏',l:'Favor',c:'#c084fc'},
  SHUFFLE:          {e:'🔀',l:'Shuffle',c:'#2dd4bf'},
  SEE_THE_FUTURE:   {e:'🔮',l:'See the\nFuture',c:'#818cf8'},
  NOPE:             {e:'⛔',l:'Nope!',c:'#f87171'},
  TACO_CAT:         {e:'🌮',l:'Taco\nCat',c:'#fbbf24'},
  HAIRY_POTATO_CAT: {e:'🥔',l:'Potato\nCat',c:'#d97706'},
  BEARD_CAT:        {e:'🧔',l:'Beard\nCat',c:'#9ca3af'},
  RAINBOW_CAT:      {e:'🌈',l:'Rainbow\nCat',c:'#f472b6'},
  CATTERMELON:      {e:'🍉',l:'Catter-\nmelon',c:'#86efac'},
};
const nice = t => t.replace(/_/g,' ').toLowerCase().replace(/\b\w/g,c=>c.toUpperCase());

// Action type → emoji for action buttons
const ACT_EMO = {
  DRAW:'🂠', PLAY_ATTACK:'⚔️', PLAY_SKIP:'⏭️', PLAY_FAVOR:'🙏',
  PLAY_SHUFFLE:'🔀', PLAY_SEE_THE_FUTURE:'🔮', PLAY_NOPE:'⛔',
  PLAY_CAT_PAIR:'🐱', PLAY_CAT_TRIPLE:'🐱🐱', NOPE:'⛔', PASS:'✅',
  PLACE:'📍',
};

// ---- state ----
let SID = null;
let lineup = [];  // array of bot names (allows duplicates)
let gabrielUnlocked = false;

// Secret console command
window.unlockGabriel = () => {
  if (gabrielUnlocked) { console.log('🪬 Already unlocked.'); return; }
  gabrielUnlocked = true;
  renderBotGrid(window._botList || []);
  console.log('%c🪬 Gabriel revealed. They won\'t see this coming.', 'color:#d4af37;font-weight:bold;font-size:14px');
};

// ---- setup ----
let _botList = [];

async function loadBots() {
  const bots = await (await fetch('/api/play/bots')).json();
  _botList = bots;
  window._botList = bots;
  renderBotGrid(bots);
}

function renderBotGrid(bots) {
  const allBots = [...bots];
  if (gabrielUnlocked) {
    allBots.push({name:'Gabriel', emoji:'🪬', blurb:'"I have the keys of hell and of death."', gabriel:true});
  }
  $('bot-grid').innerHTML = allBots.map(b => {
    const cnt = lineup.filter(n => n === b.name).length;
    return `<div class="botcard${cnt>0?' picked':''}${b.gabriel?' gabriel':''}" id="bc-${b.name}">
      <div class="e">${b.emoji}</div>
      <div class="n">${b.name}</div>
      <div class="blurb">${b.blurb||''}</div>
      <div class="ctrls">
        <button onclick="changePick('${b.name}',-1)" title="Remove one">−</button>
        <span class="cnt">${cnt||'·'}</span>
        <button onclick="changePick('${b.name}',+1)" title="Add one">+</button>
      </div>
    </div>`;
  }).join('');
}

function changePick(name, delta) {
  if (delta > 0 && lineup.length >= 4) return;
  if (delta < 0) {
    const idx = lineup.lastIndexOf(name);
    if (idx === -1) return;
    lineup.splice(idx, 1);
  } else {
    lineup.push(name);
  }
  syncLineup();
}

function syncLineup() {
  // Update bot cards
  const allNames = new Set([..._botList.map(b=>b.name), gabrielUnlocked?'Gabriel':null].filter(Boolean));
  allNames.forEach(nm => {
    const el = document.getElementById('bc-'+nm);
    if (!el) return;
    const cnt = lineup.filter(n=>n===nm).length;
    el.className = 'botcard' + (cnt>0?' picked':'') + (nm==='Gabriel'?' gabriel':'');
    el.querySelector('.cnt').textContent = cnt || '·';
  });
  // Lineup preview
  $('seat-count').textContent = lineup.length === 0 ? '— pick up to 4 opponents' :
    `— ${lineup.length}/4 opponent${lineup.length!==1?'s':''}`;
  if (lineup.length === 0) {
    $('lineup-card').style.display = 'none';
    return;
  }
  $('lineup-card').style.display = '';
  $('lineup').innerHTML = lineup.map((nm,i) =>
    `<span class="lineup-slot">${BOT_EMOJI(nm)} ${nm}<span class="rm" onclick="lineup.splice(${i},1);syncLineup()">✕</span></span>`
  ).join('');
}

function BOT_EMOJI(nm) {
  const found = _botList.find(b=>b.name===nm);
  if (found) return found.emoji;
  if (nm==='Gabriel') return '🪬';
  return '🤖';
}

$('clear-btn').onclick = () => { lineup=[]; syncLineup(); };
$('start-btn').onclick = startGame;

async function startGame() {
  const opps = lineup.length ? lineup : ['Coyote','Rhino','Lucky'];
  $('start-btn').disabled = true;
  const s = await (await fetch('/api/play/new',{
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({opponents:opps})
  })).json();
  $('setup').style.display = 'none';
  $('game').style.display = '';
  render(s);
}

// ---- game rendering ----
let _thinkTimer = null;
let _thinkPoll  = null;
let _thinkStart = 0;

function startThinking() {
  _thinkStart = Date.now();
  $('turn-banner').className = 'bot-turn';
  $('banner-icon').textContent = '⏳';
  $('banner-who').textContent = 'Bots are playing…';
  $('banner-sub').textContent = '0.0s';
  $('act-prompt').textContent = 'Bot turns in progress…';
  $('act-grid').innerHTML = '';

  // Tick elapsed time at 100ms
  _thinkTimer = setInterval(() => {
    const sub = document.getElementById('banner-sub');
    if (sub) sub.textContent = ((Date.now() - _thinkStart) / 1000).toFixed(1) + 's';
  }, 100);

  // Poll log every 600ms so new events appear as bots play
  _thinkPoll = setInterval(async () => {
    if (!SID) return;
    try {
      const snap = await (await fetch('/api/play/state?id=' + SID)).json();
      if (snap.log) renderLog(snap.log);
      // Show latest log line in banner sub while waiting
      if (snap.log && snap.log.length) {
        const last = snap.log[snap.log.length - 1];
        const sub = document.getElementById('banner-sub');
        const t = ((Date.now() - _thinkStart) / 1000).toFixed(1);
        if (sub) sub.textContent = t + 's — ' + last.replace(/[🎉💀🛡️⚔️⏭️🙏🔀🔮⛔🐱💣]/gu, '').trim().slice(0, 40);
      }
    } catch(e) {}
  }, 600);
}

function stopThinking() {
  clearInterval(_thinkTimer); _thinkTimer = null;
  clearInterval(_thinkPoll);  _thinkPoll  = null;
}

async function send(i) {
  document.querySelectorAll('#act-grid button').forEach(b=>b.disabled=true);
  startThinking();
  try {
    const s = await (await fetch('/api/play/act',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:SID, index:i})
    })).json();
    stopThinking();
    render(s);
  } catch(e) {
    stopThinking();
    $('banner-who').textContent = 'Connection lost — try refreshing';
  }
}

function render(s) {
  SID = s.id || SID;

  // Game over
  if (s.result) {
    renderLog(s.log);
    const w = s.result.winner;
    const names = s.names || [];
    $('turn-banner').className = 'bot-turn';
    $('banner-icon').textContent = w===0?'🎉':(w>0?'💀':'💔');
    $('banner-who').textContent = w===0?'You win!':(w>0?`${names[w]} wins!`:'Game over');
    $('banner-sub').textContent = '';
    $('act-grid').innerHTML = `<div class="gameover">${w===0?'🎉 You win!':(w>0?('💀 '+names[w]+' wins — better luck next time.'):'Game over')}</div>`;
    $('act-prompt').textContent = '';
    $('again-wrap').style.display = '';
    return;
  }

  renderLog(s.log);

  const p = s.pending;
  if (!p) {
    // bots are thinking
    $('turn-banner').className = 'bot-turn';
    $('banner-icon').textContent = '⏳';
    $('banner-who').textContent = 'Bots are thinking…';
    $('banner-sub').textContent = '';
    $('act-prompt').textContent = 'Waiting for bots…';
    $('act-grid').innerHTML = '';
    return;
  }

  const st = p.state;
  const names = st.names || s.names || [];

  // Turn banner
  const isYourTurn = p.kind === 'choose_action' && st.current_player === 0;
  const isPrompt = p.kind === 'give' || p.kind === 'place_exact' || p.kind === 'nope';
  if (isYourTurn) {
    $('turn-banner').className = 'your-turn fadein';
    $('banner-icon').textContent = '🧍';
    $('banner-who').textContent = 'Your turn!';
    $('banner-sub').textContent = `${st.deck_size} cards in deck`;
  } else if (isPrompt) {
    $('turn-banner').className = 'prompt-turn fadein';
    $('banner-icon').textContent = '❓';
    $('banner-who').textContent = p.note || 'You need to choose';
    $('banner-sub').textContent = '';
  } else {
    const cp = st.current_player;
    $('turn-banner').className = 'bot-turn';
    $('banner-icon').textContent = cp >= 0 && cp < names.length ? BOT_EMOJI(names[cp]) : '🤖';
    $('banner-who').textContent = `${names[cp] || 'Bot'}'s turn`;
    $('banner-sub').textContent = '';
  }

  // Deck / attack counter
  $('deck-count').textContent = st.deck_size;
  if (st.turns_remaining > 1) {
    $('atk-line').style.display = '';
    $('atk-count').textContent = st.turns_remaining;
  } else {
    $('atk-line').style.display = 'none';
  }

  // Players
  $('players').innerHTML = names.map((nm,i) => {
    const alive = st.alive.includes(i);
    const hs = st.hand_sizes?.[String(i)] ?? 0;
    const isCur = i === st.current_player && alive;
    const isHero = i === 0;
    const isWinner = !!(s.result && s.result.winner === i);
    let cls = 'player';
    if (isCur) cls += ' current';
    if (isHero) cls += ' hero';
    if (!alive) cls += ' dead';
    if (isWinner) cls += ' winner';
    const miniCards = alive ? Array(Math.min(hs,8)).fill('<i></i>').join('') : '';
    return `<div class="${cls}">
      <div class="av">${isHero?'🧍':BOT_EMOJI(nm)}</div>
      <div class="nm">${nm}</div>
      <div class="hs">${alive?(hs+' card'+(hs!==1?'s':'')):'💀'}</div>
      <div class="mini-hand">${miniCards}</div>
    </div>`;
  }).join('');

  // Hand
  if (st.my_hand && st.my_hand.length > 0) {
    $('hand').innerHTML = st.my_hand.map(c => {
      const cd = CARD_DATA[c.type] || {e:'🃏',l:c.type};
      return `<div class="pcard" data-t="${c.type}" title="${nice(c.type)}">
        <div class="emo">${cd.e}</div>
        <div class="lbl">${cd.l}</div>
        ${c.n > 1 ? `<div class="cnt">×${c.n}</div>` : ''}
      </div>`;
    }).join('');
  } else {
    $('hand').innerHTML = '<span class="muted" style="font-size:.82rem">Empty hand</span>';
  }

  // Discard
  if (st.discard_pile && st.discard_pile.length) {
    const disc = [...st.discard_pile].reverse();
    $('discard').innerHTML = disc.map((t,i) => {
      const cd = CARD_DATA[t] || {e:'🃏'};
      return `<div class="dcard" title="${nice(t)}" style="${i===0?`border-color:${cd.c||'var(--muted)'}`:''}">
        ${cd.e}
      </div>`;
    }).join('');
  } else {
    $('discard').innerHTML = '<span class="muted" style="font-size:.78rem">Empty</span>';
  }

  // Actions
  $('act-prompt').textContent = p.note || (p.kind==='choose_action'?'Choose your action:':
    p.kind==='nope'?'Do you want to Nope?':'Choose:');

  if (p.kind === 'place_exact') {
    const ds = p.deck_size;
    $('act-grid').innerHTML = `
      <div style="margin:.3rem 0 .6rem">
        <div style="display:flex;justify-content:space-between;font-size:.72rem;color:var(--muted);margin-bottom:.35rem;">
          <span>☠️ Top (pos 0) — next player draws it</span>
          <span>Bottom (pos ${ds}) — safe</span>
        </div>
        <input id="place-slider" type="range" min="0" max="${ds}" value="${Math.floor(ds/2)}"
          style="width:100%;accent-color:var(--accent2);cursor:pointer;"
          oninput="$('place-val').textContent=this.value;updatePlaceLabel(this.value,${ds})">
        <div style="margin-top:.5rem;display:flex;align-items:center;gap:.7rem;">
          <span style="font-size:.82rem;color:var(--muted)">Position:</span>
          <span id="place-val" style="font-weight:700;font-size:1rem;min-width:2ch">${Math.floor(ds/2)}</span>
          <span id="place-label" style="font-size:.78rem;color:var(--muted)"></span>
        </div>
      </div>
      <button class="act-btn" onclick="sendPlace(${ds})">
        <span class="act-emo">📍</span> Bury kitten here
      </button>`;
    updatePlaceLabel(Math.floor(ds/2), ds);
  } else {
    const opts = p.valid || p.options || [];
    $('act-grid').innerHTML = opts.map(o => {
      const emo = ACT_EMO[o.type] || '▶';
      const isDraw = o.type === 'DRAW';
      const isDanger = ['PLAY_NOPE','NOPE'].includes(o.type);
      return `<button class="act-btn${isDraw?' draw':isDanger?' danger':''}" onclick="send(${o.i})">
        <span class="act-emo">${emo}</span> ${o.label}
      </button>`;
    }).join('');
  }
}

function updatePlaceLabel(pos, ds) {
  pos = parseInt(pos);
  let label = '';
  if (pos === 0) label = '☠️ Top of deck — next player draws it!';
  else if (pos === ds) label = '✅ Bottom of deck — safest spot';
  else if (pos <= Math.ceil(ds * 0.25)) label = 'Near the top — dangerous';
  else if (pos >= Math.floor(ds * 0.75)) label = 'Near the bottom — relatively safe';
  else label = 'Middle of the deck';
  const el = document.getElementById('place-label');
  if (el) el.textContent = label;
}

async function sendPlace(ds) {
  const slider = document.getElementById('place-slider');
  const pos = slider ? parseInt(slider.value) : Math.floor(ds / 2);
  document.querySelectorAll('#act-grid button').forEach(b => b.disabled = true);
  startThinking();
  try {
    const s = await (await fetch('/api/play/act', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: SID, index: pos})
    })).json();
    stopThinking();
    render(s);
  } catch(e) {
    stopThinking();
    $('banner-who').textContent = 'Connection lost — try refreshing';
  }
}

let _lastLogLen = 0;
function renderLog(lines) {
  if (!lines || !lines.length) return;
  const el = $('log');
  // Append only new lines
  const newLines = lines.slice(_lastLogLen);
  newLines.forEach(l => {
    const d = document.createElement('div');
    d.className = 'log-line' + (l.includes('explod') || l.includes('win') ? ' hot' : '');
    d.innerHTML = l.replace(/\*\*(.*?)\*\*/g,'<b>$1</b>');
    el.appendChild(d);
  });
  if (newLines.length) {
    _lastLogLen = lines.length;
    el.scrollTop = el.scrollHeight;
  }
}

$('again-btn').onclick = () => location.reload();

loadBots();
</script>
</body>
</html>'''
