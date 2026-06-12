#!/usr/bin/env python3
"""PPO + BPTT training for Rhino.

All five decision types (action, target, nope, give, place) are trained with
the same PPO + BPTT loop. Each shares the GRU and trunk; only the head weights
differ. Gradients from all heads accumulate into dh_from_mlp and flow back
through the GRU via BPTT.

    python3 -m rhino.train --iters 3000 --workers 6
"""
import argparse, os, sys, time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from training.rhino.net import (GRUActorCritic, GRU_H, ALL_KEYS, N_TARGETS,
                       N_CARD_TYPES, N_BUCKETS)
from training.rhino.rollout import rollout_worker, evaluate
from agents.orangutan_features import N_ACTIONS

HERE      = os.path.dirname(os.path.abspath(__file__))
BEST_OUT  = os.path.join(HERE, 'best_policy.json')
CKPT_OUT  = os.path.join(HERE, 'checkpoint.json')
DEPLOY_OUT = os.path.join(HERE, '..', '..', 'agents', 'rhino_weights.json')

NEG = -1e9


def _masked_softmax(logits, mask):
    z = np.where(mask > 0, logits, NEG); z -= z.max()
    e = np.exp(z) * mask
    return e / (e.sum() + 1e-12)


def _softmax(logits):
    z = logits - logits.max()
    e = np.exp(z)
    return e / (e.sum() + 1e-12)


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(float(x), -20.0, 20.0)))


def compute_targets(games, gamma):
    for gd, reward in games:
        for log_key in ('steps', 'nope_steps', 'give_steps', 'place_steps'):
            steps = gd.get(log_key, [])
            T = len(steps)
            for t in range(T):
                R = reward * (gamma ** (T - 1 - t))
                steps[t]['return'] = R
                steps[t]['advantage'] = R - steps[t]['old_value']


def _ppo_coeff(new_logp, old_logp, adv, clip):
    ratio = float(np.exp(np.clip(new_logp - old_logp, -10.0, 10.0)))
    surr1 = ratio * adv
    surr2 = np.clip(ratio, 1.0 - clip, 1.0 + clip) * adv
    use1 = surr1 <= surr2
    in_range = (1.0 - clip) < ratio < (1.0 + clip)
    coeff = 1.0 if use1 else float(in_range)
    return -(adv * ratio * coeff)   # d(loss) / d(logp), loss = -min(surr1,surr2)


def _entropy_dlogits(P, mask, ent_coef):
    log_P = np.log(P + 1e-12)
    mean_term = float(np.sum(P * (log_P + 1.0) * mask))
    return (-ent_coef) * P * (mean_term - (log_P + 1.0) * mask)


def _game_grads(net, gd, clip, vf_coef, ent_coef):
    event_vecs = [np.array(ev, dtype=np.float32) for ev in gd['event_vecs']]
    hs, gru_caches = net.run_gru(event_vecs)
    E = len(event_vecs)

    all_grads = {k: np.zeros_like(getattr(net, k)) for k in ALL_KEYS}
    dh_acc = {}   # event_count -> accumulated dh

    def acc_dh(ec, dh):
        ec = min(ec, E)
        dh_acc[ec] = dh_acc.get(ec, np.zeros(GRU_H)) + dh

    def acc_g(g):
        for k, v in g.items():
            all_grads[k] += v

    total_n = 0

    # ---- choose_action steps (+ target head) ----
    n = len(gd['steps'])
    total_n += n
    for step in gd['steps']:
        ec = min(step['event_count'], E)
        logits, value, a2, tcache = net.mlp_forward(hs[ec], np.array(step['snapshot']))
        mask = np.array(step['mask'])
        P = _masked_softmax(logits, mask)
        new_logp = float(np.log(P[step['action']] + 1e-12))

        d_logp   = _ppo_coeff(new_logp, step['old_logp'], step['advantage'], clip) / max(n, 1)
        onehot   = np.zeros(N_ACTIONS); onehot[step['action']] = 1.0
        dlogits  = d_logp * (onehot - P) * mask + _entropy_dlogits(P, mask, ent_coef / max(n, 1))
        dvalue   = vf_coef * (value - step['return']) / max(n, 1)

        da2, pol_g = net.policy_backward(dlogits, dvalue, a2)
        acc_g(pol_g)

        if step.get('has_target') and step.get('target_mask') is not None:
            tgt_mask = np.array(step['target_mask'])
            tgt_logits = net.target_forward(a2)
            tgt_P = _masked_softmax(tgt_logits, tgt_mask)
            ta = step['target_action']
            new_tgt_logp = float(np.log(tgt_P[ta] + 1e-12))
            d_tgt_logp  = _ppo_coeff(new_tgt_logp, step['target_logp'],
                                     step['advantage'], clip) / max(n, 1)
            oh_tgt = np.zeros(N_TARGETS); oh_tgt[ta] = 1.0
            dtgt = d_tgt_logp * (oh_tgt - tgt_P) * tgt_mask
            da2_tgt, tgt_g = net.target_backward(dtgt, a2)
            da2 += da2_tgt; acc_g(tgt_g)

        dh, tk_g = net.trunk_backward(da2, tcache)
        acc_g(tk_g); acc_dh(ec, dh)

    # ---- want_to_nope steps ----
    nsteps = gd.get('nope_steps', [])
    nn = len(nsteps)
    total_n += nn
    for step in nsteps:
        ec = min(step['event_count'], E)
        _, value, a2, tcache = net.mlp_forward(hs[ec], np.array(step['snapshot']))
        cn = step['currently_noped']
        logit = net.nope_forward(a2, cn)
        prob = _sigmoid(logit)
        dec = step['decision']
        new_logp = float(np.log(prob + 1e-12) if dec else np.log(1.0 - prob + 1e-12))
        d_logp = _ppo_coeff(new_logp, step['old_logp'], step['advantage'], clip) / max(nn, 1)
        # d(logp)/d(logit) = dec - prob  for binary sigmoid
        d_logit = d_logp * (dec - prob)
        dvalue  = vf_coef * (value - step['return']) / max(nn, 1)
        da2_nope, nope_g = net.nope_backward(d_logit, a2, cn)
        da2_val, val_g   = net.policy_backward(np.zeros(N_ACTIONS), dvalue, a2)
        acc_g(nope_g); acc_g(val_g)
        dh, tk_g = net.trunk_backward(da2_nope + da2_val, tcache)
        acc_g(tk_g); acc_dh(ec, dh)

    # ---- give_card steps ----
    gsteps = gd.get('give_steps', [])
    ng = len(gsteps)
    total_n += ng
    for step in gsteps:
        ec = min(step['event_count'], E)
        _, value, a2, tcache = net.mlp_forward(hs[ec], np.array(step['snapshot']))
        card_mask = np.array(step['card_mask'])
        logits = net.give_forward(a2)
        P = _masked_softmax(logits, card_mask)
        ci = step['decision']
        new_logp = float(np.log(P[ci] + 1e-12))
        d_logp  = _ppo_coeff(new_logp, step['old_logp'], step['advantage'], clip) / max(ng, 1)
        oh = np.zeros(N_CARD_TYPES); oh[ci] = 1.0
        dlogits = d_logp * (oh - P) * card_mask
        dvalue  = vf_coef * (value - step['return']) / max(ng, 1)
        da2_give, give_g = net.give_backward(dlogits, a2)
        da2_val, val_g   = net.policy_backward(np.zeros(N_ACTIONS), dvalue, a2)
        acc_g(give_g); acc_g(val_g)
        dh, tk_g = net.trunk_backward(da2_give + da2_val, tcache)
        acc_g(tk_g); acc_dh(ec, dh)

    # ---- place_kitten steps ----
    psteps = gd.get('place_steps', [])
    np_ = len(psteps)
    total_n += np_
    for step in psteps:
        ec = min(step['event_count'], E)
        _, value, a2, tcache = net.mlp_forward(hs[ec], np.array(step['snapshot']))
        logits = net.place_forward(a2)
        P = _softmax(logits)
        bi = step['decision']
        new_logp = float(np.log(P[bi] + 1e-12))
        d_logp  = _ppo_coeff(new_logp, step['old_logp'], step['advantage'], clip) / max(np_, 1)
        oh = np.zeros(N_BUCKETS); oh[bi] = 1.0
        dlogits = d_logp * (oh - P)
        dvalue  = vf_coef * (value - step['return']) / max(np_, 1)
        da2_place, place_g = net.place_backward(dlogits, a2)
        da2_val, val_g     = net.policy_backward(np.zeros(N_ACTIONS), dvalue, a2)
        acc_g(place_g); acc_g(val_g)
        dh, tk_g = net.trunk_backward(da2_place + da2_val, tcache)
        acc_g(tk_g); acc_dh(ec, dh)

    # ---- BPTT through GRU ----
    dh_curr = dh_acc.get(E, np.zeros(GRU_H))
    for i in range(E - 1, -1, -1):
        dh_prev, gru_g = net.gru_step_backward(dh_curr, gru_caches[i])
        acc_g(gru_g)
        dh_curr = dh_prev + dh_acc.get(i, np.zeros(GRU_H))

    return all_grads, max(total_n, 1)


def ppo_update(net, games, epochs, clip, vf_coef, ent_coef, lr):
    import random
    indices = list(range(len(games)))
    for _ in range(epochs):
        random.shuffle(indices)
        for i in indices:
            gd, _ = games[i]
            grads, _ = _game_grads(net, gd, clip, vf_coef, ent_coef)
            net.step(grads, lr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--iters',     type=int,   default=3000)
    ap.add_argument('--games',     type=int,   default=256)
    ap.add_argument('--workers',   type=int,   default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument('--epochs',    type=int,   default=2)
    ap.add_argument('--clip',      type=float, default=0.2)
    ap.add_argument('--vf',        type=float, default=0.5)
    ap.add_argument('--ent',       type=float, default=0.01)
    ap.add_argument('--lr',        type=float, default=1e-4)
    ap.add_argument('--gamma',     type=float, default=0.997)
    ap.add_argument('--self_prob', type=float, default=0.4)
    ap.add_argument('--resume',    action='store_true')
    args = ap.parse_args()

    net = GRUActorCritic()
    if args.resume and os.path.exists(CKPT_OUT):
        import json
        with open(CKPT_OUT) as f: net.load_weights(json.load(f))
        print('resumed checkpoint', flush=True)

    pool = []
    base_wr, base_ap = evaluate(net.policy_weights(), n=2000)
    best = base_wr
    print(f'baseline greedy vs fleet: win {base_wr*100:.1f}%  place {base_ap:.3f}', flush=True)

    ex   = ProcessPoolExecutor(max_workers=args.workers) if args.workers > 1 else None
    seed = 2000

    for it in range(1, args.iters + 1):
        t0 = time.time()
        pw  = net.policy_weights()
        per = max(1, args.games // max(1, args.workers))

        if ex:
            futs = [ex.submit(rollout_worker, (pw, list(pool), per, seed + w, args.self_prob))
                    for w in range(args.workers)]
            seed += args.workers
            games = [g for f in futs for g in f.result()]
        else:
            seed += 1
            games = rollout_worker((pw, list(pool), args.games, seed, args.self_prob))

        compute_targets(games, args.gamma)
        ppo_update(net, games, args.epochs, args.clip, args.vf, args.ent, args.lr)
        net.save_full(CKPT_OUT)

        if it % 20 == 0:
            pool.append(net.policy_weights())
            if len(pool) > 8: pool.pop(0)

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

    if ex: ex.shutdown()
    print(f'done. best policy in {BEST_OUT}', flush=True)


if __name__ == '__main__':
    main()
