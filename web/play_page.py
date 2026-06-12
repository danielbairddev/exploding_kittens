"""HTML for the play-vs-bots page. Served at /play by dashboard_server."""

PLAY_PAGE = r'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Exploding Kittens — Play vs the Bots</title>
<style>
  :root{--bg:#0f1117;--surface:#1a1d27;--surface2:#20232f;--border:#2e3146;--accent:#f97316;
        --accent2:#818cf8;--text:#e2e8f0;--muted:#94a3b8;--green:#4ade80;--red:#f87171;--yellow:#fbbf24;}
  *{box-sizing:border-box;margin:0;padding:0;}
  body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
       font-size:15px;line-height:1.5;padding:0 1rem 4rem;}
  .page{max-width:880px;margin:0 auto;}
  header{padding:1.8rem 0 1rem;display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:.5rem;}
  h1{font-size:1.6rem;color:var(--accent);} a{color:var(--accent2);text-decoration:none;}
  .card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1.1rem 1.2rem;margin-bottom:1rem;}
  h2{font-size:.8rem;text-transform:uppercase;letter-spacing:.08em;color:var(--accent2);margin-bottom:.7rem;}
  .bots{display:grid;grid-template-columns:repeat(4,1fr);gap:.5rem;}
  @media(max-width:560px){.bots{grid-template-columns:repeat(2,1fr);}}
  .botpick{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:.6rem;text-align:center;cursor:pointer;user-select:none;}
  .botpick.on{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent);}
  .botpick .e{font-size:1.5rem;} .botpick .n{font-size:.8rem;margin-top:.2rem;}
  .row{display:flex;gap:.8rem;align-items:center;flex-wrap:wrap;}
  button{background:var(--accent2);color:#1a1d27;border:none;border-radius:8px;padding:.55rem 1rem;font-weight:700;cursor:pointer;font-size:.9rem;}
  button.ghost{background:var(--surface2);color:var(--text);border:1px solid var(--border);}
  button:disabled{opacity:.5;cursor:default;}
  .toggle{display:flex;align-items:center;gap:.5rem;color:var(--muted);font-size:.9rem;cursor:pointer;}
  .players{display:grid;grid-template-columns:repeat(5,1fr);gap:.5rem;margin-bottom:.8rem;}
  @media(max-width:560px){.players{grid-template-columns:repeat(3,1fr);}}
  .pl{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:.5rem;text-align:center;}
  .pl.cur{border-color:var(--accent);box-shadow:0 0 14px -4px var(--accent);}
  .pl.dead{opacity:.4;} .pl .nm{font-weight:600;font-size:.8rem;} .pl .hs{font-size:.7rem;color:var(--muted);}
  .hand{display:flex;flex-wrap:wrap;gap:.4rem;margin:.5rem 0;}
  .ck{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:.35rem .6rem;font-size:.82rem;}
  .acts{display:flex;flex-direction:column;gap:.45rem;margin-top:.6rem;}
  .acts button{text-align:left;}
  .stat{display:flex;gap:1.2rem;color:var(--muted);font-size:.85rem;margin-bottom:.4rem;}
  .stat b{color:var(--text);}
  .coach{background:rgba(129,140,248,.08);border-left:3px solid var(--accent2);padding:.6rem .9rem;border-radius:0 8px 8px 0;margin-top:.6rem;font-size:.88rem;}
  .coach.blunder{background:rgba(248,113,113,.1);border-color:var(--red);}
  .coach.ok{background:rgba(74,222,128,.08);border-color:var(--green);}
  .log{margin-top:.6rem;font-size:.8rem;color:var(--muted);max-height:150px;overflow:auto;}
  .log div{padding:1px 0;}
  .sug{color:var(--yellow);font-size:.82rem;margin-bottom:.4rem;}
  .gameover{font-size:1.2rem;font-weight:700;text-align:center;padding:1rem;}
  .muted{color:var(--muted);font-size:.82rem;}
</style></head>
<body><div class="page">
  <header>
    <h1>🎮 Play vs the Bots</h1>
    <div class="muted">📊 <a id="arena" href="#">Live arena</a></div>
  </header>

  <div id="setup" class="card">
    <h2>Choose your table</h2>
    <p class="muted" style="margin-bottom:.6rem">Pick up to 4 opponents (you're the 5th seat). Fewer = smaller game.</p>
    <div class="bots" id="bots"></div>
    <div class="row" style="margin-top:1rem">
      <label class="toggle"><input type="checkbox" id="coach" checked> 🧠 Coach mode (show Orangutan's move + EV loss)</label>
    </div>
    <div class="row" style="margin-top:1rem">
      <button id="start">Start game</button>
      <span class="muted" id="pickinfo"></span>
    </div>
  </div>

  <div id="game" style="display:none">
    <div class="card">
      <div class="stat"><span>Deck: <b id="deck">–</b></span><span>Top discard: <b id="disc">–</b></span><span id="atkwrap" style="display:none">Turns left: <b id="atk">1</b></span></div>
      <div class="players" id="players"></div>
      <h2>Your hand</h2>
      <div class="hand" id="hand"></div>
      <div id="sug" class="sug"></div>
      <div id="prompt" class="muted"></div>
      <div class="acts" id="acts"></div>
      <div id="coachbox"></div>
    </div>
    <div class="card">
      <h2>Game log</h2>
      <div class="log" id="log"></div>
      <div class="row" style="margin-top:.6rem"><button class="ghost" id="again" style="display:none">New game</button></div>
    </div>
  </div>
</div>
<script>
const $=id=>document.getElementById(id);
$('arena').href = location.origin.replace(/:\d+$/, ':8767');
const CARD_EMOJI={EXPLODING_KITTEN:"💣",DEFUSE:"🛡️",ATTACK:"⚔️",SKIP:"⏭️",FAVOR:"🙏",SHUFFLE:"🔀",SEE_THE_FUTURE:"🔮",NOPE:"⛔",TACO_CAT:"🌮",HAIRY_POTATO_CAT:"🥔",BEARD_CAT:"🧔",RAINBOW_CAT:"🌈",CATTERMELON:"🍉"};
const nice=t=>t.replace(/_/g,' ').toLowerCase().replace(/\b\w/g,c=>c.toUpperCase());
let SID=null, picks=[];

async function loadBots(){
  const bots=await (await fetch('/api/play/bots')).json();
  $('bots').innerHTML=bots.map(b=>`<div class="botpick" data-n="${b.name}"><div class="e">${b.emoji}</div><div class="n">${b.name}</div></div>`).join('');
  document.querySelectorAll('.botpick').forEach(el=>el.onclick=()=>{
    const n=el.dataset.n;
    if(picks.includes(n)){picks=picks.filter(x=>x!==n);el.classList.remove('on');}
    else if(picks.length<4){picks.push(n);el.classList.add('on');}
    $('pickinfo').textContent=picks.length?picks.join(', '):'(default: Coyote, Sly2, Lucky)';
  });
}
$('start').onclick=async()=>{
  $('start').disabled=true;
  const s=await (await fetch('/api/play/new',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({opponents:picks,coach:$('coach').checked})})).json();
  $('setup').style.display='none'; $('game').style.display='';
  render(s);
};
$('again').onclick=()=>location.reload();

async function send(i){
  document.querySelectorAll('#acts button').forEach(b=>b.disabled=true);
  $('prompt').textContent='…thinking (coach is running rollouts)…';
  const s=await (await fetch('/api/play/act',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id:SID,index:i})})).json();
  render(s);
}

function render(s){
  SID=s.id||SID;
  // coach feedback from last move
  const cb=s.coach; const box=$('coachbox'); box.innerHTML='';
  if(cb){
    if(cb.match){ box.innerHTML=`<div class="coach ok">✅ Optimal — <b>${cb.your_move}</b> (${cb.your_ev}% win) was the best play by rollout.</div>`; }
    else{ const cls=cb.ev_loss>=8?'blunder':(cb.ev_loss>=2?'':'ok');
      box.innerHTML=`<div class="coach ${cls}">${cb.ev_loss>=8?'⚠️ Blunder':(cb.ev_loss>=2?'🟡 Slight miss':'≈ Fine')} — you played <b>${cb.your_move}</b> (${cb.your_ev}% win); best play <b>${cb.best_move}</b> (${cb.best_ev}% win). <b>EV loss: ${cb.ev_loss}%</b></div>`; }
  }
  $('log').innerHTML=(s.log||[]).map(l=>`<div>${l}</div>`).join('');
  if(s.result){
    const w=s.result.winner; const names=s.names||[];
    $('players').innerHTML=''; $('hand').innerHTML=''; $('acts').innerHTML=''; $('sug').textContent=''; $('prompt').innerHTML='';
    $('acts').innerHTML=`<div class="gameover">${w===0?'🎉 You win!':(w>0?('💀 '+names[w]+' wins'):'Game over')}</div>`;
    $('again').style.display=''; return;
  }
  const p=s.pending; if(!p){ $('prompt').textContent='Waiting…'; return; }
  const st=p.state;
  // table
  $('deck').textContent=st.deck_size; $('disc').textContent=st.discard_top?(CARD_EMOJI[st.discard_top]+' '+nice(st.discard_top)):'–';
  if(st.turns_remaining>1){$('atkwrap').style.display='';$('atk').textContent=st.turns_remaining;}else{$('atkwrap').style.display='none';}
  $('players').innerHTML=(st.names||[]).map((nm,i)=>{
    const alive=st.alive.includes(i); const hs=st.hand_sizes[String(i)]??0;
    return `<div class="pl ${i===st.current_player?'cur':''} ${alive?'':'dead'}"><div class="nm">${i===0?'🧍 You':nm}</div><div class="hs">${alive?hs+' cards':'💀'}</div></div>`;
  }).join('');
  $('hand').innerHTML=st.my_hand.map(c=>`<span class="ck">${CARD_EMOJI[c.type]||''} ${nice(c.type)}${c.n>1?(' ×'+c.n):''}</span>`).join('') || '<span class="muted">empty</span>';
  $('sug').textContent = p.orangutan ? ('🧠 Orangutan would: '+p.orangutan) : '';
  $('prompt').textContent = p.note || (p.kind==='choose_action'?'Your turn — choose an action:':'Choose:');
  const opts = p.valid || p.options || [];
  $('acts').innerHTML=opts.map(o=>`<button onclick="send(${o.i})">${o.label}</button>`).join('');
}
loadBots();
</script></body></html>'''
