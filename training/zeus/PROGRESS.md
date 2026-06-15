# Zeus — autonomous goal: beat Elephant

**GOAL (standing):** make Zeus's win rate **> Elephant** vs the live arena roster.
When training stalls, do NOT stop — diagnose and apply the next lever, relaunch, repeat.

## The bar (measured under identical conditions)

Greedy, vs 4 distinct opponents drawn from the live arena roster (`/tmp/compare_zeus_elephant.py`, n=2500):

| Bot | win rate |
|---|---|
| **Elephant** | **45.3%** ← the bar to beat |
| Zeus (start of goal) | 24.3% |

Zeus's `training/zeus/train.py` eval (`evaluate()` vs the 18-bot arena roster, 4 distinct
opponents, greedy) uses the SAME conditions, so its reported `win %` is directly
comparable to the 45.3% bar. `--target_winrate 0.46` = "beat Elephant".

## Intervention ladder (try in order when a run stalls)

1. ✅ Arena-mirror eval (was strong-4-only) + re-annealed entropy 0.03→0.01/1500 — current.
2. **More data per update**: `--games 192` (lower-variance PPO gradients).
3. **Face the bar more**: weight the training FLEET harder toward the strongest winners
   (Coyote/Rhino/Elephant/Sly2) — Zeus trains *against* Elephant, so meeting it more often
   sharpens the matchup.
4. **Self-play up**: once Zeus clears ~35%, raise `--self_prob` 0.3→0.5 to push the ceiling.
5. **Optimizer**: try `--lr 2e-4` (faster escape) or `--epochs 2` (more updates/sample).
6. **Longer context / capacity**: only if data-side levers stall — bigger trunk or more layers
   (architecture change; gradcheck again).
7. **Reward**: optional mild place-head survival shaping, or reward = finishing position
   (not just sole-survivor) for a denser signal.

Do NOT add loser/anti-agent bots (Gabriel/Orpheus/Perdition2/Hades) to the TRAINING fleet:
they throw games, giving a win-maximiser trivial +1s and a corrupted gradient. They stay in
the EVAL only (to mirror the leaderboard).

## Run log

| round | config | result (best win % vs roster) | note |
|------|--------|------------------------------|------|
| 1 | smoke | ~11–24% | strong-4 eval undersold it |
| 2 | re-anneal ent, arena eval, games 128 | ~24% (iter ~80) | exploration revived |
| 3 | + games 192, target 0.46 | ~41% (true ~38-40%) | big jump from re-anneal |
| 4 | fleet reweight (strong x3) + self_prob 0.45 | ~40% (noise) | stalled, no real gain |
| 5 | games 256 + epochs 2 | ~40% (noise) | stalled, no real gain |
| 6 | **dense finishing-rank reward** (eval still pure win%) | _running_ | break the ~40% plateau |

## How the loop runs

`run_full_training.sh` / direct `train.py` self-stops on target (0.46), patience stall, or
iter cap. A background watcher (`pgrep -f '[-]m training.zeus.train'`, self-excluding) pings
me on exit; I then: (a) re-measure vs Elephant, (b) if > Elephant → deploy (commit weights,
un-bench ZeusAgent, bump stats), else (c) apply the next ladder item and relaunch.
