# Bot Roster

## Pure Heuristic

These bots have no ML weights and never change. They serve as baselines and opponents for training.

| Bot | Arena name | Strategy |
|-----|-----------|----------|
| Lucky | 🎲 Lucky | Random valid actions. Pure noise baseline. |
| Maverick | 💥 Maverick | Attack-first. Spams Attacks to dump the deck on others, Nopes liberally. |
| Gremlin | 🌀 Gremlin | Deliberate chaos. Randomised play to confuse opponents. |
| Professor | 🧠 Professor | Card-counting rules. Always SeeFutures, Shuffles/Skips known kittens, Nopes ~70% of attacks, buries EK deep. |
| Sly | 🦊 Sly | Survival-first. SeeFuture as a draw-gate; never draws a known kitten; uses Defuse as insurance; buries EK on top to trap the next player. |
| Sly2 | 🦝 Sly2 | Sly + relentless stealing. Same survival spine but plays cat pairs/triples aggressively for card advantage. A/B benchmarked against Sly. |
| Coyote | 🐺 Coyote | Strongest pure heuristic. Probabilistic card counting (combinatorics over remaining deck), targets the leader. Base class inherited by all ML bots. |

## ML — MLP (stateless, no game memory)

These bots encode a hand-crafted feature snapshot of the current game state and pass it through a small MLP to pick an action. They have no memory of prior turns.

### Active in arena

| Bot | Arena name | Architecture | Training | Status |
|-----|-----------|-------------|---------|--------|
| Orangutan | 🦧 Orangutan | Small MLP, feature snapshot → action type. Nopes/giving/placement inherited from Coyote. | Behavioral cloning (BC) | **In arena** |

### Abandoned

| Bot | Arena name | Why abandoned |
|-----|-----------|--------------|
| Perdition | 😢 Perdition | MLP PPO with experimental self-sabotage reward hooks. Superseded by Perdition2. Weights frozen. |
| Perdition2 | 😢 Perdition2 | Longer PPO run of Perdition. Still underperforms Rhino/Elephant. Weights frozen. |

### Benched (training, not yet competitive)

| Bot | Arena name | Architecture | Training | Status |
|-----|-----------|-------------|---------|--------|
| Orangutan2 | 🦧 Orangutan2 | Same MLP arch as Orangutan. | **Gorilla PPO** on server (6 workers). Trainer: `training/gorilla/`. Best: 37.83% at iter 30. | **Benched** — underperforms Orangutan1 in arena so far. Re-enable in `dashboard_server.py` once it beats Orangutan1. |

## ML — GRU (adversarial / inverted reward)

These bots use the GRU-128 architecture but are trained with inverted or constrained rewards.

### Disabled (training only — never in arena)

| Bot | Arena name | Architecture | Training | Status |
|-----|-----------|-------------|---------|--------|
| Orpheus | 🪕 Orpheus | GRU(39→128) + Trunk(180→128→64) + 5 heads | **PPO + BPTT** vs Gabriel/Perdition losing-fleet. Trainer: `training/orpheus/`. Bootstrapped from Gabriel weights. | **Disabled** — trained to die first against bots also trying to die. Must out-lose the losers. |

### Benched (awaiting competitive weights)

| Bot | Arena name | Architecture | Training | Status |
|-----|-----------|-------------|---------|--------|
| Gabriel | 🪬 Gabriel | GRU(39→128) + Trunk(180→128→64) + 5 heads | **PPO + BPTT** inverted reward (+1 for dying first) vs standard fleet. Trainer: `training/gabriel/`. | **Benched** — re-enable in `dashboard_server.py` when desired. |

## ML — GRU (recurrent, remembers game history)

These bots process the full event stream through a GRU to maintain a hidden state across the game. They can remember what happened on earlier turns, giving them genuine sequential reasoning.

Feature encoding: `training/rhino/event_encode.py` (39-dim event vectors, shared by all GRU bots).

| Bot | Arena name | Architecture | Params | Training | Status |
|-----|-----------|-------------|--------|---------|--------|
| Rhino | 🦏 Rhino | GRU(39→64) + Trunk(116→64→32) + 5 heads | ~35K | **PPO + BPTT** on server (6 workers). Trainer: `training/rhino/`. Best: 36.05% at iter 10. | **In arena** |
| Elephant | 🐘 Elephant | GRU(39→128) + Trunk(180→128→64) + 5 heads | ~130K | **PPO + BPTT** on laptop (4 workers). Trainer: `training/elephant/`. Best: 17.35% at iter 10 (early). | **In arena** |

## Trainer → weights mapping

| Trainer dir | Produces | Deployed to |
|-------------|---------|------------|
| `training/gorilla/` | `best_policy.json` | `agents/orangutan2_weights.json` |
| `training/rhino/` | `best_policy.json` | `agents/rhino_weights.json` |
| `training/elephant/` | `best_policy.json` | `agents/elephant_weights.json` |
| `training/gabriel/` | `best_policy.json` | `agents/gabriel_weights.json` |
| `training/orpheus/` | `best_policy.json` | `agents/orpheus_weights.json` |

## Progression

```
Lucky / Maverick / Gremlin
        ↓
    Professor
        ↓
       Sly → Sly2
                ↓
             Coyote  ←──────────────────────────────────┐
                ↓                                       │ (fallback base class)
          Orangutan (MLP, BC)                           │
          Orangutan2 (MLP, Gorilla PPO) [benched]       │
          Perdition / Perdition2 (MLP, PPO) [abandoned] │
          Rhino (GRU-64, PPO+BPTT) ────────────────────┘
          Elephant (GRU-128, PPO+BPTT) ─────────────────┘
```
