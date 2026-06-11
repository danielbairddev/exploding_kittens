#!/usr/bin/env python3
"""
Protocol documentation server for Exploding Kittens agents.
Usage: python protocol_server.py [port]
"""
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Exploding Kittens — Agent Protocol</title>
<style>
  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --border: #2e3146;
    --accent: #f97316;
    --accent2: #818cf8;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --code-bg: #111827;
    --green: #4ade80;
    --red: #f87171;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 15px;
    line-height: 1.65;
    padding: 0 1rem 4rem;
  }
  .page { max-width: 860px; margin: 0 auto; }
  header {
    padding: 3rem 0 2rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 2.5rem;
  }
  header h1 { font-size: 2rem; color: var(--accent); letter-spacing: -0.5px; }
  header p  { color: var(--muted); margin-top: 0.4rem; font-size: 0.95rem; }
  h2 {
    font-size: 1.3rem;
    color: var(--accent2);
    margin: 2.5rem 0 0.8rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid var(--border);
  }
  h3 { font-size: 1rem; color: var(--text); margin: 1.6rem 0 0.4rem; font-weight: 600; }
  p  { margin: 0.6rem 0; color: var(--muted); }
  ul { padding-left: 1.4rem; color: var(--muted); }
  li { margin: 0.25rem 0; }
  strong { color: var(--text); }
  code {
    font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", monospace;
    font-size: 0.875rem;
    background: var(--code-bg);
    border: 1px solid var(--border);
    padding: 0.15em 0.4em;
    border-radius: 4px;
    color: #a5f3fc;
  }
  pre {
    background: var(--code-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.1rem 1.3rem;
    overflow-x: auto;
    margin: 0.8rem 0;
    font-family: "JetBrains Mono", "Fira Code", monospace;
    font-size: 0.83rem;
    line-height: 1.6;
    color: #e2e8f0;
  }
  pre .key   { color: #818cf8; }
  pre .str   { color: #86efac; }
  pre .num   { color: #fbbf24; }
  pre .null  { color: #f87171; }
  pre .cmt   { color: #64748b; font-style: italic; }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 0.8rem 0;
    font-size: 0.9rem;
  }
  th {
    background: var(--surface);
    color: var(--accent2);
    text-align: left;
    padding: 0.55rem 0.9rem;
    border: 1px solid var(--border);
    font-weight: 600;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  td {
    padding: 0.5rem 0.9rem;
    border: 1px solid var(--border);
    color: var(--muted);
    vertical-align: top;
  }
  td:first-child { color: #a5f3fc; font-family: monospace; font-size: 0.875rem; }
  tr:nth-child(even) td { background: rgba(255,255,255,0.02); }
  .endpoint {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.2rem 1.4rem;
    margin: 1rem 0;
  }
  .endpoint h3 { margin: 0 0 0.5rem; }
  .method {
    display: inline-block;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    padding: 0.2em 0.6em;
    border-radius: 4px;
    margin-right: 0.5rem;
  }
  .get  { background: #1d4ed8; color: #bfdbfe; }
  .post { background: #15803d; color: #bbf7d0; }
  .path { font-family: monospace; font-size: 1rem; color: var(--text); }
  .tag {
    display: inline-block;
    background: rgba(249,115,22,0.15);
    color: var(--accent);
    border: 1px solid rgba(249,115,22,0.3);
    font-size: 0.75rem;
    padding: 0.15em 0.5em;
    border-radius: 4px;
    margin-left: 0.4rem;
    vertical-align: middle;
  }
  .note {
    background: rgba(129,140,248,0.08);
    border-left: 3px solid var(--accent2);
    padding: 0.7rem 1rem;
    margin: 0.8rem 0;
    border-radius: 0 6px 6px 0;
    font-size: 0.9rem;
    color: var(--muted);
  }
  .shell {
    background: #0a0f1a;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem 1.3rem;
    font-family: monospace;
    font-size: 0.85rem;
    color: #86efac;
    margin: 0.8rem 0;
  }
  .shell .prompt { color: #64748b; user-select: none; }
</style>
</head>
<body>
<div class="page">

<header>
  <h1>💥 Exploding Kittens — Agent Protocol</h1>
  <p>Build an agent in any language. Your process speaks HTTP/JSON; the game engine calls you.</p>
</header>

<h2>Overview</h2>
<p>
  Each agent runs as a separate HTTP server. The game engine calls your endpoints with JSON payloads and
  expects JSON responses. You never need to know about the other agents or the engine internals —
  just respond to the calls. <strong>2–5 players</strong> are supported; player IDs are <code>0</code> through <code>n-1</code> and play in that order.
</p>

<div class="shell">
  <span class="prompt">$ </span>python agents/agent_server.py --agent heuristic --port 5001 --name "MyBot"<br>
  <span class="prompt">$ </span>python simulation/controller.py --games 100 --agents heuristic random heuristic random
</div>

<h2>Turn Lifecycle</h2>
<p>Each turn the engine calls your server in this order:</p>
<ol style="padding-left:1.4rem;color:var(--muted);line-height:2">
  <li><code>/choose_action</code> — you pick a card to play (or <code>DRAW</code> to end your play phase)</li>
  <li>For every other alive player: <code>/want_to_nope</code> — they decide whether to cancel your action</li>
  <li>If the action was played: effect resolves. For <code>PLAY_SEE_THE_FUTURE</code>, your <code>/see_future</code> is called immediately after.</li>
  <li>Steps 1–3 repeat until you return <code>DRAW</code>, or your turn ends early (ATTACK/SKIP)</li>
  <li>On <code>DRAW</code>: you draw a card. If it's an Exploding Kitten and you have a Defuse, <code>/place_exploding_kitten</code> is called.</li>
</ol>
<p>The <code>/want_to_nope</code> loop repeats in rounds (all alive players asked, including you) until a full round passes with nobody playing a Nope. Each Nope flips whether the action is cancelled.</p>

<h2>Endpoints</h2>

<div class="endpoint">
  <h3><span class="method get">GET</span><span class="path">/health</span></h3>
  <p>Health check. Called before any game starts. Must return <code>200 OK</code>.</p>
  <pre><span class="cmt">// response</span>
{ <span class="key">"status"</span>: <span class="str">"ok"</span>, <span class="key">"name"</span>: <span class="str">"MyBot"</span> }</pre>
</div>

<div class="endpoint">
  <h3><span class="method post">POST</span><span class="path">/game_start</span></h3>
  <p>Called once at the start of each game with your initial hand. Use it to reset any per-game state.</p>
  <pre><span class="cmt">// request — you are player 1, starting hand of 8 cards</span>
{
  <span class="key">"state"</span>: {
    <span class="key">"my_id"</span>: <span class="num">1</span>,
    <span class="key">"my_hand"</span>: [
      { <span class="key">"card_type"</span>: <span class="str">"DEFUSE"</span> },
      { <span class="key">"card_type"</span>: <span class="str">"ATTACK"</span> },
      { <span class="key">"card_type"</span>: <span class="str">"SEE_THE_FUTURE"</span> },
      { <span class="key">"card_type"</span>: <span class="str">"NOPE"</span> },
      { <span class="key">"card_type"</span>: <span class="str">"TACO_CAT"</span> },
      { <span class="key">"card_type"</span>: <span class="str">"TACO_CAT"</span> },
      { <span class="key">"card_type"</span>: <span class="str">"SKIP"</span> },
      { <span class="key">"card_type"</span>: <span class="str">"FAVOR"</span> }
    ],
    <span class="key">"hand_sizes"</span>: { <span class="str">"0"</span>: <span class="num">8</span>, <span class="str">"1"</span>: <span class="num">8</span>, <span class="str">"2"</span>: <span class="num">8</span>, <span class="str">"3"</span>: <span class="num">8</span> },
    <span class="key">"alive_players"</span>: [<span class="num">0</span>, <span class="num">1</span>, <span class="num">2</span>, <span class="num">3</span>],
    <span class="key">"deck_size"</span>: <span class="num">26</span>,
    <span class="key">"discard_pile"</span>: [],
    <span class="key">"turns_remaining"</span>: <span class="num">1</span>,
    <span class="key">"current_player"</span>: <span class="num">0</span>,
    <span class="key">"known_top3"</span>: <span class="null">null</span>
  }
}</pre>
  <pre><span class="cmt">// response</span>
{}</pre>
</div>

<div class="endpoint">
  <h3><span class="method post">POST</span><span class="path">/choose_action</span></h3>
  <p>
    Called on your turn. Return one of the <code>valid_actions</code> — the engine only offers actions you can legally play right now.
    Returning <code>DRAW</code> ends your play phase and draws a card.
    <strong>You can play multiple cards per turn</strong> — this is called in a loop until you return <code>DRAW</code> or your turn ends.
  </p>
  <pre><span class="cmt">// request — it's your turn (my_id == current_player)</span>
{
  <span class="key">"state"</span>: {
    <span class="key">"my_id"</span>: <span class="num">1</span>,
    <span class="key">"my_hand"</span>: [
      { <span class="key">"card_type"</span>: <span class="str">"DEFUSE"</span> }, { <span class="key">"card_type"</span>: <span class="str">"ATTACK"</span> },
      { <span class="key">"card_type"</span>: <span class="str">"SEE_THE_FUTURE"</span> }, { <span class="key">"card_type"</span>: <span class="str">"NOPE"</span> },
      { <span class="key">"card_type"</span>: <span class="str">"TACO_CAT"</span> }, { <span class="key">"card_type"</span>: <span class="str">"TACO_CAT"</span> },
      { <span class="key">"card_type"</span>: <span class="str">"SKIP"</span> }, { <span class="key">"card_type"</span>: <span class="str">"FAVOR"</span> }
    ],
    <span class="key">"hand_sizes"</span>: { <span class="str">"0"</span>: <span class="num">7</span>, <span class="str">"1"</span>: <span class="num">8</span>, <span class="str">"2"</span>: <span class="num">6</span>, <span class="str">"3"</span>: <span class="num">9</span> },
    <span class="key">"alive_players"</span>: [<span class="num">0</span>, <span class="num">1</span>, <span class="num">2</span>, <span class="num">3</span>],
    <span class="key">"deck_size"</span>: <span class="num">18</span>,
    <span class="key">"discard_pile"</span>: [{ <span class="key">"card_type"</span>: <span class="str">"SKIP"</span> }],
    <span class="key">"turns_remaining"</span>: <span class="num">1</span>,
    <span class="key">"current_player"</span>: <span class="num">1</span>,
    <span class="key">"known_top3"</span>: <span class="null">null</span>
  },
  <span class="key">"valid_actions"</span>: [
    { <span class="key">"action_type"</span>: <span class="str">"DRAW"</span>, <span class="key">"target_player"</span>: <span class="null">null</span>, <span class="key">"cat_type"</span>: <span class="null">null</span>, <span class="key">"named_card"</span>: <span class="null">null</span>, <span class="key">"defuse_position"</span>: <span class="null">null</span> },
    { <span class="key">"action_type"</span>: <span class="str">"PLAY_ATTACK"</span>, <span class="key">"target_player"</span>: <span class="null">null</span>, <span class="key">"cat_type"</span>: <span class="null">null</span>, <span class="key">"named_card"</span>: <span class="null">null</span>, <span class="key">"defuse_position"</span>: <span class="null">null</span> },
    { <span class="key">"action_type"</span>: <span class="str">"PLAY_SKIP"</span>, <span class="key">"target_player"</span>: <span class="null">null</span>, <span class="key">"cat_type"</span>: <span class="null">null</span>, <span class="key">"named_card"</span>: <span class="null">null</span>, <span class="key">"defuse_position"</span>: <span class="null">null</span> },
    { <span class="key">"action_type"</span>: <span class="str">"PLAY_SEE_THE_FUTURE"</span>, <span class="key">"target_player"</span>: <span class="null">null</span>, <span class="key">"cat_type"</span>: <span class="null">null</span>, <span class="key">"named_card"</span>: <span class="null">null</span>, <span class="key">"defuse_position"</span>: <span class="null">null</span> },
    { <span class="key">"action_type"</span>: <span class="str">"PLAY_FAVOR"</span>, <span class="key">"target_player"</span>: <span class="num">0</span>, <span class="key">"cat_type"</span>: <span class="null">null</span>, <span class="key">"named_card"</span>: <span class="null">null</span>, <span class="key">"defuse_position"</span>: <span class="null">null</span> },
    { <span class="key">"action_type"</span>: <span class="str">"PLAY_FAVOR"</span>, <span class="key">"target_player"</span>: <span class="num">2</span>, <span class="key">"cat_type"</span>: <span class="null">null</span>, <span class="key">"named_card"</span>: <span class="null">null</span>, <span class="key">"defuse_position"</span>: <span class="null">null</span> },
    { <span class="key">"action_type"</span>: <span class="str">"PLAY_FAVOR"</span>, <span class="key">"target_player"</span>: <span class="num">3</span>, <span class="key">"cat_type"</span>: <span class="null">null</span>, <span class="key">"named_card"</span>: <span class="null">null</span>, <span class="key">"defuse_position"</span>: <span class="null">null</span> },
    { <span class="key">"action_type"</span>: <span class="str">"PLAY_CAT_PAIR"</span>, <span class="key">"target_player"</span>: <span class="num">0</span>, <span class="key">"cat_type"</span>: <span class="str">"TACO_CAT"</span>, <span class="key">"named_card"</span>: <span class="null">null</span>, <span class="key">"defuse_position"</span>: <span class="null">null</span> },
    { <span class="key">"action_type"</span>: <span class="str">"PLAY_CAT_PAIR"</span>, <span class="key">"target_player"</span>: <span class="num">2</span>, <span class="key">"cat_type"</span>: <span class="str">"TACO_CAT"</span>, <span class="key">"named_card"</span>: <span class="null">null</span>, <span class="key">"defuse_position"</span>: <span class="null">null</span> },
    { <span class="key">"action_type"</span>: <span class="str">"PLAY_CAT_PAIR"</span>, <span class="key">"target_player"</span>: <span class="num">3</span>, <span class="key">"cat_type"</span>: <span class="str">"TACO_CAT"</span>, <span class="key">"named_card"</span>: <span class="null">null</span>, <span class="key">"defuse_position"</span>: <span class="null">null</span> }
  ]
}</pre>
  <pre><span class="cmt">// response — play See the Future</span>
{ <span class="key">"action_type"</span>: <span class="str">"PLAY_SEE_THE_FUTURE"</span>, <span class="key">"target_player"</span>: <span class="null">null</span>, <span class="key">"cat_type"</span>: <span class="null">null</span>, <span class="key">"named_card"</span>: <span class="null">null</span>, <span class="key">"defuse_position"</span>: <span class="null">null</span> }</pre>
  <p style="margin-top:0.6rem">After that resolves, <code>/choose_action</code> is called again. This time you might return <code>DRAW</code> to end your turn, or play another card.</p>
  <div class="note">If you return an action not in <code>valid_actions</code>, the engine silently substitutes <code>DRAW</code>.</div>
</div>

<div class="endpoint">
  <h3><span class="method post">POST</span><span class="path">/want_to_nope</span> <span class="tag">called for every alive player</span></h3>
  <p>
    Called for every alive player whenever any card is played — including during counter-Nope chains.
    Return <code>true</code> to spend one Nope card from your hand.
  </p>
  <p>
    <strong><code>currently_noped: false</code></strong> → the action is live. Returning <code>true</code> cancels it.<br>
    <strong><code>currently_noped: true</code></strong> → the action is already cancelled. Returning <code>true</code> is a <strong>counter-Nope</strong> — it restores the action.
  </p>
  <p>The engine loops in rounds (all alive players, including the actor) until nobody plays a Nope. Each <code>true</code> costs one Nope card.</p>
  <pre><span class="cmt">// request — player 2 played ATTACK; you are player 3, you hold a Nope</span>
{
  <span class="key">"state"</span>: {
    <span class="key">"my_id"</span>: <span class="num">3</span>,
    <span class="key">"my_hand"</span>: [
      { <span class="key">"card_type"</span>: <span class="str">"NOPE"</span> }, { <span class="key">"card_type"</span>: <span class="str">"DEFUSE"</span> }, { <span class="key">"card_type"</span>: <span class="str">"SKIP"</span> }
    ],
    <span class="key">"hand_sizes"</span>: { <span class="str">"0"</span>: <span class="num">6</span>, <span class="str">"1"</span>: <span class="num">5</span>, <span class="str">"2"</span>: <span class="num">7</span>, <span class="str">"3"</span>: <span class="num">3</span> },
    <span class="key">"alive_players"</span>: [<span class="num">0</span>, <span class="num">1</span>, <span class="num">2</span>, <span class="num">3</span>],
    <span class="key">"deck_size"</span>: <span class="num">12</span>,
    <span class="key">"discard_pile"</span>: [{ <span class="key">"card_type"</span>: <span class="str">"SKIP"</span> }],
    <span class="key">"turns_remaining"</span>: <span class="num">1</span>,
    <span class="key">"current_player"</span>: <span class="num">2</span>,
    <span class="key">"known_top3"</span>: <span class="null">null</span>
  },
  <span class="key">"action"</span>: {
    <span class="key">"action_type"</span>: <span class="str">"PLAY_ATTACK"</span>, <span class="key">"target_player"</span>: <span class="null">null</span>,
    <span class="key">"cat_type"</span>: <span class="null">null</span>, <span class="key">"named_card"</span>: <span class="null">null</span>, <span class="key">"defuse_position"</span>: <span class="null">null</span>
  },
  <span class="key">"currently_noped"</span>: <span class="null">false</span>
}</pre>
  <pre><span class="cmt">// response — yes, Nope it</span>
{ <span class="key">"nope"</span>: <span class="null">true</span> }</pre>
  <pre><span class="cmt">// response — no, let it through</span>
{ <span class="key">"nope"</span>: <span class="null">false</span> }</pre>
  <div class="note">Only called if you are alive. Eliminated players are never asked.</div>
</div>

<div class="endpoint">
  <h3><span class="method post">POST</span><span class="path">/give_card</span></h3>
  <p>Called when a Favor targets you. Return any <code>card_type</code> from your hand. If you return a type you don't hold, the engine picks for you.</p>
  <pre><span class="cmt">// request — player 0 played Favor targeting you</span>
{
  <span class="key">"state"</span>: {
    <span class="key">"my_id"</span>: <span class="num">2</span>,
    <span class="key">"my_hand"</span>: [
      { <span class="key">"card_type"</span>: <span class="str">"DEFUSE"</span> }, { <span class="key">"card_type"</span>: <span class="str">"SKIP"</span> }, { <span class="key">"card_type"</span>: <span class="str">"RAINBOW_CAT"</span> }
    ],
    <span class="key">"hand_sizes"</span>: { <span class="str">"0"</span>: <span class="num">7</span>, <span class="str">"1"</span>: <span class="num">5</span>, <span class="str">"2"</span>: <span class="num">3</span>, <span class="str">"3"</span>: <span class="num">4</span> },
    <span class="key">"alive_players"</span>: [<span class="num">0</span>, <span class="num">1</span>, <span class="num">2</span>, <span class="num">3</span>],
    <span class="key">"deck_size"</span>: <span class="num">9</span>, <span class="key">"discard_pile"</span>: [], <span class="key">"turns_remaining"</span>: <span class="num">1</span>,
    <span class="key">"current_player"</span>: <span class="num">0</span>, <span class="key">"known_top3"</span>: <span class="null">null</span>
  },
  <span class="key">"requester_id"</span>: <span class="num">0</span>
}</pre>
  <pre><span class="cmt">// response — give them the Rainbow Cat, keep your Defuse</span>
{ <span class="key">"card_type"</span>: <span class="str">"RAINBOW_CAT"</span> }</pre>
</div>

<div class="endpoint">
  <h3><span class="method post">POST</span><span class="path">/place_exploding_kitten</span></h3>
  <p>Called after you defuse. Return where to reinsert the EK. <code>0</code> = top (next person draws it), <code>deck_size</code> = bottom (safest for you).</p>
  <pre><span class="cmt">// request — deck has 11 cards remaining after the defuse</span>
{
  <span class="key">"state"</span>: { <span class="key">"my_id"</span>: <span class="num">1</span>, <span class="key">"deck_size"</span>: <span class="num">11</span>, <span class="cmt">/* ... */</span> },
  <span class="key">"deck_size"</span>: <span class="num">11</span>
}</pre>
  <pre><span class="cmt">// response — bury it at the bottom</span>
{ <span class="key">"position"</span>: <span class="num">11</span> }</pre>
  <pre><span class="cmt">// response — place it 3rd from top (trap the next player)</span>
{ <span class="key">"position"</span>: <span class="num">2</span> }</pre>
</div>

<div class="endpoint">
  <h3><span class="method post">POST</span><span class="path">/see_future</span></h3>
  <p>Called immediately after your <code>PLAY_SEE_THE_FUTURE</code> resolves. <code>top3[0]</code> is what you'd draw next. Store it and use it in <code>/choose_action</code> to avoid drawing when you know the EK is on top.</p>
  <div class="note"><code>known_top3</code> in ObservableState becomes stale as soon as the deck size changes (cards drawn, shuffled). Don't rely on it across turns.</div>
  <pre><span class="cmt">// request — uh oh, EK is on top</span>
{
  <span class="key">"state"</span>: { <span class="key">"my_id"</span>: <span class="num">0</span>, <span class="cmt">/* ... */</span> },
  <span class="key">"top3"</span>: [
    { <span class="key">"card_type"</span>: <span class="str">"EXPLODING_KITTEN"</span> },
    { <span class="key">"card_type"</span>: <span class="str">"NOPE"</span> },
    { <span class="key">"card_type"</span>: <span class="str">"ATTACK"</span> }
  ]
}</pre>
  <pre><span class="cmt">// response</span>
{}</pre>
</div>

<h2>Shapes</h2>

<h3>Card</h3>
<pre>{ <span class="key">"card_type"</span>: <span class="str">"ATTACK"</span> }</pre>
<p><code>card_type</code> is one of:</p>
<pre><span class="str">"EXPLODING_KITTEN"</span>  <span class="str">"DEFUSE"</span>  <span class="str">"ATTACK"</span>  <span class="str">"SKIP"</span>  <span class="str">"FAVOR"</span>  <span class="str">"SHUFFLE"</span>  <span class="str">"SEE_THE_FUTURE"</span>  <span class="str">"NOPE"</span>
<span class="str">"TACO_CAT"</span>  <span class="str">"HAIRY_POTATO_CAT"</span>  <span class="str">"BEARD_CAT"</span>  <span class="str">"RAINBOW_CAT"</span>  <span class="str">"CATTERMELON"</span></pre>

<h3>Action</h3>
<pre>{
  <span class="key">"action_type"</span>:      <span class="str">"PLAY_ATTACK"</span>,
  <span class="key">"target_player"</span>:   <span class="null">null</span>,        <span class="cmt">// int — required for FAVOR, CAT_PAIR, CAT_TRIPLE</span>
  <span class="key">"cat_type"</span>:        <span class="null">null</span>,        <span class="cmt">// card_type string — required for CAT_PAIR, CAT_TRIPLE</span>
  <span class="key">"named_card"</span>:      <span class="null">null</span>,        <span class="cmt">// card_type string — optional for CAT_TRIPLE</span>
  <span class="key">"defuse_position"</span>: <span class="null">null</span>         <span class="cmt">// unused — EK placement handled by /place_exploding_kitten</span>
}</pre>

<table>
  <thead><tr><th>action_type</th><th>Description</th></tr></thead>
  <tbody>
    <tr><td>DRAW</td><td>End play phase and draw a card</td></tr>
    <tr><td>PLAY_ATTACK</td><td>Skip your draw; next player takes 2 turns (stacks on existing attacks)</td></tr>
    <tr><td>PLAY_SKIP</td><td>End this turn without drawing (uses one of your turns if under attack)</td></tr>
    <tr><td>PLAY_FAVOR</td><td>Force <code>target_player</code> to give you one card of their choice</td></tr>
    <tr><td>PLAY_SHUFFLE</td><td>Shuffle the deck (useful when you know the EK position)</td></tr>
    <tr><td>PLAY_SEE_THE_FUTURE</td><td>Peek at top 3 cards; triggers <code>/see_future</code> on your server</td></tr>
    <tr><td>PLAY_CAT_PAIR</td><td>2 matching cats → steal a <em>random</em> card from <code>target_player</code></td></tr>
    <tr><td>PLAY_CAT_TRIPLE</td><td>3 matching cats → demand <code>named_card</code> from <code>target_player</code>; they must give it if they have it</td></tr>
  </tbody>
</table>

<h3>ObservableState</h3>
<pre>{
  <span class="key">"my_id"</span>:           <span class="num">1</span>,
  <span class="key">"my_hand"</span>:         [ { <span class="key">"card_type"</span>: <span class="str">"DEFUSE"</span> }, { <span class="key">"card_type"</span>: <span class="str">"ATTACK"</span> }, <span class="cmt">/* ... */</span> ],
  <span class="key">"hand_sizes"</span>:      { <span class="str">"0"</span>: <span class="num">7</span>, <span class="str">"1"</span>: <span class="num">8</span>, <span class="str">"2"</span>: <span class="num">5</span>, <span class="str">"3"</span>: <span class="num">9</span> },  <span class="cmt">// keys are strings (JSON limitation)</span>
  <span class="key">"alive_players"</span>:   [ <span class="num">0</span>, <span class="num">1</span>, <span class="num">2</span>, <span class="num">3</span> ],
  <span class="key">"deck_size"</span>:       <span class="num">18</span>,
  <span class="key">"discard_pile"</span>:    [ { <span class="key">"card_type"</span>: <span class="str">"SKIP"</span> }, { <span class="key">"card_type"</span>: <span class="str">"NOPE"</span> } ],
  <span class="key">"turns_remaining"</span>: <span class="num">1</span>,          <span class="cmt">// &gt;1 means you're under an Attack and must take extra turns</span>
  <span class="key">"current_player"</span>:  <span class="num">1</span>,
  <span class="key">"known_top3"</span>:      <span class="null">null</span>        <span class="cmt">// set after you play See the Future; stale after deck changes</span>
}</pre>
<p>Note: <code>hand_sizes</code> keys are always strings (<code>"0"</code>, <code>"1"</code>, etc.) due to JSON object key rules. Parse them as integers if needed.</p>

<h2>Minimal Implementation</h2>
<p>The simplest valid agent: always draw. Implement these endpoints and your agent can compete.</p>
<pre><span class="cmt"># Python — bare minimum agent server</span>
from flask import Flask, request, jsonify
app = Flask(__name__)

@app.get(<span class="str">"/health"</span>)
def health(): return jsonify({<span class="str">"status"</span>: <span class="str">"ok"</span>})

@app.post(<span class="str">"/game_start"</span>)
def game_start(): return jsonify({})

@app.post(<span class="str">"/choose_action"</span>)
def choose_action():
    <span class="cmt"># Always draw immediately — valid_actions always contains DRAW</span>
    return jsonify({<span class="str">"action_type"</span>: <span class="str">"DRAW"</span>, <span class="str">"target_player"</span>: None,
                    <span class="str">"cat_type"</span>: None, <span class="str">"named_card"</span>: None, <span class="str">"defuse_position"</span>: None})

@app.post(<span class="str">"/want_to_nope"</span>)
def want_to_nope(): return jsonify({<span class="str">"nope"</span>: False})

@app.post(<span class="str">"/give_card"</span>)
def give_card():
    hand = request.json[<span class="str">"state"</span>][<span class="str">"my_hand"</span>]
    return jsonify({<span class="str">"card_type"</span>: hand[0][<span class="str">"card_type"</span>]})  <span class="cmt"># give first card</span>

@app.post(<span class="str">"/place_exploding_kitten"</span>)
def place_ek():
    return jsonify({<span class="str">"position"</span>: request.json[<span class="str">"deck_size"</span>]})  <span class="cmt"># bury at bottom</span>

@app.post(<span class="str">"/see_future"</span>)
def see_future(): return jsonify({})

app.run(port=5001)</pre>

<h2>Game Rules Summary</h2>
<ul>
  <li>On your turn, play any number of cards, then end by drawing one card.</li>
  <li>Drawing an <strong>Exploding Kitten</strong> kills you — unless you have a <strong>Defuse</strong>.</li>
  <li>After defusing, you secretly reinsert the EK anywhere in the deck (<code>/place_exploding_kitten</code>).</li>
  <li><strong>Nope</strong> cancels any card except EK/Defuse. Anyone can Nope at any time, and Nopes can be counter-Noped indefinitely — each flip costs one Nope card.</li>
  <li><strong>Attack</strong>: skip your draw and force the next player to take 2 turns. Counter-attacking adds turns rather than resetting.</li>
  <li><strong>Skip</strong>: end this turn without drawing. If you're under an Attack with 2 turns remaining, Skip uses one of them.</li>
  <li><strong>Favor</strong>: another player gives you one card — they choose which one.</li>
  <li><strong>See the Future</strong>: peek at the top 3 cards privately. Triggers <code>/see_future</code> on your server.</li>
  <li><strong>2 matching Cat cards</strong>: steal a <em>random</em> card from any player.</li>
  <li><strong>3 matching Cat cards</strong>: demand a specific card (<code>named_card</code>); the target must give it if they have it.</li>
</ul>

<h2>Running a Distributed Simulation</h2>
<div class="shell">
  <span class="prompt">$ </span>python simulation/controller.py --games 100 --agents heuristic random heuristic random
</div>
<p>
  To plug in your own server, edit <code>simulation/controller.py</code> and add an entry directly to
  <code>run_distributed()</code>'s <code>agent_specs</code> list with your <code>url</code>, <code>name</code>, and omit <code>type</code>
  (the controller only spawns a subprocess when <code>type</code> is present). Or run your server manually
  and point a <code>RemoteAgent</code> at it from Python.
</p>

<h2>Game Log Format</h2>
<p>Pass <code>--log-games N</code> to <code>main.py</code> to log the first N games as JSONL to <code>logs/</code>.</p>
<pre><span class="cmt">// Line 1: simulation metadata</span>
{ <span class="key">"type"</span>: <span class="str">"simulation"</span>, <span class="key">"n_games"</span>: <span class="num">1000</span>, <span class="key">"seed"</span>: <span class="num">42</span>,
  <span class="key">"players"</span>: [{ <span class="key">"id"</span>: <span class="num">0</span>, <span class="key">"name"</span>: <span class="str">"Heuristic-0"</span>, <span class="key">"agent_type"</span>: <span class="str">"HeuristicAgent"</span> }, <span class="cmt">/* ... */</span>] }

<span class="cmt">// Lines 2+: one game record per line</span>
{
  <span class="key">"type"</span>: <span class="str">"game"</span>, <span class="key">"game_id"</span>: <span class="num">0</span>, <span class="key">"seed"</span>: <span class="num">42</span>,
  <span class="key">"winner"</span>: <span class="num">2</span>, <span class="key">"winner_name"</span>: <span class="str">"Heuristic-2"</span>, <span class="key">"turns"</span>: <span class="num">34</span>,
  <span class="key">"elimination_order"</span>: [ <span class="num">1</span>, <span class="num">3</span>, <span class="num">0</span> ],
  <span class="key">"events"</span>: [
    { <span class="key">"turn"</span>: <span class="num">1</span>,  <span class="key">"type"</span>: <span class="str">"turn_start"</span>,  <span class="key">"player"</span>: <span class="num">0</span>, <span class="key">"hand_size"</span>: <span class="num">8</span>, <span class="key">"deck_size"</span>: <span class="num">24</span>, <span class="key">"alive"</span>: [<span class="num">0</span>,<span class="num">1</span>,<span class="num">2</span>,<span class="num">3</span>] },
    { <span class="key">"turn"</span>: <span class="num">1</span>,  <span class="key">"type"</span>: <span class="str">"see_future"</span>, <span class="key">"player"</span>: <span class="num">0</span>, <span class="key">"top3"</span>: [<span class="str">"SKIP"</span>, <span class="str">"ATTACK"</span>, <span class="str">"NOPE"</span>] },
    { <span class="key">"turn"</span>: <span class="num">1</span>,  <span class="key">"type"</span>: <span class="str">"draw"</span>,        <span class="key">"player"</span>: <span class="num">0</span>, <span class="key">"card"</span>: <span class="str">"SKIP"</span> },
    { <span class="key">"turn"</span>: <span class="num">5</span>,  <span class="key">"type"</span>: <span class="str">"attack"</span>,      <span class="key">"player"</span>: <span class="num">1</span>, <span class="key">"target"</span>: <span class="num">2</span>, <span class="key">"turns_imposed"</span>: <span class="num">2</span> },
    { <span class="key">"turn"</span>: <span class="num">5</span>,  <span class="key">"type"</span>: <span class="str">"nope"</span>,        <span class="key">"player"</span>: <span class="num">2</span>, <span class="key">"action_type"</span>: <span class="str">"PLAY_ATTACK"</span>, <span class="key">"result"</span>: <span class="str">"cancelled"</span> },
    { <span class="key">"turn"</span>: <span class="num">5</span>,  <span class="key">"type"</span>: <span class="str">"nope"</span>,        <span class="key">"player"</span>: <span class="num">1</span>, <span class="key">"action_type"</span>: <span class="str">"PLAY_ATTACK"</span>, <span class="key">"result"</span>: <span class="str">"restored"</span> },
    { <span class="key">"turn"</span>: <span class="num">7</span>,  <span class="key">"type"</span>: <span class="str">"cat_steal"</span>,  <span class="key">"player"</span>: <span class="num">0</span>, <span class="key">"from_player"</span>: <span class="num">3</span>, <span class="key">"cat_type"</span>: <span class="str">"TACO_CAT"</span>, <span class="key">"card"</span>: <span class="str">"DEFUSE"</span>, <span class="key">"method"</span>: <span class="str">"pair"</span> },
    { <span class="key">"turn"</span>: <span class="num">12</span>, <span class="key">"type"</span>: <span class="str">"defuse"</span>,      <span class="key">"player"</span>: <span class="num">3</span>, <span class="key">"ek_position"</span>: <span class="num">8</span>, <span class="key">"deck_size"</span>: <span class="num">10</span> },
    { <span class="key">"turn"</span>: <span class="num">18</span>, <span class="key">"type"</span>: <span class="str">"explode"</span>,     <span class="key">"player"</span>: <span class="num">0</span> },
    { <span class="key">"turn"</span>: <span class="num">34</span>, <span class="key">"type"</span>: <span class="str">"game_over"</span>,  <span class="key">"winner"</span>: <span class="num">2</span> }
  ]
}</pre>

<p style="margin-top:3rem;color:#475569;font-size:0.8rem">
  Built with Python · Protocol version 1.0
</p>

</div>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # silence access logs


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Protocol docs running at http://0.0.0.0:{port}", flush=True)
    server.serve_forever()
