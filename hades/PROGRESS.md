# Hades-v2 — Implementation Progress & Plan

Tracking doc for building the Hades anti-agent (the Transformer "loser" bot) end to end.
Spec: [HADES_PLAN.md](HADES_PLAN.md). This file records *how* the spec maps onto this
codebase and what was actually built.

## Goal (from the spec)

Train an agent to intentionally **lose** (die) against a fleet of other "loser" bots.
Transformer encoder replaces the GRU used by the Orpheus/Gabriel family. Strict binary
terminal reward (+1 die / −1 sole-survivor) plus dense auxiliary shaping.

Success metric: survival rate `< 2%` over 10k matches vs `[Ian3, Ian3, Perdition2, Gabriel]`.

## How this maps onto the repo

This repo has **no PyTorch** (not installed; deployed agents are pure-Python / optional
numpy). All existing nets (Rhino/Elephant/Gabriel/Orpheus) are hand-written numpy with
manual forward + backward and PPO+BPTT. Hades follows the same convention but swaps the
GRU memory module for a **manually-differentiated Transformer encoder**.

Layout (mirrors `training/orpheus/` + `agents/orpheus_agent.py`):

```
training/hades/
  __init__.py
  event_encode.py   # 64-dim event vectors, N=128 window  (spec §1.1)
  features.py       # 134-dim snapshot + per-opponent tracker (spec §1.2)
  net.py            # Transformer encoder + trunk + 6 heads, fwd/bwd (spec §2,§3)
  rollout.py        # learner agent, curriculum fleets, reward shaping (spec §4,§5)
  train.py          # PPO loop, entropy decay, phase switching (spec §4.3,§5)
  gradcheck.py      # numerical gradient check harness for net.py
agents/
  hades_agent.py    # inference (numpy + pure-python fallback), loads hades_weights.json
  hades_weights.json
```

## Architecture (as built)

- **Event encoder** (`event_encode.py`): 64-d per event — event_type(14) | actor_rel(5) |
  target_rel(6) | card_played(14) | card_given(14) | turn_norm(1) | is_my_turn(1) |
  action_resolved(1) | cards_to_draw(1) | padding(1) | reserved(6). Window N=128, left-padded.
- **Snapshot** (`features.py`): 134-d — core counts(42) | scalars(10) | opp matrix(40) |
  exact deck state(42 = 14 cards × top-3 from See-the-Future).
- **Memory** (`net.py`): 3 layers × 4 heads, d_model=128, ff=256, dropout=0.1 (train only),
  sinusoidal absolute positional encoding. Pool = concat(mean, last) → 256.
- **Trunk**: concat(mem 256, snap 134)=390 → 256 → 128, LayerNorm + Mish.
- **Heads**: policy(8, masked) · value(1) · target(5, masked) · nope(context 128+24→64→1, sigmoid)
  · give(14, hand-masked) · place(50-way softmax, masked to deck size).

## Reward (spec §4)

- Terminal: +1.0 if Hades dies at any point, −1.0 if sole survivor.
- Aux: give_defuse +0.2, waste_defuse(successful defuse) +0.2, draw_safe(non-EK draw) −0.05.
- PPO: clip ε=0.2, Huber value loss, γ=0.99, entropy 0.05→0.01.

## Curriculum (spec §5)

- Phase 1 (bootstrap): 100% standard winner bots (Coyote/Rhino/Elephant) — forces fast self-destruction.
- Phase 2 (crucible): 80% loser fleet (Ian1-3, Perdition2, Gabriel) + 20% self-play (last 5 ckpts).

## Deviations / pragmatic notes

- **`action_resolved` / `cards_to_draw` per event**: not all carried on the public event
  stream. `action_resolved` is derived (an `action_noped` that leaves the action cancelled →
  0, otherwise 1); `cards_to_draw` approximated from the running attack stack. Documented in code.
- **Opponent matrix** needs per-opponent running stats (prob_has_defuse, play/nope rates).
  Maintained in a stateful `OpponentTracker` updated from `recent_events` each absorb.
- **Training budget**: the 5M–20M-step curriculum is not run to completion here. Deliverable is
  the full, gradient-checked pipeline plus a short smoke run that produces valid weights. The bot
  stays **benched** (not added to live `ARENA_BOTS`) until real weights beat the loser fleet.
- **Inference dtype**: numpy if available, pure-Python fallback (matches Orpheus pattern).

## Status checklist

- [x] PROGRESS.md (this file)
- [x] event_encode.py + features.py (+ dim tests, validated on a real game)
- [x] net.py forward/backward — **gradcheck PASSED** (worst rel err 6e-7 over all 74 params)
- [x] rollout.py (curriculum + reward shaping) — smoke-tested
- [x] train.py (PPO loop) — single + multiprocess paths verified
- [x] agents/hades_agent.py (inference) — loads weights, 30-game crash test, fallback path
- [x] smoke train → hades_weights.json, full-game self-check
- [x] docs (BOTS.md / TRAINING.md / AGENTS.md), kept benched (commented in dashboard_server)

## CURRENT STATE (2026-06-14 — LIVE in arena, still training)

Full pipeline implemented, gradient-checked, and on `main`. Hades is now **UNBENCHED**:
`HadesAgent` is active in `web/dashboard_server.py` `ARENA_BOTS` (bot_id 15). The full
training orchestrator (`run_full_training.sh`) is still **running in the background**;
new bests keep auto-deploying to `agents/hades_weights.json`.

**Eval survival vs `[Ian3, Ian3, Perdition2, Gabriel]`** (lower = better):

| phase / checkpoint | survival | note |
|---|---|---|
| random init | ~56% | start |
| bootstrap iter 40 | 26.9% | first committed weights |
| bootstrap iter 100 | 22.5% | |
| crucible iter 40 | 19.1% | |
| **crucible iter 140 (deployed)** | **18.9%** | live in arena |

Survival fell fast then **plateaued ~19–21%**. Rollout death-rate ~77–90% in crucible
(the bot tries hard to die; genuine losers just won't win for it). Deployed weights are
monotonic — the trainer only overwrites `hades_weights.json` on a strict improvement, so
the live file is always the best-so-far.

Note: `training/hades/checkpoint.json` / `best_policy.json` / `bests.jsonl` are gitignored
(regenerated artifacts). They live **locally** on the training machine, so `--resume`
continues exactly where it left off. A fresh clone starts from the committed
`agents/hades_weights.json`.

## NEXT STEPS / potential improvements (to break the ~19% plateau)

The pipeline is done; these are research levers to push survival lower:

1. **Keep the current run going** — it self-terminates on target (2%), stall (patience 80),
   or the iter cap (3000). Each new best auto-deploys locally; **re-deploy to the arena**
   by committing the improved `agents/hades_weights.json` + bumping `GLOBAL_STATS_VERSION`
   and `LOSER_STATS_VERSION` (deploy must reset stats — see [[feedback-deploy-reset-stats]]).
2. **Stronger self-play in crucible** — raise `--self_prob` (0.2 → 0.4–0.5). Against bots
   that are themselves trying to die, the learner's best sparring partner is its own
   improving self; this is the most likely plateau-breaker.
3. **Per-step (not summed) aux rewards** — currently aux is folded into one discounted
   game scalar (see "Deviations"). Attaching give/waste-defuse and safe-draw penalties to
   their exact transitions would sharpen credit assignment toward the suicidal micro-moves.
4. **Slower entropy decay** — `--ent_decay_iters 800+` keeps exploration alive longer so it
   doesn't prematurely commit to a 19% local optimum.
5. **Curriculum tweaks** — extend bootstrap, or add a phase-2.5 that over-samples the exact
   eval fleet; the `place` head (50-way deck depth) is the key suicide lever — inspect
   whether it's learning to bury the EK at `turns_to_my_turn` as intended.
6. **Lengthen the run / more games** — `--games 256`, higher `--patience`; out-losing
   losers is genuinely hard and may need far more samples than the bootstrap.
7. **Reward audit** — confirm the −1 "sole survivor" signal isn't being swamped by the
   dense aux bonuses (a bot that hoards defuses for the +0.2 could accidentally survive).

## Useful commands

```bash
python3 -m training.hades.gradcheck          # must print GRADCHECK PASSED
python3 -m training.hades.train --phase bootstrap --iters 100 --workers 6   # phase 1 only
python3 -m training.hades.train --resume --workers 6                        # auto bootstrap->crucible
```
</content>
</invoke>
