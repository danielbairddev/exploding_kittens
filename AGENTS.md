# Agents — how we evolve strategies

## Golden rule: add a new bot, don't edit the old one

When improving a strategy, **almost always create a new agent class/file rather
than editing an existing one.** Name it as a successor (e.g. `Sly` → `Sly2`).

Why:
- **Measurable progress.** Keeping the old bot lets us pit successor vs
  predecessor head-to-head and prove the new one is actually better, not just
  different.
- **No silent regressions.** Editing a deployed bot can quietly make it worse;
  a separate bot makes every change an explicit, benchmarked A/B.
- **A living leaderboard.** Over time the arena becomes a history of our ideas,
  each generation visibly beating (or failing to beat) the last.

Exceptions (fine to edit in place): pure bug fixes, crashes, or protocol/compat
changes that don't alter strategy.

## How to add a successor

1. Copy the predecessor into a new file (`agents/<name>_agent.py`) and a new
   class. Improve from there. Give the class an `ARENA` dict with its display
   metadata so the bot file is self-contained:

   ```python
   class MyBotAgent(SurvivalAgentV2):
       ARENA = {"name": "MyBot", "emoji": "🤖", "color": "#22d3ee",
                "blurb": "One-line strategy.", "author": "Your Name"}
   ```
2. Benchmark **head-to-head**: put the successor and predecessor in the *same*
   games against a common field and compare win rates (same opponents, rotated
   seats). A successor "wins" only if it beats its predecessor beyond noise.
3. Prefer **A/B-testing individual heuristics**: toggle one idea at a time and
   keep only what measurably helps. Combine the winners.
4. Append your class to `ARENA_BOTS` in `dashboard_server.py` (keep the
   predecessor in the pool so the comparison stays live), and bump
   `SNAPSHOT_PATH`'s version suffix since the roster changed. The roster reads
   name/emoji/color/blurb/author straight from your class's `ARENA` dict.
5. Set `author` in your `ARENA` dict. Every bot is attributed to a human so we
   can credit the best bots to whoever built them — it shows on the live
   leaderboard.

## Current lineage

- `RandomAgent` (Lucky) — baseline, pure random (protects its Defuse).
- `ChaosAgent` (Gremlin) — fully random, will even give away Defuses.
- `AggressiveAgent` (Maverick) — dumps its whole hand every turn.
- `HeuristicAgent` (Professor) — first attempt at "smart"; underperforms random.
- `SurvivalAgent` (Sly) — survival-first + information + weaponised EK placement.
  Big jump: ~35% in the 5-player arena (20% baseline).
- `SurvivalAgentV2` (Sly2) — Sly + relentless stealing (always play cat pairs +
  proactive Favor), See-the-Future conserved, last Defuse protected. A/B-tested
  vs Sly: ~36% vs ~28% in the 6-bot pool (+7.7pts head-to-head). Aggressive
  ideas (attack-to-kill, endgame attacking) were benchmarked and dropped — they
  hurt; the edge is economy, not offense.
- `CoyoteAgent` (Coyote) — Sly2 + card counting off the discard pile. Holds its
  Attack when the next player likely has one (would bounce back); only
  counter-Nopes when opponents almost certainly can't re-Nope; doesn't feed cats
  on Favor; protects up to two Defuses. Narrow but real winner: +0.65pts vs Sly2
  head-to-head, #1 in the 7-bot pool (~31.8% vs 31.0%). Stealing-from-small-hands
  and snipe-attacking were tested and dropped.
- `OrangutanAgent` (Orangutan) — neural net (35→64→32→8 MLP) picks the action
  type; other endpoints inherited from Coyote. Trained by behavioral cloning of
  Coyote over ~580k decisions (99.7% action-match), reaching ~28% win / 2.62
  place vs the fleet — i.e. it matches the top heuristics through a learned
  policy. REINFORCE finetuning was tried and *degraded* it (drifts off the BC
  optimum), so we ship the BC weights. Inference is pure-Python (weights in
  agents/orangutan_weights.json); training is train_orangutan.py (numpy).
  (Display blurb is deliberately uninformative.)

## Open follow-ups (TODO)

- **Re-run opponent modeling with complete data.** `GameTracker` built opponent
  profiles from `want_to_nope`, but the engine only calls that for players
  *holding a Nope* (`if not player.has(NOPE): continue`) — so the tracker missed
  most plays and the Gorilla opponent-modeling A/B was handicapped (its ~40% tie
  is suspect). Kaushal's `state.recent_events` now gives the complete public
  action log; rebuild the tracker on top of it and re-run the A/B fairly.
  (Details in `gorilla/PROGRESS.md`; tracked as a task.)
