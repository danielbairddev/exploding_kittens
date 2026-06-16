#!/usr/bin/env python3
"""PPO + BPTT ian_folder for Gabriel — trained to die FIRST.

Gabriel uses the same GRU-128 architecture as Elephant, but the reward is
inverted: +1 when Gabriel is the first player to explode, 0 otherwise.

    python3 -m ian_folder.gabriel.train --iters 3000 --workers 6
"""
import argparse, os, sys, time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from training.elephant.net import (GRUActorCritic, GRU_H, ALL_KEYS, N_TARGETS,
                                    N_CARD_TYPES, N_BUCKETS)
from training.gabriel.rollout import rollout_worker, evaluate
from training.elephant.train import (compute_targets, _ppo_coeff, _entropy_dlogits,
                                      _game_grads, _grads_chunk, ppo_update,
                                      _masked_softmax, _softmax, _sigmoid)
from agents.orangutan_features import N_ACTIONS

HERE      = os.path.dirname(os.path.abspath(__file__))
BEST_OUT  = os.path.join(HERE, 'best_policy.json')
CKPT_OUT  = os.path.join(HERE, 'checkpoint.json')
DEPLOY_OUT = os.path.join(HERE, '..', '..', 'agents', 'gabriel_weights.json')
BESTS_LOG = os.path.join(HERE, 'bests.jsonl')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--iters',     type=int,   default=999999)
    ap.add_argument('--games',     type=int,   default=256)
    ap.add_argument('--workers',   type=int,   default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument('--epochs',    type=int,   default=1)
    ap.add_argument('--clip',      type=float, default=0.2)
    ap.add_argument('--vf',        type=float, default=0.5)
    ap.add_argument('--ent',       type=float, default=0.01)
    ap.add_argument('--lr',        type=float, default=1e-4)
    ap.add_argument('--gamma',     type=float, default=0.997)
    ap.add_argument('--self_prob', type=float, default=0.1,
                    help='prob of using past Gabriel as opponent (low — we want fleet pressure)')
    ap.add_argument('--patience',  type=int,   default=500)
    ap.add_argument('--resume',    action='store_true')
    args = ap.parse_args()

    net = GRUActorCritic()
    if args.resume and os.path.exists(CKPT_OUT):
        import json
        with open(CKPT_OUT) as f: net.load_weights(json.load(f))
        print('resumed checkpoint', flush=True)

    pool = []
    base_rate = evaluate(net.policy_weights(), n=2000)
    best = base_rate
    print(f'baseline greedy vs fleet: first-death {base_rate*100:.1f}%', flush=True)

    ex   = ProcessPoolExecutor(max_workers=args.workers) if args.workers > 1 else None
    seed = 7000
    no_improve = 0

    for it in range(1, args.iters + 1):
        t0 = time.time()
        pw  = net.policy_weights()
        per = max(1, args.games // max(1, args.workers))

        if ex:
            futs = [ex.submit(rollout_worker, (pw, list(pool), per, seed + w, args.self_prob))
                    for w in range(args.workers)]
            seed += args.workers
            t_rollout = time.time()
            games = [g for f in futs for g in f.result()]
        else:
            seed += 1
            t_rollout = time.time()
            games = rollout_worker((pw, list(pool), args.games, seed, args.self_prob))

        t_update = time.time()
        compute_targets(games, args.gamma)
        ppo_update(net, games, args.epochs, args.clip, args.vf, args.ent, args.lr, ex=ex)
        t_done = time.time()
        net.save_full(CKPT_OUT)

        if it % 20 == 0:
            pool.append(net.policy_weights())
            if len(pool) > 8: pool.pop(0)

        if it % 20 == 0:
            rate = evaluate(net.policy_weights(), n=2000, ex=ex)
            tag = ''
            if rate > best:
                best = rate; no_improve = 0
                net.save_policy(BEST_OUT)
                net.save_policy(DEPLOY_OUT)
                tag = '  <- new best (saved)'
                import json as _json
                with open(BESTS_LOG, 'a') as _f:
                    _f.write(_json.dumps({'iter': it, 'first_death': round(rate*100,2),
                                          't': int(time.time())}) + '\n')
            else:
                no_improve += 1
            rollout_fd = sum(1 for _, r in games if r > 0)
            print(f'iter {it:4d}  rollout_fd {rollout_fd/max(len(games),1)*100:4.1f}%  '
                  f'|  greedy vs fleet: first-death {rate*100:5.2f}%  '
                  f'(best {best*100:.2f}%)  {time.time()-t0:.1f}s/it'
                  f'  [rollout={t_update-t_rollout:.1f}s  update={t_done-t_update:.1f}s]{tag}',
                  flush=True)
            if no_improve >= args.patience:
                print(f'stalled: no improvement in {no_improve} evals. stopping.', flush=True)
                break

    if ex: ex.shutdown()
    print(f'done. best policy in {BEST_OUT}', flush=True)


if __name__ == '__main__':
    main()
