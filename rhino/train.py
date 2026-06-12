#!/usr/bin/env python3
"""PPO + BPTT training for Rhino (GRU Actor-Critic).

The GRU processes the public event log; the MLP maps (GRU_hidden, snapshot) to
policy + value. PPO gradients flow back through the MLP and then through the
full GRU sequence via BPTT.

    python3 -m rhino.train --iters 3000 --workers 6
"""
import argparse
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rhino.net import GRUActorCritic, GRU_H, ALL_KEYS, N_MLP_IN
from rhino.rollout import rollout_worker, evaluate
from agents.orangutan_features import N_ACTIONS

HERE = os.path.dirname(os.path.abspath(__file__))
BEST_OUT = os.path.join(HERE, 'best_policy.json')
CKPT_OUT = os.path.join(HERE, 'checkpoint.json')
DEPLOY_OUT = os.path.join(HERE, '..', 'agents', 'rhino_weights.json')

NEG = -1e9


def _masked_softmax(logits, mask):
    z = np.where(mask > 0, logits, NEG)
    z -= z.max()
    e = np.exp(z) * mask
    return e / (e.sum() + 1e-12)


def compute_targets(games, gamma):
    """Add 'return' and 'advantage' to each step in-place."""
    for gd, reward in games:
        steps = gd['steps']
        T = len(steps)
        for t in range(T):
            R = reward * (gamma ** (T - 1 - t))
            steps[t]['return'] = R
            steps[t]['advantage'] = R - steps[t]['old_value']


def _game_grads(net, gd, clip, vf_coef, ent_coef):
    """Compute PPO + BPTT gradients for one game. Returns (grads_dict, n_steps)."""
    event_vecs = [np.array(ev, dtype=np.float32) for ev in gd['event_vecs']]
    steps = gd['steps']
    if not steps:
        return None, 0

    # ---- GRU forward over all events ----
    hs, gru_caches = net.run_gru(event_vecs)
    E = len(event_vecs)

    # ---- MLP forward for each learner step ----
    step_fwd = []   # (logits, P, value, mlp_cache, event_count)
    for step in steps:
        ec = min(step['event_count'], E)
        logits, value, mlp_cache = net.mlp_forward(hs[ec], np.array(step['snapshot']))
        mask = np.array(step['mask'])
        P = _masked_softmax(logits, mask)
        step_fwd.append((logits, P, value, mlp_cache, ec))

    # ---- Accumulate PPO gradients, backprop through MLP ----
    all_grads = {k: np.zeros_like(getattr(net, k)) for k in ALL_KEYS}
    dh_from_mlp = defaultdict(lambda: np.zeros(GRU_H))
    n_steps = len(steps)

    for t, step in enumerate(steps):
        logits, P, value, mlp_cache, ec = step_fwd[t]
        mask = np.array(step['mask'])
        adv = step['advantage']
        ret = step['return']
        a = step['action']

        # PPO policy loss gradient w.r.t. log π(a)
        new_logp = float(np.log(P[a] + 1e-12))
        ratio = np.exp(new_logp - step['old_logp'])
        surr1 = ratio * adv
        surr2 = np.clip(ratio, 1.0 - clip, 1.0 + clip) * adv
        use1 = surr1 <= surr2
        in_range = (1.0 - clip) < ratio < (1.0 + clip)
        coeff = 1.0 if use1 else float(in_range)
        d_logp = -(adv * ratio * coeff) / n_steps   # minimising -obj

        # d(logp)/d(logits) = (e_a - P) for masked softmax
        onehot = np.zeros(N_ACTIONS); onehot[a] = 1.0
        dlogits = d_logp * (onehot - P) * mask

        # Entropy bonus: maximise H  →  add -ent_coef * d(-H)/d(logits)
        log_P = np.log(P + 1e-12)
        mean_term = np.sum(P * (log_P + 1.0) * mask)
        dlogits += (-ent_coef) * P * (mean_term - (log_P + 1.0) * mask)

        # Value loss gradient
        dvalue = vf_coef * (value - ret) / n_steps

        dh, mlp_g = net.mlp_backward(dlogits, dvalue, mlp_cache)
        dh_from_mlp[ec] += dh
        for k in mlp_g:
            all_grads[k] += mlp_g[k]

    # ---- BPTT through GRU ----
    dh = dh_from_mlp.get(E, np.zeros(GRU_H))
    for i in range(E - 1, -1, -1):
        dh_prev, gru_g = net.gru_step_backward(dh, gru_caches[i])
        for k in gru_g:
            all_grads[k] += gru_g[k]
        dh = dh_prev + dh_from_mlp.get(i, np.zeros(GRU_H))

    return all_grads, n_steps


def ppo_update(net, games, epochs, clip, vf_coef, ent_coef, lr):
    """Run PPO epochs over the collected games."""
    import random
    indices = list(range(len(games)))
    total_steps = 0

    for _ in range(epochs):
        random.shuffle(indices)
        for i in indices:
            gd, _ = games[i]
            grads, n = _game_grads(net, gd, clip, vf_coef, ent_coef)
            if grads is not None and n > 0:
                net.step(grads, lr)
                total_steps += n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--iters', type=int, default=3000)
    ap.add_argument('--games', type=int, default=256)
    ap.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument('--epochs', type=int, default=2)
    ap.add_argument('--clip', type=float, default=0.2)
    ap.add_argument('--vf', type=float, default=0.5)
    ap.add_argument('--ent', type=float, default=0.01)
    ap.add_argument('--lr', type=float, default=1e-4)
    ap.add_argument('--gamma', type=float, default=0.997)
    ap.add_argument('--self_prob', type=float, default=0.4)
    ap.add_argument('--resume', action='store_true')
    args = ap.parse_args()

    net = GRUActorCritic()
    if args.resume and os.path.exists(CKPT_OUT):
        import json
        with open(CKPT_OUT) as f:
            net.load_weights(json.load(f))
        print('resumed checkpoint', flush=True)

    pool = []
    base_wr, base_ap = evaluate(net.policy_weights(), n=2000)
    best = base_wr
    print(f'baseline greedy vs fleet: win {base_wr*100:.1f}%  place {base_ap:.3f}', flush=True)

    ex = ProcessPoolExecutor(max_workers=args.workers) if args.workers > 1 else None
    seed = 2000

    for it in range(1, args.iters + 1):
        t0 = time.time()
        policy_w = net.policy_weights()
        per = max(1, args.games // max(1, args.workers))

        if ex:
            futures = []
            for _ in range(args.workers):
                seed += 1
                futures.append(ex.submit(rollout_worker,
                    (policy_w, list(pool), per, seed, args.self_prob)))
            games = []
            for f in futures:
                games.extend(f.result())
        else:
            seed += 1
            games = rollout_worker((policy_w, list(pool), args.games, seed, args.self_prob))

        compute_targets(games, args.gamma)
        ppo_update(net, games, args.epochs, args.clip, args.vf, args.ent, args.lr)

        net.save_full(CKPT_OUT)

        if it % 20 == 0:
            pool.append(net.policy_weights())
            if len(pool) > 8:
                pool.pop(0)

        if it % 10 == 0:
            wr, apl = evaluate(net.policy_weights(), n=2000)
            tag = ''
            if wr > best:
                best = wr
                net.save_policy(BEST_OUT)
                net.save_policy(DEPLOY_OUT)
                tag = '  <- new best (saved)'
            wins = sum(1 for _, r in games if r > 0)
            print(f'iter {it:4d}  rollout_win {wins/max(len(games),1)*100:4.1f}%  '
                  f'|  greedy vs fleet: win {wr*100:5.2f}%  place {apl:.3f}  '
                  f'(best {best*100:.2f}%)  {time.time()-t0:.1f}s/it{tag}', flush=True)

    if ex:
        ex.shutdown()
    print(f'done. best policy in {BEST_OUT}', flush=True)


if __name__ == '__main__':
    main()
