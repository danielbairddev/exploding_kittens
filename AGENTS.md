# Agents

## Golden rule: add a new bot, don't edit the old one

When improving a strategy, create a new agent class/file rather than editing an
existing one. Name it as a successor (e.g. `Sly` → `Sly2`). Keeping the old
bot lets us prove the new one is actually better, not just different.

Exceptions: bug fixes, crashes, protocol/compat changes that don't alter strategy.

## How to add a bot

1. Create `agents/<name>_agent.py` with a class and an `ARENA` dict:

   ```python
   class MyBotAgent(CoyoteAgent):
       ARENA = {
           "name": "MyBot",
           "emoji": "🤖",
           "color": "#22d3ee",
           "blurb": "One-liner.",
           "author": "Your Name",
           "llm_assisted": False,   # True if weights/logic were LLM-assisted
           "stats_version": 1,      # bump to reset this bot's leaderboard stats on next deploy
       }
   ```

2. Append the class to `ARENA_BOTS` in `web/dashboard_server.py` (don't reorder — bot_ids are positional).

## Bot lineage

- `RandomAgent` (Lucky) — baseline, pure random.
- `ChaosAgent` (Gremlin) — fully random, will give away Defuses.
- `AggressiveAgent` (Maverick) — dumps its whole hand every turn.
- `HeuristicAgent` (Professor) — first attempt at "smart"; underperforms random.
- `SurvivalAgent` (Sly) — survival-first + information + weaponised EK placement. Big jump: ~35% in the 5-player arena (20% baseline).
- `SurvivalAgentV2` (Sly2) — Sly + relentless stealing (always play cat pairs + proactive Favor), See-the-Future conserved, last Defuse protected. A/B-tested vs Sly: ~36% vs ~28% in the 6-bot pool (+7.7pts head-to-head).
- `CoyoteAgent` (Coyote) — Sly2 + card counting off the discard pile. Holds its Attack when the next player likely has one; only counter-Nopes when opponents almost certainly can't re-Nope; protects up to two Defuses. +0.65pts vs Sly2 head-to-head.
- `OrangutanAgent` (Orangutan) — MLP (52→64→32→8) picks the action type; other endpoints inherited from Coyote. Trained by behavioural cloning of Coyote. Weights in `agents/orangutan_weights.json`.
- `Orangutan2Agent` (Orangutan2) — same MLP as Orangutan, PPO-retrained (Gorilla pipeline) against the full current fleet. Weights auto-updated by `training/gorilla/train.py` on every new best.
- `PerditionAgent` (Perdition) — same MLP as Orangutan but trained with inverted reward to minimise win rate. Self-sabotage hooks hard-coded. Frozen at ~4.43% win rate.
- `Perdition2Agent` (Perdition2) — continuation of Perdition training, fresh PPO run. Weights in `agents/perdition2_weights.json`.
- `RhinoAgent` (Rhino) — GRU(39→64) processes the full public event log; hidden state concatenated with snapshot features (52) and fed to MLP (116→64→32→8). Trained with PPO + BPTT in `training/rhino/`. Weights auto-updated by `training/rhino/train.py`.

## Open follow-ups

- **Event-log features / recurrent architecture.** `state.recent_events` gives a full public action history. Encoding it (per-player defuse/attack counts, etc.) into the feature vector is the cheapest next win. A GRU would go further for opponent modelling.
- **Train separate heads for `want_to_nope`, `give_card`, `place_exploding_kitten`.** Currently all heuristic even in the NN bots.
- **Re-run Gorilla opponent-modelling A/B.** Original run used `want_to_nope` tracking which missed most plays. Rebuild on `state.recent_events` and re-benchmark.
