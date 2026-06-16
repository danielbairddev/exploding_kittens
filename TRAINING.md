# Training & Deployment Guide

How to train, evaluate, and deploy the ML bots in this arena.

---

## Bots and their training systems

| Bot | Module | Weights file | Algorithm | Architecture |
|-----|--------|-------------|-----------|--------------|
| Orangutan2 | `gorilla/` | `agents/orangutan2_weights.json` | PPO (no BPTT) | MLP 52→64→32→8 |
| Rhino | `rhino/` | `agents/rhino_weights.json` | PPO + BPTT | GRU(64) + Trunk(116→64→32) |
| Elephant | `elephant/` | `agents/elephant_weights.json` | PPO + BPTT | GRU(128) + Trunk(180→128→64) |
| Gabriel | `gabriel/` | `agents/gabriel_weights.json` | PPO + BPTT (inverted reward) | GRU(128) + Trunk(180→128→64) |
| Orpheus | `orpheus/` | `agents/orpheus_weights.json` | PPO + BPTT (inverted reward, losing-fleet) | GRU(128) + Trunk(180→128→64) |
| Hades | `hades/` | `agents/hades_weights.json` | PPO (inverted reward + dense aux, curriculum) | Transformer(3L×4H, d=128) + Trunk(390→256→128) |
| Zeus | `zeus/` | `agents/zeus_weights.json` | PPO (win reward +1/−1, no shaping) | Same as Hades (reused) |

**Orangutan2** uses `gorilla/train.py` (confusingly named — "Gorilla" is the training system, "Orangutan2" is the deployed arena bot).

---

## Starting a training run

### Rhino
```bash
ssh root@162.243.161.27
cd /opt/ek-arena
nohup python3 -m rhino.train --workers 6 >> /tmp/rhino_train.log 2>&1 &
echo $!  # note the PID
```

### Elephant
```bash
nohup python3 -m elephant.train --workers 4 >> /tmp/elephant_train.log 2>&1 &
```

### Orangutan2 (via gorilla)
```bash
nohup python3 -m gorilla.train --workers 6 >> /tmp/gorilla_train.log 2>&1 &
```

### Orpheus (vs Gabriel/Perdition losing-fleet)
```bash
nohup python3 -m ian_folder.orpheus.train --workers 6 >> /tmp/orpheus_train.log 2>&1 &
```
Orpheus is **disabled in the arena** — trained only. Metric is `first-death %` against a fleet of Gabriel+Perdition bots also trying to die. Bootstrapped from Gabriel weights.

### Hades (Transformer anti-agent, vs the loser fleet)
```bash
# Phase 1 — bootstrap: learn to self-destruct vs winner bots
nohup python3 -m ian_folder.hades.train --phase bootstrap --iters 100 --workers 6 >> /tmp/hades_train.log 2>&1 &
# Phase 2 — crucible: out-lose the losers (auto-switches after --bootstrap_iters)
nohup python3 -m ian_folder.hades.train --resume --workers 6 >> /tmp/hades_train.log 2>&1 &
```
### Zeus (Transformer, win-maximising twin of Hades)
```bash
# full unattended run vs the competitive fleet + self-play
ian_folder/zeus/run_full_training.sh
# or directly:
nohup python3 -m ian_folder.zeus.train --resume --workers 6 >> /tmp/zeus_train.log 2>&1 &
```
Zeus reuses Hades's exact architecture (`training/hades/net.py` + encoders) but flips
the objective: reward +1 for winning (sole survivor), −1 otherwise, no shaping. Metric is
**win rate** vs `[Coyote, Rhino, Elephant, Sly2]` — **higher is better** (random ~20%).
**Benched** until trained. Don't run the Zeus and Hades full runs simultaneously on one
box — they fight for cores.

Hades is **benched in the arena** (commented in `dashboard_server.py`). The metric is
**survival rate** vs `[Ian3, Ian3, Perdition2, Gabriel]` — **lower is better** (target < 2%).
Architecture/backprop are validated by `python3 -m training.hades.gradcheck` (must print
`GRADCHECK PASSED`). Curriculum auto-switches bootstrap→crucible at `--bootstrap_iters`
(default 100); force a single phase with `--phase bootstrap|crucible`. Entropy decays
`--ent_start 0.05` → `--ent_end 0.01` over `--ent_decay_iters`.

### Key flags
- `--workers N` — parallel rollout workers (use cpu_count - 1, typically 6)
- `--resume` — continue from `<module>/checkpoint.json` (ALWAYS use this to avoid overwriting best weights)
- `--patience 500` — stop after 500 evals (~5000 iters) with no improvement (default)
- `--iters N` — hard cap on iterations (default: unlimited)
- `--games N` — games per iteration (default: 256)
- `--lr F` — learning rate (default: 1e-4)

---

## Resuming after a crash or restart

```bash
# IMPORTANT: always --resume to avoid overwriting a good checkpoint
nohup python3 -m rhino.train --resume --workers 6 >> /tmp/rhino_train.log 2>&1 &
```

**Warning:** if you restart WITHOUT `--resume`, the trainer initialises a fresh network, plays ~20 games, then saves that (terrible) policy as the new "best" to both `best_policy.json` AND the deploy path. This corrupts deployed weights. If this happens:

```bash
# Restore from git
git checkout HEAD -- agents/rhino_weights.json
# Then copy back to ian_folder files
cp agents/rhino_weights.json rhino/best_policy.json rhino/checkpoint.json
```

---

## Monitoring progress

```bash
# Tail any ian_folder log
tail -f /tmp/rhino_train.log
tail -f /tmp/elephant_train.log

# Check what's running
ps aux | grep train

# Sample output line:
# iter  340  rollout_win 28.5%  |  greedy vs fleet: win 23.40%  place 3.021  (best 24.10%)  12.3s/it
```

Fields:
- `rollout_win` — win rate during training (stochastic, noisy)
- `greedy vs fleet` — deterministic eval against all arena bots (the number that matters)
- `place` — average finishing position (1=winner, 5=first out); lower is better
- `best` — best greedy win rate seen so far

---

## How deployment works

**Auto-deploy** (server): `auto_deploy.sh` polls git every 60 seconds. When it detects new commits on `main`, it pulls, runs a smoke test, and restarts `dashboard_server.py` if the test passes.

**Training auto-deploy**: when training finds a new best (greedy win rate), it immediately copies the weights to the deploy path (e.g., `agents/rhino_weights.json`). These are picked up by the arena bot on the **next server restart** — training improvements don't hot-reload.

**To deploy training improvements manually:**
```bash
# On server — copy best weights then restart
cp rhino/best_policy.json agents/rhino_weights.json
# Then commit+push from local machine, which triggers auto-deploy
```

Or just commit and push from the local machine — `auto_deploy.sh` handles the rest.

---

## Adding a new bot to the arena

1. Create `agents/<name>_agent.py` with an `ARENA` dict (see any existing agent for the format).
2. Add the import and class to `dashboard_server.py`'s `ARENA_BOTS` list (append, don't reorder).
3. Bump `stats_version` in the agent's `ARENA` dict to discard stale leaderboard stats on restart.
4. Commit and push — auto-deploy handles the rest.

**Benching a bot** (keep training, remove from live arena):
- Comment out its entry in `ARENA_BOTS` in `dashboard_server.py`.
- Leave everything else untouched.

**Re-enabling**:
- Uncomment the `ARENA_BOTS` entry.
- Bump `stats_version` to reset its leaderboard history.
- Commit and push.

---

## Architecture reference

### Rhino (~35K params)
```
GRU(N_EVENT=39 → GRU_H=64)
Trunk(116 → H1=64 → H2=32)
Heads on H2=32:
  policy  (8 action types)
  value   (1 scalar)
  target  (5 relative positions)
  nope    (1 binary)
  give    (13 card types)
  place   (5 deck buckets)
```

### Elephant (~130K params)
```
GRU(N_EVENT=39 → GRU_H=128)
Trunk(180 → H1=128 → H2=64)
Same 5 heads on H2=64
```

---

## Training fleet

All trainers use the same fleet of opponents (mirrors the live arena):

```python
FLEET = [CoyoteAgent, SurvivalAgentV2, SurvivalAgent, AggressiveAgent, HeuristicAgent,
         OrangutanAgent, Orangutan2Agent, RandomAgent, ChaosAgent, Ian1Agent, Ian2Agent]
```

**Perdition2 is intentionally excluded** — it tries to lose, which would corrupt the training signal by teaching the learner to exploit dying opponents instead of winning.

Self-play (`--self_prob 0.4`): 40% of opponent slots in each game are filled with past snapshots of the learner itself, cycling through the last 8 saved checkpoints.

---

## Stats versions

Each bot has a `stats_version` integer in its `ARENA` dict. When the server restarts and sees a version mismatch vs stored stats, it wipes that bot's leaderboard history. Bump this whenever:
- The bot is significantly retrained and old stats are misleading.
- The bot is re-enabled from benched status.

Current versions as of 2026-06-12:
- Most heuristic bots: 7
- Rhino: 7
- Elephant: 1 (new)
