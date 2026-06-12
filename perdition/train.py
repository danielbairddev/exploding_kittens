#!/usr/bin/env python3
"""PPO training for Perdition — optimise to lose (minimise win rate).

Mirrors gorilla/train.py but with:
  - Inverted reward (-1 win, +1 any loss) from perdition/rollout.py
  - No BC warm-start (we don't want it imitating competent play)
  - Best policy tracked by LOWEST greedy win rate, not highest
  - Saves policy weights to agents/perdition_weights.json

    python3 -m perdition.train --iters 3000 --workers 8
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gorilla.net import ActorCritic
from gorilla.train import compute_targets, ppo_update
from perdition.rollout import rollout_worker, evaluate

HERE = os.path.dirname(os.path.abspath(__file__))
WEIGHTS_OUT = os.path.join(HERE, "..", "agents", "perdition_weights.json")
BEST_OUT = os.path.join(HERE, "best_policy.json")
CKPT_OUT = os.path.join(HERE, "checkpoint.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=3000)
    ap.add_argument("--games", type=int, default=512)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--mb", type=int, default=2048)
    ap.add_argument("--clip", type=float, default=0.2)
    ap.add_argument("--vf", type=float, default=0.5)
    ap.add_argument("--ent", type=float, default=0.01)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--gamma", type=float, default=0.997)
    ap.add_argument("--self_prob", type=float, default=0.2)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    net = ActorCritic()
    if args.resume and os.path.exists(CKPT_OUT):
        net.load_full(json.load(open(CKPT_OUT)))
        print("resumed from checkpoint", flush=True)
    else:
        print("starting from random weights (no BC warm-start)", flush=True)

    pool = []
    base_wr, base_ap = evaluate(net.policy_weights(), n=3000)
    # Best = lowest win rate.
    best_wr = base_wr
    print(f"baseline (random init) greedy vs fleet: win {base_wr*100:.1f}%  place {base_ap:.3f}", flush=True)

    ex = ProcessPoolExecutor(max_workers=args.workers) if args.workers > 1 else None
    seed = 2000
    for it in range(1, args.iters + 1):
        t0 = time.time()
        policy_w = net.full_weights()
        per = max(1, args.games // max(1, args.workers))
        tasks = []
        if ex:
            for _ in range(args.workers):
                seed += 1
                tasks.append(ex.submit(rollout_worker, (policy_w, list(pool), per, seed, args.self_prob)))
            games = []
            for f in tasks:
                games.extend(f.result())
        else:
            seed += 1
            games = rollout_worker((policy_w, list(pool), args.games, seed, args.self_prob))

        data = compute_targets(games, args.gamma)
        if data is not None:
            ppo_update(net, data, args.epochs, args.mb, args.clip, args.vf, args.ent, args.lr)

        net.save_full(CKPT_OUT)
        if it % 20 == 0:
            pool.append(net.policy_weights())
            if len(pool) > 8:
                pool.pop(0)
        if it % 10 == 0:
            wr, apl = evaluate(net.policy_weights(), n=3000)
            tag = ""
            if wr < best_wr:
                best_wr = wr
                net.save_policy(BEST_OUT)
                # Also push to the live agent weights so the arena picks it up.
                net.save_policy(WEIGHTS_OUT)
                tag = "  <- new best (saved)"
            losses = sum(1 for _, r in games if r > 0)
            print(f"iter {it:4d}  rollout_loss {losses/len(games)*100:4.1f}%  "
                  f"|  greedy vs fleet: win {wr*100:5.2f}%  loss {(1-wr)*100:5.2f}%  "
                  f"place {apl:.3f}  (best win {best_wr*100:.2f}%)  "
                  f"{time.time()-t0:.1f}s/it{tag}", flush=True)
    if ex:
        ex.shutdown()
    # Save final weights regardless.
    net.save_policy(WEIGHTS_OUT)
    print("done. best policy in", BEST_OUT, flush=True)


if __name__ == "__main__":
    main()
