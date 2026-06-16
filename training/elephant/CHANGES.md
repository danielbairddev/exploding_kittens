# Elephant Training — Changes & Rollback Guide

## Optimization pass (commit `360f905`)

**Before:** ~20s/iter — **After:** ~5.6s/iter (~3.5× speedup)

### What changed

#### 1. Parallel gradient computation (`train.py`)

**Before:** Online SGD — called `net.step(grads, lr)` once per game, sequentially (256 steps/iter).

**After:** Batch gradient descent — games are split into chunks across workers. Each worker computes and sums gradients for its chunk. Main process averages all gradients and calls `net.step(avg_grads, lr)` once per epoch.

Key functions added/changed:
- `_grads_chunk(args)` — top-level worker function (must be top-level to be picklable)
- `ppo_update(..., ex=None)` — now accepts the executor; falls back to old behaviour if `ex=None`

**Effect on training dynamics:** switches from online SGD to batch gradient descent. Standard for PPO. If training regresses, try `--epochs 2` to restore more gradient steps per iter.

#### 2. Parallel eval (`rollout.py`)

**Before:** `evaluate()` ran 2000 games serially in a single loop.

**After:** `_evaluate_chunk(args)` is a picklable worker; `evaluate(..., ex=None)` splits games across workers when an executor is passed.

No change to training dynamics — eval is read-only. Safe to revert independently.

#### 3. Eval every 20 iters instead of 10 (`train.py`)

**Before:** `if it % 10 == 0`  
**After:** `if it % 20 == 0`

Halves the number of eval calls. You'll see new-best notifications half as often. If you want faster feedback, change back to `% 10`.

#### 4. Default epochs 2 → 1 (`train.py`)

**Before:** `--epochs 2` default  
**After:** `--epochs 1` default

One epoch per iter is standard for PPO with a large batch (256 games). If training quality regresses, run with `--epochs 2` to restore more gradient passes per batch.

---

### How to roll back

**Full rollback** (revert everything to before this commit):
```bash
git revert 360f905
# then restart ian_folder with --resume
```

**Partial rollbacks** (change flags without touching code):
```bash
# More gradient passes per iter (slower but potentially better)
python3 -m ian_folder.elephant.train --resume --workers 4 --epochs 2

# More frequent evals
# Edit train.py: change `it % 20` back to `it % 10`

# Disable parallel gradient update (sequential fallback):
# Edit train.py: pass ex=None to ppo_update instead of ex=ex
```

**Previous stable checkpoint:** commit `ea8219f` — the last version before any of these optimizations.

---

### Timing breakdown (4 workers, M-series laptop)

| Phase         | Before   | After    |
|---------------|----------|----------|
| Rollout       | 0.7s     | 0.7s     |
| PPO update    | 5.5s     | 0.8s     |
| Eval (amort.) | ~3.5s    | ~1.8s    |
| **Total**     | **~20s** | **~5.6s** |
