"""Transformer actor-critic for Hades (numpy, manual forward + backward).

Replaces the GRU memory module of the Orpheus/Gabriel family with a Transformer
encoder (HADES_PLAN.md §2-§3). Everything is hand-differentiated and validated
by ian_folder/hades/gradcheck.py.

Design note — no cross-step recurrence:
  A GRU shares one hidden-state chain across all decision steps in a game, which
  forces the BPTT machinery in the Elephant trainer. The Transformer is purely
  feed-forward over the event window, so each decision step is an independent
  forward/backward over its own window (the last N events up to that step). We
  simply accumulate gradients of the shared parameters across all steps/games.

Architecture:
  encoder: 3 x PreLN TransformerLayer (d=128, heads=4, ff=256) + final LN
  pool:    concat(mean over tokens, last token) -> H_mem in R^256
  trunk:   concat(H_mem 256, snap 134)=390 -> 256 -> 128, each LN + Mish
  heads:   policy(8) value(1) target(5) give(14) place(50)
           nope: concat(A_core 128, C_nope 24)=152 -> 64 (Mish) -> 1 (sigmoid)
"""
import json
import os
import numpy as np

from training.hades.event_encode import N_EVENT, CONTEXT_WINDOW
from training.hades.features import N_FEATURES as N_SNAP

# ---- dimensions ----
D_MODEL = 128
N_HEADS = 4
HEAD_DIM = D_MODEL // N_HEADS     # 32
FF_DIM = 256
N_LAYERS = 3
H_MEM = 2 * D_MODEL              # 256 (mean ++ last)

TRUNK_IN = H_MEM + N_SNAP       # 390
TR_H1, TR_H2 = 256, 128
A_CORE = TR_H2                  # 128

N_ACTIONS = 8
N_TARGETS = 5
N_CARD_TYPES = 14               # matches features.N_CARD
N_PLACE = 50                    # exact deck-depth softmax (deck < 50)

NOPE_CTX = 24                   # action_type(8)+card(14)+targets_me(1)+already_noped(1)
NOPE_IN = A_CORE + NOPE_CTX     # 152
NOPE_H = 64

EPS = 1e-5


# ======================================================================
# elementwise helpers
# ======================================================================

def _softmax_rows(x):
    x = x - x.max(axis=-1, keepdims=True)
    e = np.exp(x)
    return e / (e.sum(axis=-1, keepdims=True) + 1e-12)


def _mish(x):
    sp = np.logaddexp(0.0, x)         # softplus, stable
    t = np.tanh(sp)
    return x * t, (x, sp, t)


def _mish_back(dy, cache):
    x, sp, t = cache
    sig = 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))
    dx = t + x * (1.0 - t * t) * sig
    return dy * dx


def _ln_forward(x, gamma, beta):
    """Row-wise LayerNorm. x: [..., d]."""
    mu = x.mean(axis=-1, keepdims=True)
    xc = x - mu
    var = (xc * xc).mean(axis=-1, keepdims=True)
    inv = 1.0 / np.sqrt(var + EPS)
    xhat = xc * inv
    out = gamma * xhat + beta
    return out, (xhat, inv, gamma)


def _ln_backward(dout, cache):
    xhat, inv, gamma = cache
    d = xhat.shape[-1]
    dgamma = (dout * xhat).reshape(-1, d).sum(axis=0)
    dbeta = dout.reshape(-1, d).sum(axis=0)
    dxhat = dout * gamma
    # standard layernorm input grad
    mean_dxhat = dxhat.mean(axis=-1, keepdims=True)
    mean_dxhat_xhat = (dxhat * xhat).mean(axis=-1, keepdims=True)
    dx = inv * (dxhat - mean_dxhat - xhat * mean_dxhat_xhat)
    return dx, dgamma, dbeta


def _pos_encoding(L, d):
    """Fixed sinusoidal absolute positional encoding [L, d]."""
    pos = np.arange(L)[:, None]
    i = np.arange(d)[None, :]
    angle = pos / np.power(10000.0, (2 * (i // 2)) / d)
    pe = np.zeros((L, d))
    pe[:, 0::2] = np.sin(angle[:, 0::2])
    pe[:, 1::2] = np.cos(angle[:, 1::2])
    return pe


# ======================================================================
# network
# ======================================================================

class TransformerActorCritic:
    def __init__(self, seed=0):
        rng = np.random.default_rng(seed)
        self.P = {}

        def lin(name, out_d, in_d, scale=None):
            s = scale if scale is not None else np.sqrt(2.0 / in_d)
            self.P[name + '_W'] = rng.standard_normal((out_d, in_d)) * s
            self.P[name + '_b'] = np.zeros(out_d)

        def ln(name, d):
            self.P[name + '_g'] = np.ones(d)
            self.P[name + '_b'] = np.zeros(d)

        # input projection: 64-dim event -> d_model
        lin('inp', D_MODEL, N_EVENT)

        # transformer layers (pre-LN)
        for l in range(N_LAYERS):
            p = f'L{l}_'
            ln(p + 'ln1', D_MODEL)
            lin(p + 'q', D_MODEL, D_MODEL)
            lin(p + 'k', D_MODEL, D_MODEL)
            lin(p + 'v', D_MODEL, D_MODEL)
            lin(p + 'o', D_MODEL, D_MODEL)
            ln(p + 'ln2', D_MODEL)
            lin(p + 'ff1', FF_DIM, D_MODEL)
            lin(p + 'ff2', D_MODEL, FF_DIM)
        ln('lnf', D_MODEL)

        # trunk
        lin('t1', TR_H1, TRUNK_IN)
        ln('t1ln', TR_H1)
        lin('t2', TR_H2, TR_H1)
        ln('t2ln', TR_H2)

        # heads (small init)
        lin('pol', N_ACTIONS, A_CORE, scale=np.sqrt(0.01))
        lin('val', 1, A_CORE, scale=np.sqrt(0.01))
        lin('tgt', N_TARGETS, A_CORE, scale=np.sqrt(0.01))
        lin('give', N_CARD_TYPES, A_CORE, scale=np.sqrt(0.01))
        lin('place', N_PLACE, A_CORE, scale=np.sqrt(0.01))
        lin('nope1', NOPE_H, NOPE_IN, scale=np.sqrt(0.01))
        lin('nope2', 1, NOPE_H, scale=np.sqrt(0.01))

        self.keys = list(self.P.keys())
        self._m = {k: np.zeros_like(v) for k, v in self.P.items()}
        self._v = {k: np.zeros_like(v) for k, v in self.P.items()}
        self._t = 0

    # -------- attention --------

    def _mha_forward(self, x, p):
        """x: [L, d]. p: layer prefix. Returns out[L,d], cache."""
        L = x.shape[0]
        W = self.P
        Q = x @ W[p + 'q_W'].T + W[p + 'q_b']
        K = x @ W[p + 'k_W'].T + W[p + 'k_b']
        V = x @ W[p + 'v_W'].T + W[p + 'v_b']
        Qh = Q.reshape(L, N_HEADS, HEAD_DIM).transpose(1, 0, 2)  # [H,L,hd]
        Kh = K.reshape(L, N_HEADS, HEAD_DIM).transpose(1, 0, 2)
        Vh = V.reshape(L, N_HEADS, HEAD_DIM).transpose(1, 0, 2)
        scale = 1.0 / np.sqrt(HEAD_DIM)
        scores = np.matmul(Qh, Kh.transpose(0, 2, 1)) * scale     # [H,L,L]
        A = _softmax_rows(scores)
        ctxh = np.matmul(A, Vh)                                   # [H,L,hd]
        ctx = ctxh.transpose(1, 0, 2).reshape(L, D_MODEL)
        out = ctx @ W[p + 'o_W'].T + W[p + 'o_b']
        cache = (x, Qh, Kh, Vh, A, ctx, scale, p, L)
        return out, cache

    def _mha_backward(self, dout, cache, grads):
        x, Qh, Kh, Vh, A, ctx, scale, p, L = cache
        W = self.P
        grads[p + 'o_W'] += dout.T @ ctx
        grads[p + 'o_b'] += dout.sum(axis=0)
        dctx = dout @ W[p + 'o_W']                                # [L,d]
        dctxh = dctx.reshape(L, N_HEADS, HEAD_DIM).transpose(1, 0, 2)  # [H,L,hd]
        dV = np.matmul(A.transpose(0, 2, 1), dctxh)               # [H,L,hd]
        dA = np.matmul(dctxh, Vh.transpose(0, 2, 1))              # [H,L,L]
        # softmax backward per row
        dscores = A * (dA - (A * dA).sum(axis=-1, keepdims=True))
        dscores *= scale
        dQh = np.matmul(dscores, Kh)                              # [H,L,hd]
        dKh = np.matmul(dscores.transpose(0, 2, 1), Qh)          # [H,L,hd]
        dQ = dQh.transpose(1, 0, 2).reshape(L, D_MODEL)
        dK = dKh.transpose(1, 0, 2).reshape(L, D_MODEL)
        dVm = dV.transpose(1, 0, 2).reshape(L, D_MODEL)
        for nm, dY in (('q', dQ), ('k', dK), ('v', dVm)):
            grads[p + nm + '_W'] += dY.T @ x
            grads[p + nm + '_b'] += dY.sum(axis=0)
        dx = dQ @ W[p + 'q_W'] + dK @ W[p + 'k_W'] + dVm @ W[p + 'v_W']
        return dx

    # -------- FFN --------

    def _ffn_forward(self, x, p):
        W = self.P
        h_pre = x @ W[p + 'ff1_W'].T + W[p + 'ff1_b']
        h, mc = _mish(h_pre)
        out = h @ W[p + 'ff2_W'].T + W[p + 'ff2_b']
        return out, (x, h, mc, p)

    def _ffn_backward(self, dout, cache, grads):
        x, h, mc, p = cache
        W = self.P
        grads[p + 'ff2_W'] += dout.T @ h
        grads[p + 'ff2_b'] += dout.sum(axis=0)
        dh = dout @ W[p + 'ff2_W']
        dh_pre = _mish_back(dh, mc)
        grads[p + 'ff1_W'] += dh_pre.T @ x
        grads[p + 'ff1_b'] += dh_pre.sum(axis=0)
        dx = dh_pre @ W[p + 'ff1_W']
        return dx

    # -------- one transformer layer (pre-LN) --------

    def _layer_forward(self, x, l):
        p = f'L{l}_'
        n1, c1 = _ln_forward(x, self.P[p + 'ln1_g'], self.P[p + 'ln1_b'])
        att, ca = self._mha_forward(n1, p)
        a = x + att
        n2, c2 = _ln_forward(a, self.P[p + 'ln2_g'], self.P[p + 'ln2_b'])
        ff, cf = self._ffn_forward(n2, p)
        y = a + ff
        return y, (c1, ca, c2, cf, p)

    def _layer_backward(self, dy, cache, grads):
        c1, ca, c2, cf, p = cache
        # y = a + ff
        da = dy.copy()
        dn2 = self._ffn_backward(dy, cf, grads)
        dx_ln2, dg2, db2 = _ln_backward(dn2, c2)
        grads[p + 'ln2_g'] += dg2
        grads[p + 'ln2_b'] += db2
        da += dx_ln2
        # a = x + att
        dx = da.copy()
        dn1 = self._mha_backward(da, ca, grads)
        dx_ln1, dg1, db1 = _ln_backward(dn1, c1)
        grads[p + 'ln1_g'] += dg1
        grads[p + 'ln1_b'] += db1
        dx += dx_ln1
        return dx

    # -------- encoder + pooling --------

    def encode(self, event_window):
        """event_window: [L, N_EVENT] (most recent last). Returns H_mem[256], cache.

        If L == 0, returns zeros and a cache flagged empty.
        """
        L = len(event_window)
        if L == 0:
            return np.zeros(H_MEM), ('empty',)
        X = np.asarray(event_window, dtype=np.float64)
        h0 = X @ self.P['inp_W'].T + self.P['inp_b']             # [L,d]
        pe = _pos_encoding(L, D_MODEL)
        h = h0 + pe
        layer_caches = []
        for l in range(N_LAYERS):
            h, lc = self._layer_forward(h, l)
            layer_caches.append(lc)
        hf, cf = _ln_forward(h, self.P['lnf_g'], self.P['lnf_b'])
        mean = hf.mean(axis=0)
        last = hf[-1]
        hmem = np.concatenate([mean, last])
        cache = ('full', X, layer_caches, cf, hf, L)
        return hmem, cache

    def encode_backward(self, dhmem, cache, grads):
        if cache[0] == 'empty':
            return
        _, X, layer_caches, cf, hf, L = cache
        dmean = dhmem[:D_MODEL]
        dlast = dhmem[D_MODEL:]
        dhf = np.zeros((L, D_MODEL))
        dhf += dmean / L                       # mean pooling grad
        dhf[-1] += dlast                        # last token
        dh, dgf, dbf = _ln_backward(dhf, cf)
        grads['lnf_g'] += dgf
        grads['lnf_b'] += dbf
        for l in range(N_LAYERS - 1, -1, -1):
            dh = self._layer_backward(dh, layer_caches[l], grads)
        # dh is grad wrt (h0 + pe); pe is constant -> grad to inp projection
        grads['inp_W'] += dh.T @ X
        grads['inp_b'] += dh.sum(axis=0)

    # -------- trunk --------

    def trunk(self, hmem, snap):
        x = np.concatenate([hmem, snap])
        z1 = self.P['t1_W'] @ x + self.P['t1_b']
        n1, c1 = _ln_forward(z1, self.P['t1ln_g'], self.P['t1ln_b'])
        a1, m1 = _mish(n1)
        z2 = self.P['t2_W'] @ a1 + self.P['t2_b']
        n2, c2 = _ln_forward(z2, self.P['t2ln_g'], self.P['t2ln_b'])
        a2, m2 = _mish(n2)
        return a2, (x, c1, m1, a1, c2, m2)

    def trunk_backward(self, da2, cache, grads):
        x, c1, m1, a1, c2, m2 = cache
        dn2 = _mish_back(da2, m2)
        dz2, dg2, db2 = _ln_backward(dn2, c2)
        grads['t2ln_g'] += dg2
        grads['t2ln_b'] += db2
        grads['t2_W'] += np.outer(dz2, a1)
        grads['t2_b'] += dz2
        da1 = self.P['t2_W'].T @ dz2
        dn1 = _mish_back(da1, m1)
        dz1, dg1, db1 = _ln_backward(dn1, c1)
        grads['t1ln_g'] += dg1
        grads['t1ln_b'] += db1
        grads['t1_W'] += np.outer(dz1, x)
        grads['t1_b'] += dz1
        dx = self.P['t1_W'].T @ dz1
        return dx[:H_MEM]   # grad back into H_mem

    # -------- heads (forward) --------

    def policy(self, a2):
        return self.P['pol_W'] @ a2 + self.P['pol_b']

    def value(self, a2):
        return float((self.P['val_W'] @ a2 + self.P['val_b'])[0])

    def target(self, a2):
        return self.P['tgt_W'] @ a2 + self.P['tgt_b']

    def give(self, a2):
        return self.P['give_W'] @ a2 + self.P['give_b']

    def place(self, a2):
        return self.P['place_W'] @ a2 + self.P['place_b']

    def nope_logit(self, a2, ctx):
        x = np.concatenate([a2, ctx])
        h_pre = self.P['nope1_W'] @ x + self.P['nope1_b']
        h, mc = _mish(h_pre)
        logit = float((self.P['nope2_W'] @ h + self.P['nope2_b'])[0])
        return logit, (x, h, mc)

    # -------- simple linear-head backward helpers --------

    def _lin_head_backward(self, name, dlogits, a2, grads):
        grads[name + '_W'] += np.outer(dlogits, a2)
        grads[name + '_b'] += dlogits
        return self.P[name + '_W'].T @ dlogits

    def value_backward(self, dval, a2, grads):
        grads['val_W'] += np.outer([dval], a2)
        grads['val_b'] += np.array([dval])
        return self.P['val_W'].T @ np.array([dval])

    def nope_backward(self, dlogit, cache, grads):
        x, h, mc = cache
        grads['nope2_W'] += np.outer([dlogit], h)
        grads['nope2_b'] += np.array([dlogit])
        dh = self.P['nope2_W'].T @ np.array([dlogit])
        dh_pre = _mish_back(dh, mc)
        grads['nope1_W'] += np.outer(dh_pre, x)
        grads['nope1_b'] += dh_pre
        dx = self.P['nope1_W'].T @ dh_pre
        return dx[:A_CORE]   # grad into a2 (drop ctx part)

    # -------- optimizer / IO --------

    def zero_grads(self):
        return {k: np.zeros_like(v) for k, v in self.P.items()}

    def step(self, grads, lr, max_norm=1.0):
        norm = np.sqrt(sum(float(np.sum(g * g)) for g in grads.values()))
        if norm > max_norm:
            scale = max_norm / (norm + 1e-8)
            grads = {k: v * scale for k, v in grads.items()}
        self._t += 1
        t = self._t
        for k, g in grads.items():
            m, v = self._m[k], self._v[k]
            m[:] = 0.9 * m + 0.1 * g
            v[:] = 0.999 * v + 0.001 * (g * g)
            mh = m / (1.0 - 0.9 ** t)
            vh = v / (1.0 - 0.999 ** t)
            self.P[k] -= lr * mh / (np.sqrt(vh) + 1e-8)

    def weights(self):
        return {k: v.tolist() for k, v in self.P.items()}

    def load_weights(self, d):
        for k in self.keys:
            if k in d:
                arr = np.array(d[k], dtype=np.float64)
                if arr.shape == self.P[k].shape:
                    self.P[k][...] = arr
                    self._m[k] = np.zeros_like(self.P[k])
                    self._v[k] = np.zeros_like(self.P[k])

    def save(self, path):
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(self.weights(), f)
        os.replace(tmp, path)
