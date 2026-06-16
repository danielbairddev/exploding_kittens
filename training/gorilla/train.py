#!/usr/bin/env python3
"""PPO self-play ian_folder for Gorilla / improved Orangutan.

Warm-starts from Orangutan's BC weights, then runs a clipped-objective
Actor-Critic PPO loop against a mix of the heuristic fleet and snapshots of its
own past selves. Saves the best policy (Orangutan-compatible) so it can be
dropped into agents/orangutan_weights.json.

    python3 -m gorilla.train --iters 2000 --workers 8

Progress lines report greedy win% / avg place vs the fleet.
"""
import argparse
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from training.gorilla.net import ActorCritic, masked_softmax, NEG
from training.gorilla.rollout import rollout_worker, evaluate
from agents.orangutan_features import N_ACTIONS

HERE = os.path.dirname(os.path.abspath(__file__))
BC_WEIGHTS = os.path.join(HERE, "..", "..", "agents", "orangutan_weights.json")
BEST_OUT = os.path.join(HERE, "best_policy.json")
CKPT_OUT = os.path.join(HERE, "checkpoint.json")
DEPLOY_OUT = os.path.join(HERE, "..", "..", "agents", "orangutan2_weights.json")
BESTS_LOG = os.path.join(HERE, "bests.jsonl")
DEFAULT_LOG = os.path.join(HERE, "..", "..", "logs", "train_orangutan_gorilla2.log")


def parse_log_progress(log_path):
    """Last iter + best win rate from a ian_folder log (for --resume)."""
    if not os.path.exists(log_path):
        return 0, None
    last_iter, best = 0, None
    with open(log_path) as f:
        for line in f:
            m = re.search(r"iter\s+(\d+)", line)
            if m:
                last_iter = int(m.group(1))
            m = re.search(r"\(best\s+([\d.]+)%\)", line)
            if m:
                best = float(m.group(1)) / 100.0
    return last_iter, best


def compute_targets(games, gamma):
    """Flatten (traj, reward) games into PPO arrays with discounted returns."""
    X, idx, oldlp, ret, mask = [], [], [], [], []
    val = []
    for traj, reward in games:
        T = len(traj)
        for t, (feat, a, lp, v, m) in enumerate(traj):
            R = reward * (gamma ** (T - 1 - t))
            X.append(feat); idx.append(a); oldlp.append(lp); ret.append(R)
            val.append(v); mask.append(m)
    if not X:
        return None
    X = np.array(X); idx = np.array(idx); oldlp = np.array(oldlp)
    ret = np.array(ret); val = np.array(val); mask = np.array(mask)
    adv = ret - val
    adv = (adv - adv.mean()) / (adv.std() + 1e-8)
    return X, idx, oldlp, adv, ret, mask


def ppo_update(net, data, epochs, mb, clip, vf_coef, ent_coef, lr):
    X, idx, oldlp, adv, ret, mask = data
    N = len(X); ar = np.arange(N)
    for _ in range(epochs):
        perm = np.random.permutation(N)
        for s in range(0, N, mb):
            b = perm[s:s + mb]
            Xb, ib, olp, ad, rt, mk = X[b], idx[b], oldlp[b], adv[b], ret[b], mask[b]
            B = len(b)
            logits, value, (xx, Z1, A1, Z2, A2) = net.forward(Xb)
            P = masked_softmax(logits, mk)
            logp_all = np.where(mk > 0, np.log(P + 1e-12), 0.0)
            logp = logp_all[np.arange(B), ib]
            ratio = np.exp(logp - olp)
            surr1 = ratio * ad
            surr2 = np.clip(ratio, 1 - clip, 1 + clip) * ad
            use1 = surr1 <= surr2
            in_range = (ratio > 1 - clip) & (ratio < 1 + clip)
            coeff = np.where(use1, 1.0, in_range.astype(float))
            gpol_logp = -(ad * ratio * coeff) / B                  # d pol_loss / d logp
            onehot = np.eye(logits.shape[1])[ib]
            dlogits = gpol_logp[:, None] * (onehot - P)
            # entropy: maximize -> subtract from loss
            a_term = (logp_all + 1.0) * mk
            mean_a = (P * a_term).sum(1, keepdims=True)
            dent = P * (mean_a - a_term)                            # d entropy / d logits
            dlogits += (-ent_coef) * dent / B
            # value
            dvalue = vf_coef * (value - rt) / B                     # (B,)
            gW3 = dlogits.T @ A2; gb3 = dlogits.sum(0)
            gWv = (dvalue[None, :] @ A2); gbv = np.array([dvalue.sum()])
            dA2 = dlogits @ net.W3 + np.outer(dvalue, net.Wv[0])
            dZ2 = dA2 * (Z2 > 0); gW2 = dZ2.T @ A1; gb2 = dZ2.sum(0)
            dA1 = dZ2 @ net.W2; dZ1 = dA1 * (Z1 > 0); gW1 = dZ1.T @ Xb; gb1 = dZ1.sum(0)
            net.step({"W1": gW1, "b1": gb1, "W2": gW2, "b2": gb2,
                      "W3": gW3, "b3": gb3, "Wv": gWv, "bv": gbv}, lr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=999999, help="max iters (default: unlimited)")
    ap.add_argument("--games", type=int, default=512, help="rollout games per iter")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--mb", type=int, default=2048)
    ap.add_argument("--clip", type=float, default=0.2)
    ap.add_argument("--vf", type=float, default=0.5)
    ap.add_argument("--ent", type=float, default=0.01)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--gamma", type=float, default=0.997)
    ap.add_argument("--self_prob", type=float, default=0.5)
    ap.add_argument("--patience", type=int, default=500,
                    help="stop after this many evals with no improvement (default 500)")
    ap.add_argument("--resume", action="store_true",
                    help="load checkpoint.json; --iters is additional iters to run")
    ap.add_argument("--log", default=DEFAULT_LOG,
                    help="ian_folder log to read last iter/best when resuming")
    args = ap.parse_args()

    net = ActorCritic()
    start_iter = 0
    if args.resume and os.path.exists(CKPT_OUT):
        import json
        net.load_full(json.load(open(CKPT_OUT)))
        start_iter, log_best = parse_log_progress(args.log)
        print(f"resumed checkpoint @ iter {start_iter}", flush=True)
    else:
        net.load_bc(BC_WEIGHTS)
        print("warm-started from BC weights", flush=True)
        log_best = None

    pool = []                       # past-self policy snapshots (Orangutan format)
    base_wr, base_ap = evaluate(net.policy_weights(), n=3000)
    best = log_best if log_best is not None else base_wr
    if start_iter:
        print(f"resume baseline greedy vs fleet: win {base_wr*100:.1f}%  place {base_ap:.3f}  "
              f"(log best {best*100:.2f}%)", flush=True)
    else:
        print(f"baseline (BC) greedy vs fleet: win {base_wr*100:.1f}%  place {base_ap:.3f}", flush=True)

    end_iter = start_iter + args.iters
    ex = ProcessPoolExecutor(max_workers=args.workers) if args.workers > 1 else None
    seed = 1000 + start_iter
    no_improve = 0  # evals since last best
    for it in range(start_iter + 1, end_iter + 1):
        t0 = time.time()
        policy_w = net.full_weights()
        per = max(1, args.games // max(1, args.workers))
        tasks = []
        if ex:
            for w in range(args.workers):
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
            if wr > best:
                best = wr; no_improve = 0
                net.save_policy(BEST_OUT); net.save_policy(DEPLOY_OUT); tag = "  <- new best (saved)"
                import json as _json
                with open(BESTS_LOG, 'a') as _f:
                    _f.write(_json.dumps({'iter': it, 'win': round(wr*100,2), 'place': round(apl,3), 't': int(time.time())}) + '\n')
            else:
                no_improve += 1
            wins = sum(1 for _, r in games if r > 0)
            print(f"iter {it:4d}  rollout_win {wins/len(games)*100:4.1f}%  "
                  f"|  greedy vs fleet: win {wr*100:5.2f}%  place {apl:.3f}  "
                  f"(best {best*100:.2f}%)  {time.time()-t0:.1f}s/it{tag}", flush=True)
            if no_improve >= args.patience:
                print(f"stalled: no improvement in {no_improve} evals. stopping.", flush=True)
                break
    if ex:
        ex.shutdown()
    print("done. best policy in", BEST_OUT, flush=True)


if __name__ == "__main__":
    main()
