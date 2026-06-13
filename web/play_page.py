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

/* ---- NOPE STACK ---- */
#nope-overlay{
  display:none;border-radius:16px;padding:1.3rem 1.4rem;margin-bottom:.9rem;
  background:var(--surface);border:2px solid var(--red);
  box-shadow:0 0 50px -8px rgba(248,113,113,.5);
  position:relative;
}
#nope-overlay.active{display:block;animation:nopeAppear .25s cubic-bezier(.17,.67,.36,1.4) forwards;}
@keyframes nopeAppear{from{transform:scale(.95);opacity:0;}to{transform:scale(1);opacity:1;}}
.nope-header{font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;color:var(--red);font-weight:700;margin-bottom:.9rem;display:flex;align-items:center;gap:.4rem;}
.nope-stack-rows{display:flex;flex-direction:column;gap:.45rem;margin-bottom:1rem;}
.stack-row{
  background:var(--surface2);border:1.5px solid var(--border);border-radius:10px;
  padding:.6rem .9rem;display:flex;align-items:center;gap:.6rem;font-size:.88rem;
}
.stack-row.action-row{border-color:#f97316;}
.stack-row.noped-row{border-color:var(--red);opacity:.85;}
.stack-row .sr-icon{font-size:1.3rem;flex-shrink:0;}
.stack-row .sr-text{flex:1;}
.stack-row .sr-text .sr-who{font-weight:600;color:var(--text);}
.stack-row .sr-text .sr-what{color:var(--muted);font-size:.8rem;}
.stack-row .sr-badge{
  font-size:.65rem;font-weight:700;padding:2px 7px;border-radius:8px;
  text-transform:uppercase;letter-spacing:.06em;flex-shrink:0;
}
.stack-row .sr-badge.cancelled{background:rgba(248,113,113,.18);color:var(--red);}
.stack-row .sr-badge.restored{background:rgba(74,222,128,.15);color:var(--green);}
.nope-status{
  text-align:center;font-size:.82rem;font-weight:700;padding:.45rem;
  border-radius:8px;margin-bottom:.9rem;
}
.nope-status.noped{background:rgba(248,113,113,.12);color:var(--red);}
.nope-status.active{background:rgba(74,222,128,.1);color:var(--green);}
.nope-btns{display:grid;grid-template-columns:1fr 1fr;gap:.6rem;}
.nope-btns button{
  padding:.8rem;border-radius:12px;border:2px solid;font-size:.95rem;font-weight:700;
  cursor:pointer;transition:opacity .15s,transform .1s;
}
.nope-btns button:hover{opacity:.85;transform:translateY(-2px);}
.nope-btns button:disabled{opacity:.4;cursor:default;transform:none;}
.nope-btn-yes{background:rgba(248,113,113,.15);border-color:var(--red);color:var(--red);}
.nope-btn-pass{background:rgba(100,116,139,.12);border-color:var(--border);color:var(--muted);}

/* ---- STAGE (bot action animations) ---- */
#stage{
  border-radius:14px;padding:1.2rem;margin-bottom:.9rem;
  background:var(--surface);border:1.5px solid var(--border);
  text-align:center;position:relative;display:none;
  transition:border-color .2s,box-shadow .2s;
}
#stage.active{display:block;}
#stage.ev-explode{border-color:#ef4444;box-shadow:0 0 50px -8px #ef4444;}
#stage.ev-defuse {border-color:var(--green);box-shadow:0 0 40px -8px var(--green);}
#stage.ev-nope   {border-color:var(--red);box-shadow:0 0 30px -6px var(--red);}
#stage.ev-attack {border-color:var(--accent);box-shadow:0 0 30px -6px var(--accent);}
#stage.ev-cat    {border-color:var(--pink);box-shadow:0 0 24px -6px var(--pink);}
#stage.ev-favor  {border-color:#c084fc;box-shadow:0 0 24px -6px #c084fc;}
#stage.ev-shuffle{border-color:#2dd4bf;box-shadow:0 0 24px -6px #2dd4bf;}
#stage.ev-future {border-color:var(--accent2);box-shadow:0 0 24px -6px var(--accent2);}
.stage-icon{font-size:2.8rem;line-height:1;animation:stagePop .35s cubic-bezier(.17,.67,.36,1.4) forwards;}
.stage-text{font-size:1.05rem;font-weight:700;margin-top:.5rem;}
.stage-sub{font-size:.82rem;color:var(--muted);margin-top:.2rem;}

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

/* Player flash effects */
@keyframes flRed   {0%,100%{background:var(--surface2);}50%{background:rgba(248,113,113,.25);box-shadow:inset 0 0 20px rgba(248,113,113,.3);}}
@keyframes flGreen {0%,100%{background:var(--surface2);}50%{background:rgba(74,222,128,.2);box-shadow:inset 0 0 20px rgba(74,222,128,.25);}}
@keyframes flYellow{0%,100%{background:var(--surface2);}50%{background:rgba(251,191,36,.18);box-shadow:inset 0 0 20px rgba(251,191,36,.22);}}
@keyframes flPurple{0%,100%{background:var(--surface2);}50%{background:rgba(192,132,252,.18);box-shadow:inset 0 0 20px rgba(192,132,252,.22);}}
.fl-red   {animation:flRed    .75s ease-in-out !important;}
.fl-green {animation:flGreen  .75s ease-in-out !important;}
.fl-yellow{animation:flYellow .75s ease-in-out !important;}
.fl-purple{animation:flPurple .75s ease-in-out !important;}

/* Player action bubbles */
.player-pop{
  position:absolute;bottom:calc(100% + 6px);left:50%;
  transform:translateX(-50%);
  background:var(--surface);border:1.5px solid var(--border);
  border-radius:10px;padding:4px 9px;font-size:.72rem;font-weight:700;
  white-space:nowrap;pointer-events:none;z-index:20;
  animation:playerPopFade var(--pop-dur, 1.8s) ease-in-out forwards;
}
@keyframes playerPopFade{
  0%  {opacity:0;transform:translateX(-50%) translateY(6px);}
  15% {opacity:1;transform:translateX(-50%) translateY(0);}
  70% {opacity:1;}
  100%{opacity:0;transform:translateX(-50%) translateY(-10px);}
}

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

/* Speed control */
.speed-ctrl{display:flex;align-items:center;gap:.4rem;font-size:.72rem;color:var(--muted);}
.speed-ctrl select{
  background:var(--surface2);color:var(--text);border:1px solid var(--border);
  border-radius:5px;font-size:.7rem;padding:2px 5px;cursor:pointer;
}

/* ---- PEEK STACK (see the future) ---- */
.peek-stack{display:flex;justify-content:center;gap:.7rem;margin-top:.9rem;flex-wrap:wrap;}
.peek-card{
  background:linear-gradient(145deg,#1e2235,#252839);
  border:1.5px solid var(--border);border-radius:10px;
  padding:.55rem .6rem;text-align:center;min-width:64px;
  position:relative;
}
.peek-card[data-t="EXPLODING_KITTEN"]{border-color:var(--red);box-shadow:0 0 10px -2px #ef4444;}
.peek-card[data-t="DEFUSE"]{border-color:var(--green);}
.peek-card[data-t="NOPE"]{border-color:var(--red);}
.peek-card[data-t="ATTACK"]{border-color:#f97316;}
.peek-card[data-t="SEE_THE_FUTURE"]{border-color:var(--accent2);}
.peek-pos{font-size:.55rem;text-transform:uppercase;letter-spacing:.07em;color:var(--accent2);font-weight:700;margin-bottom:.2rem;}
.peek-pos.next{color:var(--red);}
.peek-emo{font-size:1.6rem;line-height:1;}
.peek-name{font-size:.6rem;color:var(--muted);margin-top:.25rem;line-height:1.2;}

/* ---- GAMEOVER ---- */
.gameover{font-size:1.3rem;font-weight:700;text-align:center;padding:1.5rem;color:var(--yellow);}

/* animations */
@keyframes pulse{0%,100%{transform:scale(1);}50%{transform:scale(1.08);}}
@keyframes slideIn{from{opacity:0;transform:translateY(-4px);}to{opacity:1;transform:none;}}
@keyframes popUp{0%{opacity:1;transform:translateY(0);}100%{opacity:0;transform:translateY(-28px);}}
@keyframes stagePop{from{transform:scale(.5);opacity:0;}to{transform:scale(1);opacity:1;}}
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

    <!-- Nope stack overlay (shown when human can nope) -->
    <div id="nope-overlay"></div>

    <!-- Stage (bot action animations) -->
    <div id="stage"></div>

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
      <h2>Game log <span class="speed-ctrl">
        Speed:
        <select id="anim-speed">
          <option value="5000">Glacial</option>
          <option value="2500">Very slow</option>
          <option value="1400" selected>Slow</option>
          <option value="700">Normal</option>
          <option value="280">Fast</option>
          <option value="80">Turbo</option>
        </select>
      </span></h2>
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

// ---- Animation stage config ----
// Maps event type → {icon, cls, flash for actor, flashTarget, sub(nm, tnm)}
// Conjugate verb: strip trailing 's' for "You"
const _v = (nm, w) => nm === 'You' ? w.replace(/s$/, '') : w;

const STAGE_CFG = {
  explode:      {icon:'💣', cls:'ev-explode', flash:'fl-red',                                 popText:'💣 BOOM!',         sub:(nm)       => `${nm} EXPLODES!`},
  defuse:       {icon:'🛡️', cls:'ev-defuse',  flash:'fl-green',                               popText:'🛡️ defused!',      sub:(nm)       => `${nm} defuses it!`},
  attack:       {icon:'⚔️', cls:'ev-attack',  flash:'fl-yellow', flashTgt:'fl-red',    tgt:true, popText:'⚔️ attacks!', popTgt:'💥 targeted', sub:(nm,tnm) => `${nm} ${_v(nm,'attacks')} ${tnm}`},
  skip:         {icon:'⏭️', cls:'ev-shuffle', flash:'fl-yellow',                               popText:'⏭️ skips',         sub:(nm)       => `${nm} ${_v(nm,'skips')}`},
  favor:        {icon:'🙏', cls:'ev-favor',   flash:'fl-purple', flashTgt:'fl-purple', tgt:true, popText:'🙏 favors',   popTgt:'🎁 lost a card', sub:(nm,tnm) => `${nm} ${_v(nm,'favors')} ${tnm}`},
  shuffle:      {icon:'🔀', cls:'ev-shuffle', flash:'fl-yellow',                               popText:'🔀 shuffles',      sub:(nm)       => `${nm} ${_v(nm,'shuffles')} the deck`},
  see_future:   {icon:'🔮', cls:'ev-future',  flash:'fl-purple',                               popText:'🔮 peeks',         sub:(nm)       => `${nm} ${_v(nm,'sees')} the future`},
  nope:         {icon:'⛔', cls:'ev-nope',    flash:'fl-red',                                 popText:'⛔ NOPE!',         sub:(nm)       => `${nm} plays Nope!`},
  action_noped: {icon:'🚫', cls:'ev-nope',    flash:null,                                      popText:null,               sub:()         => `Action cancelled by Nope!`},
  cat_steal:    {icon:'🐱', cls:'ev-cat',     flash:'fl-purple', flashTgt:'fl-red',    tgt:true, popText:'🐱 steals!',  popTgt:'🎴 stolen from', sub:(nm,tnm) => `${nm} ${_v(nm,'steals')} from ${tnm}`},
  draw:         {icon:'🂠', cls:'',           flash:null,                                      popText:null,               sub:(nm)       => `${nm} ${_v(nm,'draws')}`},
};

// Action type → display emoji for nope stack
const ACT_ICON = {
  PLAY_ATTACK:'⚔️', PLAY_SKIP:'⏭️', PLAY_FAVOR:'🙏', PLAY_SHUFFLE:'🔀',
  PLAY_SEE_THE_FUTURE:'🔮', PLAY_CAT_PAIR:'🐱', PLAY_CAT_TRIPLE:'🐱🐱',
};

// ---- Animation queue state ----
let _animQueue   = [];
let _animCursor  = -1;
let _animRunning = false;
let _animTimers  = [];
let _stageHide   = null;

function getSpeed() {
  const el = document.getElementById('anim-speed');
  return el ? parseInt(el.value) : 320;
}

function enqueueEvents(events) {
  if (!events || !events.length) return;
  const novel = events.filter(e => e.id > _animCursor);
  if (!novel.length) return;
  _animQueue.push(...novel);
  if (!_animRunning) _processQueue();
}

function _processQueue() {
  if (!_animQueue.length) { _animRunning = false; return; }
  _animRunning = true;
  const ev = _animQueue.shift();

  // Pseudo-events: apply state then continue immediately (no delay)
  if (ev.type === '_state_update') {
    _applyStateUpdate(ev);
    _processQueue();
    return;
  }
  if (ev.type === '_nope_prompt') {
    _animRunning = false;
    renderNopeStack(ev.pending);
    return;
  }

  if (ev.id !== undefined) _animCursor = Math.max(_animCursor, ev.id);
  _showStageEvent(ev);
  const t = setTimeout(_processQueue, getSpeed());
  _animTimers.push(t);
}

// Apply deferred state update (fires after animations for this batch)
function _applyStateUpdate(ev) {
  if (ev.result !== undefined) {
    // Game over — update banner now that final animations have played
    const w = ev.result.winner;
    const names = ev.names || [];
    $('turn-banner').className = w === 0 ? 'your-turn' : 'bot-turn';
    $('banner-icon').textContent = w===0?'🎉':(w>0?'💀':'💔');
    $('banner-who').textContent = w===0?'You win!':(w>0?`${names[w]} wins!`:'Game over');
    $('banner-sub').textContent = `Game over after ${ev.result.turns||'?'} turns`;
    const survivors = ev.result.survivors || (w >= 0 ? [w] : []);
    $('players').innerHTML = names.map((nm, i) => {
      const alive = survivors.includes(i);
      const isWinner = i === w;
      let cls = 'player' + (i===0?' hero':'') + (!alive?' dead':'') + (isWinner?' winner':'');
      return `<div class="${cls}">
        <div class="av">${i===0?'🧍':BOT_EMOJI(nm)}</div>
        <div class="nm">${nm}</div>
        <div class="hs">${alive?'🏆 survived':'💀 exploded'}</div>
        <div class="mini-hand"></div>
      </div>`;
    }).join('');
    $('hand').innerHTML = '<span class="muted" style="font-size:.82rem">Game over</span>';
    $('discard').innerHTML = '';
    $('act-grid').innerHTML = `<div class="gameover">${w===0?'🎉 You win!':(w>0?('💀 '+names[w]+' wins — better luck next time.'):'Game over')}</div>`;
    $('act-prompt').textContent = '';
    $('atk-line').style.display = 'none';
    $('again-wrap').style.display = '';
    // Flush any log lines not covered by anim events (win message, etc.)
    if (ev.log) renderLog(ev.log);
    return;
  }

  const {st, names, p} = ev;

  // Banner — now that animations for this batch have played
  const isYourTurn = p && p.kind === 'choose_action' && st.current_player === 0;
  const isNope     = p && p.kind === 'nope';
  const isPrompt   = p && (p.kind === 'give' || p.kind === 'place_exact');
  if (isNope) {
    $('turn-banner').className = 'prompt-turn';
    $('banner-icon').textContent = '⚡';
    $('banner-who').textContent = 'Nope opportunity incoming…';
    $('banner-sub').textContent = p.action_label || '';
  } else if (isYourTurn) {
    $('turn-banner').className = 'your-turn fadein';
    $('banner-icon').textContent = '🧍';
    $('banner-who').textContent = 'Your turn!';
    $('banner-sub').textContent = '';
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

  // Players / hand / discard
  renderStateView(st, names);

  // Flush any log lines not emitted by individual anim events (see_future peek, etc.)
  if (ev.log) renderLog(ev.log);

  // Action grid (skip for nope — that's handled by _nope_prompt)
  if (!p || p.kind === 'nope') return;

  $('act-prompt').textContent = p.note || (p.kind==='choose_action' ? 'Choose your action:' : 'Choose:');

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
  } else if (p.kind === 'give') {
    const opts = p.options || [];
    $('act-grid').innerHTML = opts.map(o => {
      const emo = ACT_EMO[o.type] || '🃏';
      return `<button class="act-btn" onclick="send(${o.i})">
        <span class="act-emo">${emo}</span> ${o.label}
      </button>`;
    }).join('');
  } else {
    const opts = p.valid || [];
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

function _showStageEvent(ev) {
  const cfg = STAGE_CFG[ev.type];
  if (!cfg) return;
  if (ev.log) appendLogLine(ev.log);
  const stageEl = $('stage');
  if (!stageEl) return;

  const names = window._curNames || [];
  const nm  = names[ev.player] || (ev.player >= 0 ? `P${ev.player}` : '');
  const tnm = names[ev.target] || (ev.target  >= 0 ? `P${ev.target}` : '');

  stageEl.className = 'active' + (cfg.cls ? ' ' + cfg.cls : '');

  let extraHtml = '';
  if (ev.type === 'see_future' && ev.cards && ev.cards.length) {
    const peekCards = ev.cards.map((ct, i) => {
      const cd = CARD_DATA[ct] || {e:'🃏', l:ct.replace(/_/g,' ')};
      return `<div class="peek-card" data-t="${ct}">
        <div class="peek-pos${i===0?' next':''}">${i===0?'next drawn':'#'+(i+1)}</div>
        <div class="peek-emo">${cd.e}</div>
        <div class="peek-name">${cd.l}</div>
      </div>`;
    }).join('');
    extraHtml = `<div class="peek-stack">${peekCards}</div>`;
  }

  stageEl.innerHTML = `
    <div class="stage-icon">${cfg.icon}</div>
    <div class="stage-text">${cfg.sub(nm, tnm)}</div>
    ${extraHtml}
  `;

  // Flash + popup actor
  if (cfg.flash && ev.player >= 0) _flashPlayer(ev.player, cfg.flash);
  if (cfg.popText && ev.player >= 0) _popAbovePlayer(ev.player, cfg.popText, null);

  // Flash + popup target after a beat
  if (cfg.tgt && ev.target >= 0) {
    if (cfg.flashTgt) {
      const t2 = setTimeout(() => _flashPlayer(ev.target, cfg.flashTgt), 200);
      _animTimers.push(t2);
    }
    if (cfg.popTgt) {
      const t3 = setTimeout(() => _popAbovePlayer(ev.target, cfg.popTgt, 'var(--red)'), 200);
      _animTimers.push(t3);
    }
  }

  // Hide stage after delay
  if (_stageHide) clearTimeout(_stageHide);
  _stageHide = setTimeout(() => {
    const el = $('stage');
    if (el && !_animQueue.length) el.className = '';
  }, getSpeed() * 2.2);
}

function _flashPlayer(idx, cls) {
  const players = $('players');
  if (!players) return;
  const cards = players.querySelectorAll('.player');
  if (!cards[idx]) return;
  cards[idx].classList.remove('fl-red','fl-green','fl-yellow','fl-purple');
  void cards[idx].offsetWidth; // force reflow to restart animation
  cards[idx].classList.add(cls);
  const t = setTimeout(() => { if (cards[idx]) cards[idx].classList.remove(cls); }, 850);
  _animTimers.push(t);
}

function _popAbovePlayer(idx, text, borderColor) {
  const players = $('players');
  if (!players) return;
  const cards = players.querySelectorAll('.player');
  if (!cards[idx]) return;
  // Remove any existing popup on this player
  const old = cards[idx].querySelector('.player-pop');
  if (old) old.remove();
  const dur = Math.max(getSpeed() * 2.5, 1400);
  const pop = document.createElement('div');
  pop.className = 'player-pop';
  pop.style.setProperty('--pop-dur', dur + 'ms');
  if (borderColor) pop.style.borderColor = borderColor;
  pop.textContent = text;
  cards[idx].appendChild(pop);
  const t = setTimeout(() => { if (pop.parentNode) pop.remove(); }, dur + 100);
  _animTimers.push(t);
}

function cancelAnim() {
  _animTimers.forEach(clearTimeout);
  _animTimers  = [];
  _animQueue   = [];
  _animRunning = false;
  if (_stageHide) { clearTimeout(_stageHide); _stageHide = null; }
  const el = $('stage');
  if (el) el.className = '';
}

// ---- state ----
let SID = null;
let lineup = [];
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
  const allNames = new Set([..._botList.map(b=>b.name), gabrielUnlocked?'Gabriel':null].filter(Boolean));
  allNames.forEach(nm => {
    const el = document.getElementById('bc-'+nm);
    if (!el) return;
    const cnt = lineup.filter(n=>n===nm).length;
    el.className = 'botcard' + (cnt>0?' picked':'') + (nm==='Gabriel'?' gabriel':'');
    el.querySelector('.cnt').textContent = cnt || '·';
  });
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
  cancelAnim();
  _animCursor = -1;
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

  _thinkTimer = setInterval(() => {
    const sub = $('banner-sub');
    if (sub) sub.textContent = ((Date.now() - _thinkStart) / 1000).toFixed(1) + 's';
  }, 100);

  _thinkPoll = setInterval(async () => {
    if (!SID) return;
    try {
      const snap = await (await fetch('/api/play/state?id=' + SID)).json();
      if (snap.anim_events) enqueueEvents(snap.anim_events);
      if (snap.log && snap.log.length) {
        const last = snap.log[snap.log.length - 1];
        const sub = $('banner-sub');
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

function renderStateView(st, names) {
  $('players').innerHTML = names.map((nm,i) => {
    const alive = st.alive.includes(i);
    const hs = st.hand_sizes?.[String(i)] ?? 0;
    const isCur = i === st.current_player && alive;
    const isHero = i === 0;
    let cls = 'player';
    if (isCur) cls += ' current';
    if (isHero) cls += ' hero';
    if (!alive) cls += ' dead';
    const miniCards = alive ? Array(Math.min(hs,8)).fill('<i></i>').join('') : '';
    return `<div class="${cls}">
      <div class="av">${isHero?'🧍':BOT_EMOJI(nm)}</div>
      <div class="nm">${nm}</div>
      <div class="hs">${alive?(hs+' card'+(hs!==1?'s':'')):'💀'}</div>
      <div class="mini-hand">${miniCards}</div>
    </div>`;
  }).join('');

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

  if (st.discard_pile && st.discard_pile.length) {
    const disc = [...st.discard_pile].reverse();
    $('discard').innerHTML = disc.map((t,idx) => {
      const cd = CARD_DATA[t] || {e:'🃏'};
      return `<div class="dcard" title="${nice(t)}" style="${idx===0?`border-color:${cd.c||'var(--muted)'}`:''}">
        ${cd.e}
      </div>`;
    }).join('');
  } else {
    $('discard').innerHTML = '<span class="muted" style="font-size:.78rem">Empty</span>';
  }
}

function render(s) {
  SID = s.id || SID;
  if (s.names) window._curNames = s.names;

  // Queue animation events FIRST so they run before the state update
  if (s.anim_events) enqueueEvents(s.anim_events);

  // Clear nope overlay (re-shown by queue when its turn comes)
  const _nopeEl = $('nope-overlay');
  if (_nopeEl) _nopeEl.className = '';

  // Game over — queue everything after animations
  if (s.result) {
    _animQueue.push({type: '_state_update', result: s.result, names: s.names || [], log: s.log});
    if (!_animRunning) _processQueue();
    return;
  }

  const p = s.pending;
  if (!p) {
    // Timeout fallback: bots still computing, nothing to queue
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

  // Queue EVERYTHING — banner, deck, players, hand, actions — all after animations
  _animQueue.push({type: '_state_update', st, names, p, log: s.log});
  if (p.kind === 'nope') _animQueue.push({type: '_nope_prompt', pending: p});
  if (!_animRunning) _processQueue();
}


function renderNopeStack(p) {
  // Update banner now that animations have played and nope is shown
  $('turn-banner').className = 'prompt-turn fadein';
  $('banner-icon').textContent = '⛔';
  $('banner-who').textContent = p.currently_noped ? 'Counter-nope opportunity!' : 'Nope opportunity!';
  $('banner-sub').textContent = p.action_label || '';

  const el = $('nope-overlay');
  if (!el) return;

  const actionIcon = ACT_ICON[p.action_type] || '🃏';
  const isCancelled = p.currently_noped;

  // Build stack rows: original action on bottom, nopes stacked above
  let rows = '';

  // Original action row (always first)
  rows += `<div class="stack-row action-row">
    <div class="sr-icon">${actionIcon}</div>
    <div class="sr-text">
      <div class="sr-who">${p.actor_name || '?'}</div>
      <div class="sr-what">${p.action_label || 'plays a card'}</div>
    </div>
  </div>`;

  // Nope chain rows
  const chain = p.nope_chain || [];
  chain.forEach(n => {
    const cancelled = n.result === 'cancelled';
    rows += `<div class="stack-row noped-row">
      <div class="sr-icon">⛔</div>
      <div class="sr-text">
        <div class="sr-who">${n.name}</div>
        <div class="sr-what">plays Nope!</div>
      </div>
      <div class="sr-badge ${cancelled?'cancelled':'restored'}">${cancelled?'Cancelled':'Restored'}</div>
    </div>`;
  });

  // Status line
  const statusCls = isCancelled ? 'noped' : 'active';
  const statusText = isCancelled
    ? '⛔ Action is currently CANCELLED — counter-nope to restore it'
    : '✅ Action will happen — Nope it to cancel';

  el.className = 'active';
  el.innerHTML = `
    <div class="nope-header">⚡ Nope stack</div>
    <div class="nope-stack-rows">${rows}</div>
    <div class="nope-status ${statusCls}">${statusText}</div>
    <div class="nope-btns">
      <button class="nope-btn-yes" onclick="nopeDecide(0)">⛔ ${isCancelled ? 'Counter-nope!' : 'Nope it!'}</button>
      <button class="nope-btn-pass" onclick="nopeDecide(1)">✅ ${isCancelled ? 'Let it be cancelled' : 'Let it happen'}</button>
    </div>
  `;
}

function updatePlaceLabel(pos, ds) {
  pos = parseInt(pos);
  let label = '';
  if (pos === 0) label = '☠️ Top of deck — next player draws it!';
  else if (pos === ds) label = '✅ Bottom of deck — safest spot';
  else if (pos <= Math.ceil(ds * 0.25)) label = 'Near the top — dangerous';
  else if (pos >= Math.floor(ds * 0.75)) label = 'Near the bottom — relatively safe';
  else label = 'Middle of the deck';
  const el = $('place-label');
  if (el) el.textContent = label;
}

async function sendPlace(ds) {
  const slider = $('place-slider');
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

function nopeDecide(i) {
  // Disable nope buttons immediately so double-click can't happen
  const el = $('nope-overlay');
  if (el) el.querySelectorAll('button').forEach(b => b.disabled = true);
  send(i);
}

let _lastLogLen = 0;
function appendLogLine(msg) {
  if (!msg) return;
  const el = $('log');
  if (!el) return;
  const d = document.createElement('div');
  d.className = 'log-line' + (msg.includes('explod') || msg.includes('win') ? ' hot' : '');
  d.innerHTML = msg.replace(/\*\*(.*?)\*\*/g,'<b>$1</b>');
  el.appendChild(d);
  el.scrollTop = el.scrollHeight;
  _lastLogLen++;
}
function renderLog(lines) {
  if (!lines || !lines.length) return;
  const el = $('log');
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
