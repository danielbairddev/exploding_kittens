#!/usr/bin/env python3
"""One-time surgery: break the collapsed place (and target) heads on the deployed
Zeus, then write the result as the resume checkpoint.

The spot-check found the place head fully collapsed (100% top-of-deck, zero state
dependence) and the target head heavily skewed (~88% one seat). Both saturated
because their gradient signal is too weak to escape a degenerate basin. Re-randomising
just those two output layers (everything else — encoder, trunk, policy/value/give/nope
heads — is preserved) drops them back into a high-entropy state; the new entropy
regularisers in train.py (PLACE_ENT / TGT_ENT) then keep them from re-collapsing while
PPO re-learns state-dependent placement/targeting.

    python3 -m training.zeus.reinit_heads
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
from training.hades.net import TransformerActorCritic, A_CORE, N_PLACE, N_TARGETS

HERE      = os.path.dirname(os.path.abspath(__file__))
DEPLOY    = os.path.join(HERE, '..', '..', 'agents', 'zeus_weights.json')
CKPT_OUT  = os.path.join(HERE, 'checkpoint.json')


def main():
    with open(DEPLOY) as f:
        w = json.load(f)

    net = TransformerActorCritic()
    net.load_weights(w)

    rng = np.random.default_rng(1234)
    scale = np.sqrt(0.01)   # same small init as the heads in net.__init__
    net.P['place_W'][...] = rng.standard_normal((N_PLACE, A_CORE)) * scale
    net.P['place_b'][...] = 0.0
    net.P['tgt_W'][...]   = rng.standard_normal((N_TARGETS, A_CORE)) * scale
    net.P['tgt_b'][...]   = 0.0
    # clear Adam moments for the reinitialised params so they move freely
    for k in ('place_W', 'place_b', 'tgt_W', 'tgt_b'):
        net._m[k] = np.zeros_like(net.P[k])
        net._v[k] = np.zeros_like(net.P[k])

    net.save(CKPT_OUT)
    # Do NOT touch agents/zeus_weights.json (stays deployed) or best_policy.json
    # (the trainer's deploy floor is the live net's win rate, so it only ships a
    # net that genuinely beats deployed Zeus — see train.py).
    print(f'reinitialised place + target heads; wrote {CKPT_OUT}')
    print('encoder/trunk/policy/value/give/nope heads preserved from deployed Zeus.')


if __name__ == '__main__':
    main()
