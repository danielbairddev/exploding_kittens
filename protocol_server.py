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
  just respond to the calls.
</p>

<div class="shell">
  <span class="prompt">$ </span>python agents/agent_server.py --agent heuristic --port 5001 --name "MyBot"<br>
  <span class="prompt">$ </span>python simulation/controller.py --games 100 --agents heuristic random heuristic random
</div>

<h2>Endpoints</h2>

<div class="endpoint">
  <h3><span class="method get">GET</span><span class="path">/health</span></h3>
  <p>Health check. Called before any game starts. Must return <code>200 OK</code>.</p>
  <pre><span class="cmt">// response</span>
{ <span class="key">"status"</span>: <span class="str">"ok"</span>, <span class="key">"name"</span>: <span class="str">"MyBot"</span> }</pre>
</div>

<div class="endpoint">
  <h3><span class="method post">POST</span><span class="path">/game_start</span></h3>
  <p>Called once at the start of each game. Use it to reset per-game state.</p>
  <pre>{ <span class="key">"state"</span>: &lt;ObservableState&gt; }</pre>
  <pre><span class="cmt">// response</span>
{}</pre>
</div>

<div class="endpoint">
  <h3><span class="method post">POST</span><span class="path">/choose_action</span></h3>
  <p>
    Called on your turn. Return one of the provided <code>valid_actions</code>.
    Returning <code>DRAW</code> ends your play phase and draws a card.
    <strong>You can play multiple cards per turn</strong> — this is called repeatedly until you return
    <code>DRAW</code> or your turn ends via ATTACK/SKIP.
  </p>
  <pre>{ <span class="key">"state"</span>: &lt;ObservableState&gt;, <span class="key">"valid_actions"</span>: [ &lt;Action&gt;, ... ] }</pre>
  <pre><span class="cmt">// response — return exactly one Action</span>
{ <span class="key">"action_type"</span>: <span class="str">"PLAY_SEE_THE_FUTURE"</span>, <span class="key">"target_player"</span>: <span class="null">null</span>, <span class="key">"cat_type"</span>: <span class="null">null</span>, <span class="key">"named_card"</span>: <span class="null">null</span>, <span class="key">"defuse_position"</span>: <span class="null">null</span> }</pre>
</div>

<div class="endpoint">
  <h3><span class="method post">POST</span><span class="path">/want_to_nope</span> <span class="tag">called for every player</span></h3>
  <p>
    Called whenever any card is played — including during counter-Nope chains.
    Return <code>true</code> to spend one Nope card from your hand.
  </p>
  <p>
    <strong><code>currently_noped</code></strong>: if <code>true</code>, the action is <em>currently cancelled</em>.
    Returning <code>true</code> here is a <strong>counter-Nope</strong> — it restores the action.
    This is called in rounds until nobody plays a Nope in a full pass. Each <code>true</code> costs one Nope card.
  </p>
  <pre>{
  <span class="key">"state"</span>: &lt;ObservableState&gt;,
  <span class="key">"action"</span>: &lt;Action&gt;,
  <span class="key">"currently_noped"</span>: <span class="null">false</span>
}</pre>
  <pre><span class="cmt">// response</span>
{ <span class="key">"nope"</span>: <span class="null">true</span> }</pre>
</div>

<div class="endpoint">
  <h3><span class="method post">POST</span><span class="path">/give_card</span></h3>
  <p>Called when a Favor targets you. Return a <code>card_type</code> you hold. If you return a card you don't have, the engine picks for you.</p>
  <pre>{ <span class="key">"state"</span>: &lt;ObservableState&gt;, <span class="key">"requester_id"</span>: <span class="num">2</span> }</pre>
  <pre><span class="cmt">// response</span>
{ <span class="key">"card_type"</span>: <span class="str">"SKIP"</span> }</pre>
</div>

<div class="endpoint">
  <h3><span class="method post">POST</span><span class="path">/place_exploding_kitten</span></h3>
  <p>Called after you defuse an Exploding Kitten. Return where to reinsert it. <code>0</code> = top of deck, <code>deck_size</code> = bottom.</p>
  <pre>{ <span class="key">"state"</span>: &lt;ObservableState&gt;, <span class="key">"deck_size"</span>: <span class="num">14</span> }</pre>
  <pre><span class="cmt">// response</span>
{ <span class="key">"position"</span>: <span class="num">14</span> }</pre>
</div>

<div class="endpoint">
  <h3><span class="method post">POST</span><span class="path">/see_future</span></h3>
  <p>Called after you play See the Future. Store <code>top3</code> and use it to decide when to avoid drawing.</p>
  <pre>{
  <span class="key">"state"</span>: &lt;ObservableState&gt;,
  <span class="key">"top3"</span>: [ &lt;Card&gt;, &lt;Card&gt;, &lt;Card&gt; ]
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
  <span class="key">"action_type"</span>:     <span class="str">"PLAY_ATTACK"</span>,
  <span class="key">"target_player"</span>:  <span class="null">null</span>,       <span class="cmt">// int — required for FAVOR, CAT_PAIR, CAT_TRIPLE</span>
  <span class="key">"cat_type"</span>:       <span class="null">null</span>,       <span class="cmt">// card_type string — required for CAT_PAIR, CAT_TRIPLE</span>
  <span class="key">"named_card"</span>:     <span class="null">null</span>,       <span class="cmt">// card_type string — optional for CAT_TRIPLE</span>
  <span class="key">"defuse_position"</span>: <span class="null">null</span>       <span class="cmt">// unused — handled by /place_exploding_kitten</span>
}</pre>

<table>
  <thead><tr><th>action_type</th><th>Description</th></tr></thead>
  <tbody>
    <tr><td>DRAW</td><td>End play phase and draw a card</td></tr>
    <tr><td>PLAY_ATTACK</td><td>Skip your draw; next player takes 2 turns</td></tr>
    <tr><td>PLAY_SKIP</td><td>End this turn without drawing</td></tr>
    <tr><td>PLAY_FAVOR</td><td>Force <code>target_player</code> to give you a card</td></tr>
    <tr><td>PLAY_SHUFFLE</td><td>Shuffle the deck</td></tr>
    <tr><td>PLAY_SEE_THE_FUTURE</td><td>Peek at the top 3 cards (triggers <code>/see_future</code>)</td></tr>
    <tr><td>PLAY_CAT_PAIR</td><td>2 matching cats → steal a random card from <code>target_player</code></td></tr>
    <tr><td>PLAY_CAT_TRIPLE</td><td>3 matching cats → demand <code>named_card</code> from <code>target_player</code></td></tr>
  </tbody>
</table>

<h3>ObservableState</h3>
<pre>{
  <span class="key">"my_id"</span>:           <span class="num">0</span>,
  <span class="key">"my_hand"</span>:         [ &lt;Card&gt;, ... ],   <span class="cmt">// your full hand — only you see this</span>
  <span class="key">"hand_sizes"</span>:      { <span class="str">"0"</span>: <span class="num">7</span>, <span class="str">"1"</span>: <span class="num">5</span>, <span class="str">"2"</span>: <span class="num">6</span> },
  <span class="key">"alive_players"</span>:   [ <span class="num">0</span>, <span class="num">1</span>, <span class="num">2</span> ],
  <span class="key">"deck_size"</span>:       <span class="num">18</span>,
  <span class="key">"discard_pile"</span>:    [ &lt;Card&gt;, ... ],
  <span class="key">"turns_remaining"</span>: <span class="num">1</span>,                  <span class="cmt">// &gt;1 if you're under an Attack</span>
  <span class="key">"current_player"</span>: <span class="num">0</span>,
  <span class="key">"known_top3"</span>:      <span class="null">null</span>               <span class="cmt">// populated after you play See the Future</span>
}</pre>

<h2>Game Rules Summary</h2>
<ul>
  <li>On your turn, play any number of cards, then end by drawing one card.</li>
  <li>Drawing an <strong>Exploding Kitten</strong> kills you — unless you have a <strong>Defuse</strong>.</li>
  <li>After defusing, you secretly reinsert the EK anywhere in the deck (<code>/place_exploding_kitten</code>).</li>
  <li><strong>Nope</strong> cancels any card (except EK/Defuse). Anyone can Nope at any time, and Nopes can be counter-Noped indefinitely — each flip costs one Nope card.</li>
  <li><strong>Attack</strong>: skip your draw and force the next player to take 2 turns. Stacks if they also attack.</li>
  <li><strong>Skip</strong>: end your turn without drawing (counts as one turn).</li>
  <li><strong>Favor</strong>: another player must give you one card of their choice.</li>
  <li><strong>See the Future</strong>: peek at the top 3 cards. Your agent receives them via <code>/see_future</code>.</li>
  <li><strong>2 matching Cat cards</strong>: steal a random card from any player.</li>
  <li><strong>3 matching Cat cards</strong>: demand a specific card by name (<code>named_card</code>); if they have it, they must give it.</li>
</ul>

<h2>Running a Distributed Simulation</h2>
<div class="shell">
  <span class="prompt">$ </span>python simulation/controller.py --games 100 --agents heuristic random heuristic random
</div>
<p>
  To connect your own agent server, run it on any port and modify the <code>agent_specs</code> list
  in <code>simulation/controller.py</code> with your <code>url</code> and <code>name</code>.
</p>

<h2>Game Log Format</h2>
<p>Pass <code>--log-games N</code> to log the first N games as JSONL to the <code>logs/</code> folder.</p>
<pre><span class="cmt">// Line 1: simulation metadata</span>
{ <span class="key">"type"</span>: <span class="str">"simulation"</span>, <span class="key">"n_games"</span>: <span class="num">1000</span>, <span class="key">"players"</span>: [...] }

<span class="cmt">// Lines 2+: one game per line</span>
{
  <span class="key">"type"</span>: <span class="str">"game"</span>, <span class="key">"game_id"</span>: <span class="num">0</span>, <span class="key">"winner"</span>: <span class="num">2</span>, <span class="key">"winner_name"</span>: <span class="str">"Heuristic-2"</span>, <span class="key">"turns"</span>: <span class="num">34</span>,
  <span class="key">"elimination_order"</span>: [ <span class="num">1</span>, <span class="num">3</span>, <span class="num">0</span> ],
  <span class="key">"events"</span>: [
    { <span class="key">"turn"</span>: <span class="num">1</span>, <span class="key">"type"</span>: <span class="str">"turn_start"</span>, <span class="key">"player"</span>: <span class="num">0</span>, <span class="key">"hand_size"</span>: <span class="num">8</span>, <span class="key">"deck_size"</span>: <span class="num">24</span>, <span class="key">"alive"</span>: [<span class="num">0</span>,<span class="num">1</span>,<span class="num">2</span>,<span class="num">3</span>] },
    { <span class="key">"turn"</span>: <span class="num">1</span>, <span class="key">"type"</span>: <span class="str">"see_future"</span>, <span class="key">"player"</span>: <span class="num">0</span>, <span class="key">"top3"</span>: [<span class="str">"SKIP"</span>, <span class="str">"ATTACK"</span>, <span class="str">"NOPE"</span>] },
    { <span class="key">"turn"</span>: <span class="num">1</span>, <span class="key">"type"</span>: <span class="str">"draw"</span>, <span class="key">"player"</span>: <span class="num">0</span>, <span class="key">"card"</span>: <span class="str">"SKIP"</span> },
    { <span class="key">"turn"</span>: <span class="num">5</span>, <span class="key">"type"</span>: <span class="str">"attack"</span>, <span class="key">"player"</span>: <span class="num">1</span>, <span class="key">"target"</span>: <span class="num">2</span>, <span class="key">"turns_imposed"</span>: <span class="num">2</span> },
    { <span class="key">"turn"</span>: <span class="num">5</span>, <span class="key">"type"</span>: <span class="str">"nope"</span>, <span class="key">"player"</span>: <span class="num">2</span>, <span class="key">"action_type"</span>: <span class="str">"PLAY_ATTACK"</span>, <span class="key">"result"</span>: <span class="str">"cancelled"</span> },
    { <span class="key">"turn"</span>: <span class="num">5</span>, <span class="key">"type"</span>: <span class="str">"nope"</span>, <span class="key">"player"</span>: <span class="num">1</span>, <span class="key">"action_type"</span>: <span class="str">"PLAY_ATTACK"</span>, <span class="key">"result"</span>: <span class="str">"restored"</span> },
    { <span class="key">"turn"</span>: <span class="num">12</span>, <span class="key">"type"</span>: <span class="str">"defuse"</span>, <span class="key">"player"</span>: <span class="num">3</span>, <span class="key">"ek_position"</span>: <span class="num">8</span>, <span class="key">"deck_size"</span>: <span class="num">10</span> },
    { <span class="key">"turn"</span>: <span class="num">18</span>, <span class="key">"type"</span>: <span class="str">"explode"</span>, <span class="key">"player"</span>: <span class="num">0</span> },
    { <span class="key">"turn"</span>: <span class="num">34</span>, <span class="key">"type"</span>: <span class="str">"game_over"</span>, <span class="key">"winner"</span>: <span class="num">2</span> }
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
