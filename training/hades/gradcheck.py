"""Numerical gradient check for ian_folder/hades/net.py.

Builds a scalar loss that routes gradient into every parameter (encoder, trunk,
and all six heads), computes analytic gradients via the manual backward passes,
then compares against central finite differences on a random sample of entries.

    python3 -m ian_folder.hades.gradcheck
"""
import numpy as np

from training.hades.net import TransformerActorCritic, _softmax_rows
from training.hades.event_encode import N_EVENT
from training.hades.features import N_FEATURES
from training.hades.net import NOPE_CTX


def _logsoftmax_ce(logits, idx):
    z = logits - logits.max()
    lse = np.log(np.exp(z).sum())
    return -(z[idx] - lse)


def _sm(logits):
    e = np.exp(logits - logits.max())
    return e / e.sum()


def loss_and_grads(net, window, snap, nope_ctx, targets):
    """Forward + analytic backward. Returns (scalar_loss, grads dict)."""
    a_idx, v_tgt, t_idx, g_idx, p_idx, nope_y = targets
    grads = net.zero_grads()

    hmem, ecache = net.encode(window)
    a2, tcache = net.trunk(hmem, snap)

    pol = net.policy(a2)
    val = net.value(a2)
    tgt = net.target(a2)
    giv = net.give(a2)
    plc = net.place(a2)
    nlogit, ncache = net.nope_logit(a2, nope_ctx)

    loss = (_logsoftmax_ce(pol, a_idx)
            + 0.5 * (val - v_tgt) ** 2
            + _logsoftmax_ce(tgt, t_idx)
            + _logsoftmax_ce(giv, g_idx)
            + _logsoftmax_ce(plc, p_idx))
    sig = 1.0 / (1.0 + np.exp(-nlogit))
    loss += -(nope_y * np.log(sig + 1e-12) + (1 - nope_y) * np.log(1 - sig + 1e-12))

    # ---- backward ----
    da2 = np.zeros_like(a2)
    dpol = _sm(pol); dpol[a_idx] -= 1.0
    da2 += net._lin_head_backward('pol', dpol, a2, grads)
    da2 += net.value_backward(val - v_tgt, a2, grads)
    dtgt = _sm(tgt); dtgt[t_idx] -= 1.0
    da2 += net._lin_head_backward('tgt', dtgt, a2, grads)
    dgiv = _sm(giv); dgiv[g_idx] -= 1.0
    da2 += net._lin_head_backward('give', dgiv, a2, grads)
    dplc = _sm(plc); dplc[p_idx] -= 1.0
    da2 += net._lin_head_backward('place', dplc, a2, grads)
    da2 += net.nope_backward(sig - nope_y, ncache, grads)

    dhmem = net.trunk_backward(da2, tcache, grads)
    net.encode_backward(dhmem, ecache, grads)
    return loss, grads


def loss_only(net, window, snap, nope_ctx, targets):
    a_idx, v_tgt, t_idx, g_idx, p_idx, nope_y = targets
    hmem, _ = net.encode(window)
    a2, _ = net.trunk(hmem, snap)
    pol = net.policy(a2); val = net.value(a2); tgt = net.target(a2)
    giv = net.give(a2); plc = net.place(a2)
    nlogit, _ = net.nope_logit(a2, nope_ctx)
    loss = (_logsoftmax_ce(pol, a_idx) + 0.5 * (val - v_tgt) ** 2
            + _logsoftmax_ce(tgt, t_idx) + _logsoftmax_ce(giv, g_idx)
            + _logsoftmax_ce(plc, p_idx))
    sig = 1.0 / (1.0 + np.exp(-nlogit))
    loss += -(nope_y * np.log(sig + 1e-12) + (1 - nope_y) * np.log(1 - sig + 1e-12))
    return loss


def main():
    rng = np.random.default_rng(1)
    net = TransformerActorCritic(seed=3)
    # Use a non-trivial window length to exercise pooling + attention.
    L = 6
    window = rng.standard_normal((L, N_EVENT))
    snap = rng.standard_normal(N_FEATURES)
    nope_ctx = rng.standard_normal(NOPE_CTX)
    targets = (2, 0.4, 1, 5, 11, 1.0)

    _, grads = loss_and_grads(net, window, snap, nope_ctx, targets)

    eps = 1e-5
    worst = 0.0
    worst_key = None
    n_checked = 0
    for k in net.keys:
        P = net.P[k]
        flat = P.reshape(-1)
        gflat = grads[k].reshape(-1)
        # sample up to 5 indices per parameter
        idxs = rng.choice(flat.size, size=min(5, flat.size), replace=False)
        for i in idxs:
            orig = flat[i]
            flat[i] = orig + eps
            lp = loss_only(net, window, snap, nope_ctx, targets)
            flat[i] = orig - eps
            lm = loss_only(net, window, snap, nope_ctx, targets)
            flat[i] = orig
            num = (lp - lm) / (2 * eps)
            ana = gflat[i]
            # Combined criterion: ignore entries where both grads are ~0
            # (relative error is meaningless on finite-difference noise).
            if abs(num) + abs(ana) < 1e-6:
                n_checked += 1
                continue
            rel = abs(num - ana) / (abs(num) + abs(ana))
            n_checked += 1
            if rel > worst:
                worst = rel; worst_key = (k, int(i), float(num), float(ana))
    print(f'checked {n_checked} entries across {len(net.keys)} params')
    print(f'worst relative error (non-trivial grads): {worst:.2e}  at {worst_key}')
    if worst < 1e-4:
        print('GRADCHECK PASSED')
        return 0
    print('GRADCHECK FAILED')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
