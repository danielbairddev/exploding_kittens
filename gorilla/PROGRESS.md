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
| (baseline) | BC clone of Coyote (35 feat) | ~28.3% | original Orangutan weights |
| run 1 | PPO self-play, 35 feat | **30.7%** best | confirmed PPO escapes the BC ceiling (stable, no collapse) |
| — | **expanded features 35 → 52** | — | added explicit unseen/card-counting (12), attack-stack depth, my-defuse count, next-4 opponents' hand sizes in turn order |
| run 2 | re-BC (52 feat) | ~28.5% | new Orangutan weights; BC ceiling unchanged (still clones Coyote) |
| run 2 | PPO self-play, 52 feat | **40.1%** final | **DEPLOYED into Orangutan** (redeployed as it climbed: 31.6→35.4→37.4→40.1%). Now the clear #1 bot; head-to-head it beats Coyote/Sly2 by several points. Run concluded (plateau). |

## Ceiling analysis — why everything plateaus at ~40%

An oracle that always sees the real top 3 cards (perfect See-the-Future, via the
engine's `reveal_top`) and otherwise plays Coyote wins **43.8%** vs the fleet.
That's the information-theoretic ceiling. Reference points (1-of-5, 20% baseline):

| agent | win% |
|------|------|
| random | 20% |
| Coyote (heuristic) | 29% |
| Orangutan (RL, deployed) | **40.1%** |
| oracle (perfect top-3) | **43.8% (ceiling)** |

Orangutan reaches **91% of the perfect-information ceiling with no cheating.**
The remaining ~3.7pts is unseen-card knowledge we can't get — which is exactly
why neural Nope (Mandrill, 40.3%), opponent modeling (Gorilla, 39.9%), and the
other heads all tied: the limit is *information, not policy*. The only partial
lever left is a probabilistic belief-state to better estimate the top — and even
that can capture only a fraction of 3.7pts. Verdict: Orangutan is near-optimal;
stop grinding policy. Belief-state (Abaddon) is the only avenue with any headroom,
at low ROI.

## Head-to-head verdict — Orangutan is the proven champion

Benchmark win% (vs the heuristic fleet) hides direct strength, so we ran big
5-player head-to-heads with randomized counts (per-seat win rate, baseline 20%):

| matchup (200k / 120k games) | Orangutan | challenger | verdict |
|---|---|---|---|
| Orangutan vs Abaddon (belief, trained vs fleet) | **21.34%** | 18.66% | Orangutan +2.67 |
| Orangutan vs Abaddon **trained against Orangutan** (~500 iters) | **23.59%** | 16.40% | Orangutan +7.19 |

Training *against* Orangutan made it **worse**, not better: best-responding to a
2-Orangutan field is slow (23.7% -> 28.7% over 500 iters vs the 1700 Orangutan
needed against the easy fleet), so we just got an under-developed, weaker policy.
There was no exploit to find — Orangutan plays near the information ceiling.

**Three independent confirmations Orangutan is best:** (1) it's at 91% of the
perfect-info ceiling; (2) every successor (Gorilla, Mandrill, Abaddon) tied or
lost on the benchmark; (3) training directly against it fails to produce a
counter. Conclusion: 🦧 Orangutan (40.1% vs fleet) is the champion; the neural-bot
line of work is complete. The 👹 Abaddon demon icon stays in reserve.

## Gorilla proper — progress

- **GameTracker** (`tracker.py`) built + validated. Reconstructs the full action
  log from an agent's `want_to_nope` callbacks (fires for every play by every
  player) → accurate per-opponent behavior profiles. Verified it fingerprints
  bots correctly (Professor = 43% See-the-Future/30% Attack; Sly2 = 35%
  cat-pair). This is the opponent-modeling foundation for Gorilla + Abaddon.
- **Next:** belief-state encoder (deck-position probabilities) + a multi-head
  Actor-Critic that also makes the Nope / give-card / placement decisions
  (masked), with the tracker's profile features fed in.

## TODO (next, once the Orangutan PPO run is exhausted)

**Build Gorilla proper** — the big lever past Orangutan. Two changes that
together make it its own bot (input size changes, so it can't fold into
Orangutan):

## Roadmap for Gorilla proper (beyond Orangutan-compat)

- Richer observation encoder with a **belief state** over EK/Defuse positions
  (Bayesian update from shuffles/draws/See-the-Future) and an explicit danger
  scalar. This changes the input size, so it becomes its own bot (Gorilla),
  deployed separately rather than folded into Orangutan.
- Give the net the **Nope / give-card / placement** decisions too (currently
  inherited from Coyote), as separate masked heads.
- True vectorized envs (batched step) instead of per-game rollouts.
