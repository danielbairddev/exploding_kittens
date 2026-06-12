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

2. Append the class to `ARENA_BOTS` in `dashboard_server.py` (don't reorder — bot_ids are positional).

## Bot lineage

- **Random → Heuristic → Aggressive → Chaos** — baselines and early experiments.
- **Survival → SurvivalV2 (Sly → Sly2)** — survival-first; V2 adds relentless stealing.
- **Coyote** — best rule-based; adds card counting, conditional Noping, hand-size targeting.
- **Orangutan** — MLP trained by behavioural cloning of Coyote. Weights in `agents/orangutan_weights.json`.
- **Orangutan2** — same MLP, PPO-retrained against the full current fleet. Weights auto-updated by `gorilla/train.py`.
- **Perdition / Perdition2** — inverted-reward PPO; trained to lose. Self-sabotage hooks hard-coded.

## Open follow-ups

- **Event-log features / recurrent architecture.** `state.recent_events` gives a full public action history. Encoding it (per-player defuse/attack counts, etc.) into the feature vector is the cheapest next win. A GRU would go further for opponent modelling.
- **Train separate heads for `want_to_nope`, `give_card`, `place_exploding_kitten`.** Currently all heuristic even in the NN bots.
- **Re-run Gorilla opponent-modelling A/B.** Original run used `want_to_nope` tracking which missed most plays. Rebuild on `state.recent_events` and re-benchmark.
