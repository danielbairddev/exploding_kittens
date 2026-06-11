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
   class. Improve from there.
2. Benchmark **head-to-head**: put the successor and predecessor in the *same*
   games against a common field and compare win rates (same opponents, rotated
   seats). A successor "wins" only if it beats its predecessor beyond noise.
3. Prefer **A/B-testing individual heuristics**: toggle one idea at a time and
   keep only what measurably helps. Combine the winners.
4. Add it to the arena roster in `dashboard_server.py` (keep the predecessor in
   the pool so the comparison stays live), and bump `SNAPSHOT_PATH`'s version
   suffix since the roster changed.

## Current lineage

- `RandomAgent` (Lucky) — baseline, pure random (protects its Defuse).
- `ChaosAgent` (Gremlin) — fully random, will even give away Defuses.
- `AggressiveAgent` (Maverick) — dumps its whole hand every turn.
- `HeuristicAgent` (Professor) — first attempt at "smart"; underperforms random.
- `SurvivalAgent` (Sly) — survival-first + information + weaponised EK placement.
  Big jump: ~35% in the 5-player arena (20% baseline).
