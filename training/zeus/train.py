#!/usr/bin/env python3
"""PPO ian_folder for Zeus — the win-maximising Transformer (Hades's twin).

Reuses Hades's architecture and PPO machinery wholesale (ian_folder.hades.net +
ian_folder.hades.train); only the rollout reward (+1 win / -1 loss) and the metric
(win rate, HIGHER is better) differ. Single phase vs the competitive fleet with
self-play — no anti-logic curriculum.

    python3 -m ian_folder.zeus.train --workers 6
    python3 -m ian_folder.zeus.train --resume --workers 6
"""
import argparse, json, os, sys, time
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from training.hades.net import TransformerActorCritic
from training.hades.train import compute_targets, ppo_update, _ent_coef, PLACE_ENT, TGT_ENT
from training.zeus.rollout import rollout_worker, evaluate


def _aux_ent(it, args):
    """Anneal the place/target head entropy from full strength down to 1/10th over
    --aux_ent_decay_iters. A fixed-high coefficient (the first fix attempt) held
    placement near-uniform forever and capped win rate below the collapsed-but-rigid
    baseline; annealing lets the heads explore early, then sharpen so the learned
    greedy placement/targeting can actually beat 'always top / always seat-4'."""
    if args.aux_ent_decay_iters <= 0:
        frac = 1.0
    else:
        frac = min(1.0, it / args.aux_ent_decay_iters)
    scale = 1.0 - 0.9 * frac            # 1.0 -> 0.1
    return PLACE_ENT * scale, TGT_ENT * scale

HERE       = os.path.dirname(os.path.abspath(__file__))
BEST_OUT   = os.path.join(HERE, 'best_policy.json')
CKPT_OUT   = os.path.join(HERE, 'checkpoint.json')
DEPLOY_OUT = os.path.join(HERE, '..', '..', 'agents', 'zeus_weights.json')
BESTS_LOG  = os.path.join(HERE, 'bests.jsonl')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--iters',     type=int,   default=999999)
    ap.add_argument('--games',     type=int,   default=256)
    ap.add_argument('--workers',   type=int,   default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument('--epochs',    type=int,   default=1)
    ap.add_argument('--clip',      type=float, default=0.2)
    ap.add_argument('--vf',        type=float, default=0.5)
    ap.add_argument('--ent_start', type=float, default=0.02)
    ap.add_argument('--ent_end',   type=float, default=0.005)
    ap.add_argument('--ent_decay_iters', type=int, default=400)
    ap.add_argument('--aux_ent_decay_iters', type=int, default=400,
                    help='iters to anneal place/target head entropy from full to 1/10')
    ap.add_argument('--lr',        type=float, default=1e-4)
    ap.add_argument('--gamma',     type=float, default=0.99)
    ap.add_argument('--self_prob', type=float, default=0.3)
    ap.add_argument('--eval_n',    type=int,   default=2000)
    ap.add_argument('--eval_every', type=int,  default=20)
    ap.add_argument('--patience',  type=int,   default=500)
    ap.add_argument('--target_winrate', type=float, default=0.0,
                    help='stop once greedy win rate >= this. 0 disables.')
    ap.add_argument('--resume',    action='store_true')
    args = ap.parse_args()

    net = TransformerActorCritic()
    if args.resume and os.path.exists(CKPT_OUT):
        with open(CKPT_OUT) as f:
            net.load_weights(json.load(f))
        print('resumed checkpoint', flush=True)

    base = evaluate(net.weights(), n=args.eval_n)
    best = base  # higher win rate is better
    print(f'baseline greedy vs eval-fleet: win {base*100:.2f}%', flush=True)

    # Deploy floor: never regress the live bot. After a head re-init the resumed
    # checkpoint evaluates LOWER than deployed Zeus, so the bar to overwrite
    # agents/zeus_weights.json must be the *deployed* net's win rate (same eval
    # seed -> directly comparable), not the checkpoint's. Only a genuinely-better
    # net ships.
    if os.path.exists(DEPLOY_OUT):
        with open(DEPLOY_OUT) as f:
            deployed_w = json.load(f)
        floor = evaluate(deployed_w, n=args.eval_n)
        if floor > best:
            best = floor
        print(f'deploy floor (live Zeus): win {floor*100:.2f}%  -> must beat {best*100:.2f}% to ship',
              flush=True)

    ex = ProcessPoolExecutor(max_workers=args.workers) if args.workers > 1 else None
    pool = []
    seed = 5000
    no_improve = 0

    for it in range(1, args.iters + 1):
        t0 = time.time()
        ent = _ent_coef(it, args)
        place_ent, tgt_ent = _aux_ent(it, args)
        pw = net.weights()
        per = max(1, args.games // max(1, args.workers))

        if ex:
            futs = [ex.submit(rollout_worker, (pw, list(pool), per, seed + w, args.self_prob))
                    for w in range(args.workers)]
            seed += args.workers
            t_roll = time.time()
            games = [g for f in futs for g in f.result()]
        else:
            seed += 1
            t_roll = time.time()
            games = rollout_worker((pw, list(pool), args.games, seed, args.self_prob))

        t_upd = time.time()
        compute_targets(games, args.gamma)
        ppo_update(net, games, args.epochs, args.clip, args.vf, ent, args.lr, ex=ex,
                   place_ent=place_ent, tgt_ent=tgt_ent)
        t_done = time.time()
        net.save(CKPT_OUT)

        if it % args.eval_every == 0:
            pool.append(net.weights())
            if len(pool) > 5:
                pool.pop(0)
            wr = evaluate(net.weights(), n=args.eval_n, ex=ex)
            tag = ''
            if wr > best:
                best = wr; no_improve = 0
                net.save(BEST_OUT); net.save(DEPLOY_OUT)
                tag = '  <- new best (saved)'
                with open(BESTS_LOG, 'a') as fp:
                    fp.write(json.dumps({'iter': it, 'win': round(wr*100, 2),
                                         't': int(time.time())}) + '\n')
            else:
                no_improve += 1
            won = sum(1 for _, r in games if r > 0)
            print(f'iter {it:4d}  rollout_win {won/max(len(games),1)*100:4.1f}%  ent {ent:.3f}  '
                  f'pl_ent {place_ent:.3f}  |  '
                  f'greedy win {wr*100:5.2f}%  (best {best*100:.2f}%)  '
                  f'{time.time()-t0:.1f}s/it  [roll={t_upd-t_roll:.1f}s upd={t_done-t_upd:.1f}s]{tag}',
                  flush=True)
            if args.target_winrate > 0 and wr >= args.target_winrate:
                print(f'TARGET REACHED: win {wr*100:.2f}% >= {args.target_winrate*100:.2f}%. stopping.',
                      flush=True)
                break
            if no_improve >= args.patience:
                print(f'stalled: no improvement in {no_improve} evals. stopping.', flush=True)
                break

    if ex:
        ex.shutdown()
    print(f'done. best policy in {BEST_OUT}', flush=True)


if __name__ == '__main__':
    main()
