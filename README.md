# Exploding Kittens Bot Arena

The card game Exploding Kittens, rebuilt as an online arena where bots play each other over and over. A pure-Python game engine runs continuous simulations, a live dashboard shows the leaderboard, and anyone can add a bot — from a few `if` statements to a PPO-trained neural net — and watch how it stacks up.

## Quickstart

No dependencies needed for the engine or arena (`numpy` and `psutil` are only used for training — see `requirements.txt`).

```bash
# Run 1000 games with 4 random bots
python3 main.py --agent Lucky

# Watch a single game move by move
python3 main.py --agent Coyote --verbose

# Pit any arena bot against itself (see --help for all names)
python3 main.py --agent Rhino --games 5000 --players 5
```

Start the live arena dashboard (leaderboard + continuous simulation):

```bash
python3 web/dashboard_server.py 8767
```

Then open http://localhost:8767. The same server hosts a play-vs-bots page at `/play`, with an optional Orangutan coach that scores your moves.

## Skull (second game, port 6767)

The same server binary runs a second game — **Skull** (a.k.a. Skull & Roses), a
bluffing game — when started with the `skulls` argument. It has its own engine
(`skull/`), its own snapshot files, and its own live dashboard with an animated
play-by-play of games in progress. The roster currently holds a single baseline
bot — `RandomSkullAgent` (random legal moves) — for newcomers to beat; add a bot
by appending its class to `SKULL_BOTS` in `web/dashboard_server.py`.

```bash
python3 web/dashboard_server.py 6767 skulls   # Skull arena on its own port
python3 -m skull.run --players 4 --games 5000  # headless simulation + stats
python3 -m skull.run --verbose                 # watch a single game
```

In production both games run side by side: `scripts/arena_restart.sh` launches
Exploding Kittens on `PORT` (8767) and Skull on `PORT2` (6767).

## Adding a bot

The golden rule: **add a new bot, don't edit an old one** — keeping the old bot proves the new one is actually better. See `AGENTS.md` for the full guide and the lineage of every bot in the arena, from `Lucky` (pure random) to `Rhino` (GRU over the public event log).

In short: create `agents/<name>_agent.py` with an `ARENA` dict, then append the class to `ARENA_BOTS` in `web/dashboard_server.py`.

Bots can also run as separate processes in any language, speaking HTTP/JSON:

```bash
python3 simulation/controller.py --games 100 --agents heuristic random heuristic random
```

The protocol (endpoints, state schema, valid actions) is documented in `AGENT_PROTOCOL.md` and served as a docs page by `web/protocol_server.py`.

## Repository layout

```
game/        Core EK engine: cards, actions, observable state, rules
agents/      All EK bots + their trained weights, agent HTTP server
skull/       Skull engine (discs, state, actions, engine) + Skull bots
simulation/  In-process runner and multi-process controller
protocol/    JSON schema for the remote-agent protocol
web/         Arena dashboards (EK + Skull), play page, protocol docs server
training/    NN training pipelines (gorilla, rhino, perdition, ...)
scripts/     Deploy and restart scripts for the arena server
main.py      CLI simulation runner
smoke_test.py  Pre-deploy gate: import the stack, play one game
```

## Training

The neural bots are trained by the pipelines in `training/`, each named after the experiment that produced it (`gorilla` = PPO pipeline behind Orangutan2, `rhino` = GRU + PPO/BPTT, `perdition` = inverted-reward sabotage bot, `abaddon`/`mandrill` = follow-up experiments). Trainers write best weights directly into `agents/*_weights.json`, which the deployed agents load with no numpy required at inference time.

```bash
python3 training/train_orangutan.py --batches 4000   # behavioural cloning
python3 training/gorilla/train.py                    # PPO against the fleet
python3 training/train_dashboard.py                  # local training monitor on :7777
```

## Deployment

The arena runs from a git checkout on the server. `scripts/setup_auto_deploy.sh` bootstraps the box; after that, `scripts/auto_deploy.sh` polls `origin/main`, smoke-tests each new commit in a detached worktree, and restarts the dashboard only when the test passes. `scripts/deploy_dashboard.sh` does a guarded manual deploy (it refuses to ship anything not pushed to GitHub).
