# Gorilla — self-play PPO training ground

This folder is the home for the **Gorilla** project: a proper self-play
reinforcement-learning pipeline (PPO Actor-Critic) for Exploding Kittens. It is
also the engine we use to push **Orangutan** past its local maximum.

## Why we're here

- **Orangutan** is a neural net trained by *behavioral cloning* of Coyote. That
  pins it AT Coyote's policy (~28% win vs the fleet) — it can't exceed the
  teacher it copied.
- Vanilla **REINFORCE** finetuning degraded it: no value baseline (huge
  variance) and no trust region, so updates drifted off the good policy.

## How we escape the local max (the plan)

A self-play **PPO** loop with all the variance/stability machinery:

1. **Actor-Critic net** — shared MLP base, a policy head (action logits) and a
   value head (expected outcome). The critic is the baseline that makes the
   gradient low-variance.
2. **Clipped surrogate objective** — a trust region so a single batch can't
   destroy the policy (the thing that killed the REINFORCE run).
3. **Entropy bonus** — keeps exploration alive so it doesn't collapse early.
4. **Self-play opponent pool** — the learner plays a *random mix of the
   heuristic fleet + snapshots of its own past selves*. Beating evolving
   opponents (not a fixed teacher) is what lets it discover new strategy.
5. **Warm start from the BC weights** — start competent, then improve.
6. **Sparse reward**: +1 win (last alive), −1 explode, per the spec.

The policy network is kept **identical in shape to Orangutan** (35 features →
64 → 32 → 8 actions), so a better policy from this loop loads straight into
`agents/orangutan_weights.json` — improving Orangutan with **no new bot**.

## Files

- `net.py` — Actor-Critic numpy net + Adam; saves policy in Orangutan format.
- `rollout.py` — the Learner/Frozen net agents + single-game rollout, opponent
  sampling from fleet + self-play pool. Parallelizable (stateless given weights).
- `train.py` — PPO loop: parallel rollouts → GAE/returns → clipped update → eval
  → checkpoint. Run: `python3 -m gorilla.train --iters 2000 --workers 8`.

## Results log

| date | change | eval win% vs fleet | notes |
|------|--------|--------------------|-------|
| (baseline) | BC clone of Coyote | ~28.3% | Orangutan's shipped weights |
| _pending_ | PPO self-play warm-started from BC | _running_ | targeting > 28.3% |

## Roadmap for Gorilla proper (beyond Orangutan-compat)

- Richer observation encoder with a **belief state** over EK/Defuse positions
  (Bayesian update from shuffles/draws/See-the-Future) and an explicit danger
  scalar. This changes the input size, so it becomes its own bot (Gorilla),
  deployed separately rather than folded into Orangutan.
- Give the net the **Nope / give-card / placement** decisions too (currently
  inherited from Coyote), as separate masked heads.
- True vectorized envs (batched step) instead of per-game rollouts.
