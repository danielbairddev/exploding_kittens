#!/usr/bin/env python3
"""PPO ian_folder for Hades — the Transformer anti-agent (HADES_PLAN.md §4-§5).

All five decision types (action+target, nope, give, place) plus the value critic
are trained with one PPO loop. Each decision step re-encodes its own event window
through the Transformer (there is no cross-step recurrence), so gradients of the
shared parameters simply accumulate across steps and games.

Metric: survival rate vs the eval fleet — LOWER is better (target < 2%).

    python3 -m ian_folder.hades.train --workers 6
    python3 -m ian_folder.hades.train --resume --workers 6
    python3 -m ian_folder.hades.train --phase bootstrap --iters 200   # phase 1 only
"""
import argparse, json, math, os, sys, time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from training.hades.net import (TransformerActorCritic, CONTEXT_WINDOW, N_ACTIONS,
                                N_TARGETS, N_CARD_TYPES, N_PLACE)
from training.hades.rollout import rollout_worker, evaluate
from training.elephant.train import _ppo_coeff, _entropy_dlogits, _masked_softmax, _softmax, _sigmoid

HERE       = os.path.dirname(os.path.abspath(__file__))
BEST_OUT   = os.path.join(HERE, 'best_policy.json')
CKPT_OUT   = os.path.join(HERE, 'checkpoint.json')
DEPLOY_OUT = os.path.join(HERE, '..', '..', 'agents', 'hades_weights.json')
BESTS_LOG  = os.path.join(HERE, 'bests.jsonl')

HUBER_DELTA = 1.0
NOPE_ENT = 0.15   # entropy weight on the binary nope head (anti-collapse)
# Place/target heads collapse for the same reason nope did: their decision rarely
# flips the win/loss outcome, so PPO gives them almost no gradient and they
# saturate to one output (place->always top-of-deck, target->always one seat). A
# persistent softmax-entropy regulariser is a restoring force toward uniform over
# the *valid* (masked) choices, keeping them state-dependent so the sparse outcome
# signal can still shape them. Paired with a one-time head re-init (reinit_heads.py).
PLACE_ENT = 0.05  # entropy weight on the 50-way place softmax
TGT_ENT   = 0.03  # entropy weight on the 5-way target softmax


def _huber_grad(err):
    return float(np.clip(err, -HUBER_DELTA, HUBER_DELTA))


def compute_targets(games, gamma):
    """Discounted return + advantage for every logged step."""
    for gd, reward in games:
        for log_key in ('steps', 'nope_steps', 'give_steps', 'place_steps'):
            steps = gd.get(log_key, [])
            T = len(steps)
            for t in range(T):
                R = reward * (gamma ** (T - 1 - t))
                steps[t]['return'] = R
                steps[t]['advantage'] = R - steps[t]['old_value']


def _window_for(event_vecs, ec):
    lo = max(0, ec - CONTEXT_WINDOW)
    return event_vecs[lo:ec]


def _game_grads(net, gd, clip, vf_coef, ent_coef, place_ent=PLACE_ENT, tgt_ent=TGT_ENT):
    grads = net.zero_grads()
    event_vecs = gd['event_vecs']

    def fwd(step):
        window = _window_for(event_vecs, step['event_count'])
        hmem, ec_cache = net.encode(window)
        a2, t_cache = net.trunk(hmem, np.asarray(step['snapshot'], dtype=np.float64))
        return a2, t_cache, ec_cache

    def back(da2, t_cache, ec_cache):
        dhmem = net.trunk_backward(da2, t_cache, grads)
        net.encode_backward(dhmem, ec_cache, grads)

    # ---- policy (+ target) ----
    steps = gd['steps']; n = max(len(steps), 1)
    for step in steps:
        a2, tc, ec = fwd(step)
        value = net.value(a2)
        logits = net.policy(a2)
        mask = np.array(step['mask'])
        P = _masked_softmax(logits, mask)
        new_logp = float(np.log(P[step['action']] + 1e-12))
        d_logp = _ppo_coeff(new_logp, step['old_logp'], step['advantage'], clip) / n
        onehot = np.zeros(N_ACTIONS); onehot[step['action']] = 1.0
        dlogits = d_logp * (onehot - P) * mask + _entropy_dlogits(P, mask, ent_coef / n)
        dvalue = vf_coef * _huber_grad(value - step['return']) / n

        da2 = net._lin_head_backward('pol', dlogits, a2, grads)
        da2 += net.value_backward(dvalue, a2, grads)

        if step.get('has_target') and step.get('target_mask') is not None:
            tgt_mask = np.array(step['target_mask'])
            tlogits = net.target(a2)
            tP = _masked_softmax(tlogits, tgt_mask)
            ta = step['target_action']
            new_tlogp = float(np.log(tP[ta] + 1e-12))
            d_tlogp = _ppo_coeff(new_tlogp, step['target_logp'], step['advantage'], clip) / n
            oh = np.zeros(N_TARGETS); oh[ta] = 1.0
            dtgt = d_tlogp * (oh - tP) * tgt_mask + _entropy_dlogits(tP, tgt_mask, tgt_ent / n)
            da2 += net._lin_head_backward('tgt', dtgt, a2, grads)
        back(da2, tc, ec)

    # ---- nope ----
    nsteps = gd.get('nope_steps', []); nn = max(len(nsteps), 1)
    for step in nsteps:
        a2, tc, ec = fwd(step)
        value = net.value(a2)
        logit, ncache = net.nope_logit(a2, np.asarray(step['nope_ctx'], dtype=np.float64))
        prob = _sigmoid(logit)
        dec = step['decision']
        new_logp = float(np.log(prob + 1e-12) if dec else np.log(1.0 - prob + 1e-12))
        d_logp = _ppo_coeff(new_logp, step['old_logp'], step['advantage'], clip) / nn
        d_logit = d_logp * (dec - prob)
        # Entropy regulariser on the binary nope head: a restoring force toward
        # p=0.5 (zero exactly at 0.5) so the head can't collapse to always-nope
        # and the targeting features + nope cost can actually shape it.
        p_c = min(max(prob, 1e-6), 1.0 - 1e-6)
        dH_dlogit = p_c * (1.0 - p_c) * np.log((1.0 - p_c) / p_c)
        d_logit += (-NOPE_ENT / nn) * dH_dlogit
        dvalue = vf_coef * _huber_grad(value - step['return']) / nn
        da2 = net.nope_backward(d_logit, ncache, grads)
        da2 += net.value_backward(dvalue, a2, grads)
        back(da2, tc, ec)

    # ---- give ----
    gsteps = gd.get('give_steps', []); ng = max(len(gsteps), 1)
    for step in gsteps:
        a2, tc, ec = fwd(step)
        value = net.value(a2)
        card_mask = np.array(step['card_mask'])
        logits = net.give(a2)
        P = _masked_softmax(logits, card_mask)
        ci = step['decision']
        new_logp = float(np.log(P[ci] + 1e-12))
        d_logp = _ppo_coeff(new_logp, step['old_logp'], step['advantage'], clip) / ng
        oh = np.zeros(N_CARD_TYPES); oh[ci] = 1.0
        dlogits = d_logp * (oh - P) * card_mask
        dvalue = vf_coef * _huber_grad(value - step['return']) / ng
        da2 = net._lin_head_backward('give', dlogits, a2, grads)
        da2 += net.value_backward(dvalue, a2, grads)
        back(da2, tc, ec)

    # ---- place ----
    psteps = gd.get('place_steps', []); npl = max(len(psteps), 1)
    for step in psteps:
        a2, tc, ec = fwd(step)
        value = net.value(a2)
        mask = np.array(step['place_mask'])
        logits = net.place(a2)
        P = _masked_softmax(logits, mask)
        bi = step['decision']
        new_logp = float(np.log(P[bi] + 1e-12))
        d_logp = _ppo_coeff(new_logp, step['old_logp'], step['advantage'], clip) / npl
        oh = np.zeros(N_PLACE); oh[bi] = 1.0
        dlogits = d_logp * (oh - P) * mask + _entropy_dlogits(P, mask, place_ent / npl)
        dvalue = vf_coef * _huber_grad(value - step['return']) / npl
        da2 = net._lin_head_backward('place', dlogits, a2, grads)
        da2 += net.value_backward(dvalue, a2, grads)
        back(da2, tc, ec)

    return grads


def _grads_chunk(args):
    weights, chunk, clip, vf, ent, place_ent, tgt_ent = args
    net = TransformerActorCritic()
    net.load_weights(weights)
    sum_grads = None
    for gd, _ in chunk:
        g = _game_grads(net, gd, clip, vf, ent, place_ent, tgt_ent)
        if sum_grads is None:
            sum_grads = {k: v.copy() for k, v in g.items()}
        else:
            for k in sum_grads:
                sum_grads[k] += g[k]
    return sum_grads, len(chunk)


def ppo_update(net, games, epochs, clip, vf, ent, lr, ex=None,
               place_ent=PLACE_ENT, tgt_ent=TGT_ENT):
    import random
    idxs = list(range(len(games)))
    for _ in range(epochs):
        random.shuffle(idxs)
        shuffled = [games[i] for i in idxs]
        if ex is None:
            for gd, _ in shuffled:
                net.step(_game_grads(net, gd, clip, vf, ent, place_ent, tgt_ent), lr)
        else:
            workers = ex._max_workers
            cs = max(1, math.ceil(len(shuffled) / workers))
            chunks = [shuffled[i:i+cs] for i in range(0, len(shuffled), cs)]
            w = net.weights()
            futs = [ex.submit(_grads_chunk, (w, c, clip, vf, ent, place_ent, tgt_ent)) for c in chunks]
            sum_grads, n_total = None, 0
            for f in futs:
                g, n = f.result()
                if g is None:
                    continue
                n_total += n
                if sum_grads is None:
                    sum_grads = {k: v.copy() for k, v in g.items()}
                else:
                    for k in sum_grads:
                        sum_grads[k] += g[k]
            if sum_grads and n_total > 0:
                net.step({k: v / n_total for k, v in sum_grads.items()}, lr)


def _ent_coef(it, args):
    """Linear decay from --ent_start to --ent_end over --ent_decay_iters."""
    if args.ent_decay_iters <= 0:
        return args.ent_end
    frac = min(1.0, it / args.ent_decay_iters)
    return args.ent_start + frac * (args.ent_end - args.ent_start)


def _phase_for(it, args):
    if args.phase != 'auto':
        return args.phase
    return 'bootstrap' if it <= args.bootstrap_iters else 'crucible'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--iters',     type=int,   default=999999)
    ap.add_argument('--games',     type=int,   default=256)
    ap.add_argument('--workers',   type=int,   default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument('--epochs',    type=int,   default=1)
    ap.add_argument('--clip',      type=float, default=0.2)
    ap.add_argument('--vf',        type=float, default=0.5)
    ap.add_argument('--ent_start', type=float, default=0.05)
    ap.add_argument('--ent_end',   type=float, default=0.01)
    ap.add_argument('--ent_decay_iters', type=int, default=400)
    ap.add_argument('--lr',        type=float, default=1e-4)
    ap.add_argument('--gamma',     type=float, default=0.99)
    ap.add_argument('--self_prob', type=float, default=0.2)
    ap.add_argument('--phase',     choices=['auto', 'bootstrap', 'crucible'], default='auto')
    ap.add_argument('--bootstrap_iters', type=int, default=100)
    ap.add_argument('--eval_n',    type=int,   default=2000)
    ap.add_argument('--eval_every', type=int,  default=20)
    ap.add_argument('--patience',  type=int,   default=500)
    ap.add_argument('--target_survival', type=float, default=0.0,
                    help='stop once greedy survival <= this (e.g. 0.02). 0 disables.')
    ap.add_argument('--resume',    action='store_true')
    args = ap.parse_args()

    net = TransformerActorCritic()
    if args.resume and os.path.exists(CKPT_OUT):
        with open(CKPT_OUT) as f:
            net.load_weights(json.load(f))
        print('resumed checkpoint', flush=True)

    base = evaluate(net.weights(), n=args.eval_n)
    best = base  # lower survival is better
    print(f'baseline greedy vs eval-fleet: survival {base*100:.2f}%', flush=True)

    ex = ProcessPoolExecutor(max_workers=args.workers) if args.workers > 1 else None
    pool = []
    seed = 7000
    no_improve = 0

    for it in range(1, args.iters + 1):
        t0 = time.time()
        phase = _phase_for(it, args)
        ent = _ent_coef(it, args)
        pw = net.weights()
        per = max(1, args.games // max(1, args.workers))

        if ex:
            futs = [ex.submit(rollout_worker, (pw, list(pool), per, seed + w, phase, args.self_prob))
                    for w in range(args.workers)]
            seed += args.workers
            t_roll = time.time()
            games = [g for f in futs for g in f.result()]
        else:
            seed += 1
            t_roll = time.time()
            games = rollout_worker((pw, list(pool), args.games, seed, phase, args.self_prob))

        t_upd = time.time()
        compute_targets(games, args.gamma)
        ppo_update(net, games, args.epochs, args.clip, args.vf, ent, args.lr, ex=ex)
        t_done = time.time()
        net.save(CKPT_OUT)

        if it % args.eval_every == 0:
            pool.append(net.weights())
            if len(pool) > 5:
                pool.pop(0)
            surv = evaluate(net.weights(), n=args.eval_n, ex=ex)
            tag = ''
            if surv < best:
                best = surv; no_improve = 0
                net.save(BEST_OUT); net.save(DEPLOY_OUT)
                tag = '  <- new best (saved)'
                with open(BESTS_LOG, 'a') as fp:
                    fp.write(json.dumps({'iter': it, 'survival': round(surv*100, 2),
                                         'phase': phase, 't': int(time.time())}) + '\n')
            else:
                no_improve += 1
            died = sum(1 for _, r in games if r > 0)
            print(f'iter {it:4d}  [{phase}]  rollout_death {died/max(len(games),1)*100:4.1f}%  '
                  f'ent {ent:.3f}  |  greedy survival {surv*100:5.2f}%  (best {best*100:.2f}%)  '
                  f'{time.time()-t0:.1f}s/it  [roll={t_upd-t_roll:.1f}s upd={t_done-t_upd:.1f}s]{tag}',
                  flush=True)
            if args.target_survival > 0 and surv <= args.target_survival:
                print(f'TARGET REACHED: survival {surv*100:.2f}% <= '
                      f'{args.target_survival*100:.2f}%. stopping.', flush=True)
                break
            if no_improve >= args.patience:
                print(f'stalled: no improvement in {no_improve} evals. stopping.', flush=True)
                break

    if ex:
        ex.shutdown()
    print(f'done. best policy in {BEST_OUT}', flush=True)


if __name__ == '__main__':
    main()
