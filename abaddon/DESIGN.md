# Abaddon — the final bot

The all-out endgame bot. Everything we learned from Orangutan/Gorilla, plus a
big swing at new features, opponent exploitation, and game-history modeling.
Built **after** Gorilla proper, reusing the `gorilla/` PPO infrastructure.

Goal: the highest win rate we can squeeze out — dominate the whole fleet.

---

## What we already know (carry forward)

- **Stealing / card economy is the dominant heuristic lever** (Sly2's +7pts).
  Aggression (attacking to force kills, endgame attacking) consistently *hurt*.
- **Card counting matters** — the 35→52 feature jump (explicit unseen counts)
  helped; Coyote's hypergeometric Nope/Defuse reasoning is real signal.
- **BC clones the teacher** (caps at Coyote ~28%). **Self-play PPO breaks the
  ceiling** (value baseline + clipped objective + opponent pool) — Orangutan
  hit ~37% vs fleet and became the #1 bot.
- Deploy constraint so far: **pure-Python inference** (no numpy on the box).
  Abaddon may justify lifting this.

---

## Research answers

### 1. Train against the repo bots and learn to exploit them? — YES

Two layers:

- **Best-response / exploitation.** PPO against the *fixed* repo fleet converges
  to a best response that exploits their specific patterns:
  - Aggressive (Maverick) dumps its whole hand every turn → predictable, runs
    out of defensive cards → bait it, then pressure it late.
  - Random/Chaos → pure exploitable noise.
  - Coyote/Sly/Sly2 are largely **deterministic**: EK always placed on top,
    fixed Nope thresholds, "steal the biggest hand." We can *predict* their
    moves and counter (e.g. know when they'll Nope, when the kitten is coming).
  - Risk: training only vs the fleet **overfits** and gets brittle. Mitigate by
    mixing in self-play (past selves) — a weighted curriculum, fleet-heavy for
    exploitation but with enough self-play to stay robust.
- **Opponent modeling (the big one).** Give Abaddon features that *infer the
  opponent's type/strategy from their observed behavior* and condition its
  policy on it ("this seat attacks every turn → it's Maverick → exploit"). This
  needs per-opponent history features (see #3) and is where the largest
  exploitation gains live.

### 2. Pre-compute more information and feed it in? — YES (high value)

MLPs are bad at deriving combinatorial quantities from raw counts, so handing
them the computed values is high-signal:

- **Exact hypergeometric probabilities** (Coyote already computes these):
  - P(draw an EK on my next draw)
  - P(each opponent holds a Nope) — can my play be cancelled?
  - P(each opponent holds a Defuse / Attack / a completable cat set)
- **Belief state over deck positions** — a probability vector for where the EKs
  and Defuses sit, Bayesian-updated from shuffles, draws, and See-the-Future
  (also a Gorilla-proper item). Feed the top-k position probabilities.
- **Derived EV / threat metrics** — turns until I'm forced to draw, my survival
  probability this trip around, each opponent's "kill potential."
- Caveat: only add **signal-bearing** features; redundant ones just add noise
  and parameters. Validate each block with an A/B like we did for 35→52.

### 3. Track game log / actions already taken? — YES (enables #1)

The current observation is a snapshot; Exploding Kittens leaks hidden info over
time (who played what, who Noped, who was Favored which card, See-the-Future
peeks). Tracking it lets us:

- **Opponent modeling** — per-opponent rates of attack/skip/nope/favor/cat-play,
  defuses used, **whether they've already spent their Nope** (so a play is
  safe), cards revealed via Favor/See-the-Future.
- **Sharper card tracking** than aggregate unseen counts.

Architecture options:

- **Engineered history summary (MLP-friendly, pure-Python deployable).** A
  fixed-size per-opponent stat vector. Cheap, captures most of the value.
  **Start here.**
- **Sequence model (GRU / small attention over the action log).** More
  powerful, but heavier inference → would push us off pure-Python (numpy on the
  box, or accept slower sim). **Experiment second.**

---

## Proposed feature set (superset of Orangutan's 52)

1. Orangutan's 52 (hand/discard/unseen counts, deck/attack/alive, turn-order
   opponent sizes, known-top flags).
2. **Pre-computed probabilities**: P(EK next draw); per-next-opponent P(Nope),
   P(Defuse), P(Attack).
3. **Per-opponent history summary** (for each of up to 4 opponents in turn
   order): action-type rates, nope-spent flag, defuses-used, cards-revealed.
4. **Belief state**: top-k deck-position EK/Defuse probabilities + danger scalar.
5. **Self threat/EV**: turns-until-forced-draw, survival prob.

## Architecture

- Actor-Critic (reuse `gorilla/net.py`, `train.py`), but **all decision heads
  neural and masked**: choose_action, want_to_nope, give_card,
  place_exploding_kitten (Coyote's heuristics showed Nope/placement carry real
  value, so neuralizing them is upside).
- Start: a bigger MLP (still pure-Python). Then try a GRU over the action log.

## Training plan

- Warm-start the action head via BC from the best current bot (Coyote/Orangutan);
  random-init the new heads.
- PPO self-play + fleet exploitation, opponent pool, GAE, clipped objective,
  entropy. Curriculum: fleet-heavy → add self-play.
- Long run; checkpoint best; deploy when it clearly beats Gorilla & Orangutan
  head-to-head (and on the live ladders).

## Open decisions

- Pure-Python inference vs numpy-on-remote (history/GRU pushes toward numpy;
  Abaddon is probably worth it).
- Exploitation vs robustness weighting in the opponent curriculum.
- Reward: win-only (+1/−1, what the spec used) vs placement-shaped.

## Sequencing

1. Gorilla proper (neural heads + belief state) — task #3.
2. **Abaddon** — this doc. Reuses Gorilla's infra; adds opponent modeling +
   pre-computed probabilities + game-log history + new feature blocks.
