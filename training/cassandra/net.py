"""Cassandra network — GRU-192 + expanded decision heads.

Architecture:
  GRU(53 -> 192): richer event stream (card_given slot)
  Trunk(192 + 97 -> 256 -> 128): bigger shared representation
  Heads:
    Policy:  a2(128)              -> 8 action logits
    Value:   a2(128)              -> 1 scalar
    Target:  a2(128)              -> 5 target logits
    Nope:    a2(128) + ctx(24)   -> 64 -> 1   (two-layer; ctx = action_type+card+targets_me+noped)
    Give:    a2(128)              -> 13 card logits
    Place:   a2(128) + parity(1) -> 5 bucket logits

Nope context (24 dims):
  action_type one-hot (8) + card_played one-hot (14) + targets_me (1) + currently_noped (1)

Place context (1 dim):
  deck_parity — critical for 2-player endgame strategy
"""
import json
import os
import numpy as np

from training.cassandra.event_encode import N_EVENT
from training.cassandra.features import N_SNAP

GRU_H    = 192
H1, H2   = 256, 128   # trunk hidden sizes; H2 = a2 dim
N_MLP_IN = GRU_H + N_SNAP  # 289

N_ACTIONS    = 8
N_TARGETS    = 5
N_CARD_TYPES = 13
N_BUCKETS    = 5
BUCKET_FRACS = [0.0, 0.25, 0.5, 0.75, 1.0]

NOPE_CTX_DIM = 24    # action_type(8) + card(14) + targets_me(1) + noped(1)
NOPE_HID     = 64    # intermediate nope MLP layer
PLACE_CTX    = 1     # deck_parity

GRU_KEYS    = ('Wz','Uz','bz','Wr','Ur','br','Wn','Un','bn')
TRUNK_KEYS  = ('W1','b1','W2','b2')
POLICY_KEYS_H = ('W3','b3','Wv','bv')
AUX_KEYS    = ('Wtgt','btgt',
                'Wnope1','bnope1','Wnope2','bnope2',
                'Wgive','bgive',
                'Wplace','bplace')
ALL_KEYS    = GRU_KEYS + TRUNK_KEYS + POLICY_KEYS_H + AUX_KEYS
POLICY_KEYS = GRU_KEYS + TRUNK_KEYS + ('W3','b3') + AUX_KEYS


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20.0, 20.0)))


def _orth(rows, cols, rng):
    m = rng.standard_normal((max(rows, cols), min(rows, cols)))
    u, _, vt = np.linalg.svd(m, full_matrices=False)
    w = u if rows >= cols else vt
    return w[:rows, :cols]


class CassandraNet:
    def __init__(self, seed=0):
        rng = np.random.default_rng(seed)
        s_ev = np.sqrt(2.0 / N_EVENT)

        for g in ('z', 'r', 'n'):
            setattr(self, f'W{g}', rng.standard_normal((GRU_H, N_EVENT)) * s_ev)
            setattr(self, f'U{g}', _orth(GRU_H, GRU_H, rng))
            setattr(self, f'b{g}', np.zeros(GRU_H))
        self.bz += 1.0

        s1 = np.sqrt(2.0 / N_MLP_IN)
        self.W1 = rng.standard_normal((H1, N_MLP_IN)) * s1
        self.b1 = np.zeros(H1)
        self.W2 = rng.standard_normal((H2, H1)) * np.sqrt(2.0 / H1)
        self.b2 = np.zeros(H2)

        s_head = np.sqrt(0.01)
        self.W3  = rng.standard_normal((N_ACTIONS, H2))    * s_head; self.b3  = np.zeros(N_ACTIONS)
        self.Wv  = rng.standard_normal((1, H2))            * s_head; self.bv  = np.zeros(1)
        self.Wtgt = rng.standard_normal((N_TARGETS, H2))   * s_head; self.btgt = np.zeros(N_TARGETS)

        # Two-layer nope head
        self.Wnope1 = rng.standard_normal((NOPE_HID, H2 + NOPE_CTX_DIM)) * s_head
        self.bnope1 = np.zeros(NOPE_HID)
        self.Wnope2 = rng.standard_normal((1, NOPE_HID)) * s_head
        self.bnope2 = np.zeros(1)

        self.Wgive  = rng.standard_normal((N_CARD_TYPES, H2))        * s_head; self.bgive  = np.zeros(N_CARD_TYPES)
        self.Wplace = rng.standard_normal((N_BUCKETS, H2 + PLACE_CTX)) * s_head; self.bplace = np.zeros(N_BUCKETS)

        self._m = {k: np.zeros_like(getattr(self, k)) for k in ALL_KEYS}
        self._v = {k: np.zeros_like(getattr(self, k)) for k in ALL_KEYS}
        self._t = 0

    # ---- GRU ----

    def gru_step(self, x, h):
        z = _sigmoid(self.Wz @ x + self.Uz @ h + self.bz)
        r = _sigmoid(self.Wr @ x + self.Ur @ h + self.br)
        rh = r * h
        n = np.tanh(self.Wn @ x + self.Un @ rh + self.bn)
        h_new = (1.0 - z) * h + z * n
        return h_new, (x, h, z, r, rh, n)

    def gru_step_backward(self, dh_new, cache):
        x, h, z, r, rh, n = cache
        dz_raw  = dh_new * (n - h)
        dn      = dh_new * z
        dh_dir  = dh_new * (1.0 - z)
        dn_pre  = dn * (1.0 - n * n)
        drh     = self.Un.T @ dn_pre
        dr_raw  = drh * h; dh_n = drh * r
        dz_pre  = dz_raw * z * (1.0 - z)
        dr_pre  = dr_raw * r * (1.0 - r)
        dh_prev = dh_dir + dh_n + self.Uz.T @ dz_pre + self.Ur.T @ dr_pre
        grads = {
            'Wz': np.outer(dz_pre, x), 'Uz': np.outer(dz_pre, h), 'bz': dz_pre,
            'Wr': np.outer(dr_pre, x), 'Ur': np.outer(dr_pre, h), 'br': dr_pre,
            'Wn': np.outer(dn_pre, x), 'Un': np.outer(dn_pre, rh), 'bn': dn_pre,
        }
        return dh_prev, grads

    def run_gru(self, event_vecs):
        h = np.zeros(GRU_H)
        hs = [h]; caches = []
        for ev in event_vecs:
            h, cache = self.gru_step(ev, h)
            hs.append(h); caches.append(cache)
        return hs, caches

    # ---- Trunk ----

    def trunk_forward(self, h, snap):
        x  = np.concatenate([h, snap])
        z1 = self.W1 @ x + self.b1;  a1 = np.maximum(z1, 0.0)
        z2 = self.W2 @ a1 + self.b2; a2 = np.maximum(z2, 0.0)
        return a2, (x, z1, a1, z2)

    def trunk_backward(self, da2, cache):
        x, z1, a1, z2 = cache
        dz2 = da2 * (z2 > 0)
        gW2 = np.outer(dz2, a1); gb2 = dz2.copy()
        da1 = self.W2.T @ dz2
        dz1 = da1 * (z1 > 0)
        gW1 = np.outer(dz1, x); gb1 = dz1.copy()
        dx  = self.W1.T @ dz1
        return dx[:GRU_H], {'W1': gW1, 'b1': gb1, 'W2': gW2, 'b2': gb2}

    # ---- Policy + value ----

    def policy_forward(self, a2):
        logits = self.W3 @ a2 + self.b3
        value  = float((self.Wv @ a2 + self.bv)[0])
        return logits, value

    def policy_backward(self, dlogits, dvalue, a2):
        da2 = self.W3.T @ dlogits + self.Wv.T @ np.array([dvalue])
        return da2, {
            'W3': np.outer(dlogits, a2), 'b3': dlogits.copy(),
            'Wv': np.outer([dvalue], a2), 'bv': np.array([dvalue]),
        }

    # ---- Target head ----

    def target_forward(self, a2):
        return self.Wtgt @ a2 + self.btgt

    def target_backward(self, dlogits, a2):
        return self.Wtgt.T @ dlogits, {'Wtgt': np.outer(dlogits, a2), 'btgt': dlogits.copy()}

    # ---- Nope head (two-layer, context-aware) ----

    def nope_forward(self, a2, nope_ctx):
        """nope_ctx: 24-dim array [action_type(8), card(14), targets_me(1), noped(1)]"""
        ext = np.concatenate([a2, nope_ctx])
        h1  = np.maximum(self.Wnope1 @ ext + self.bnope1, 0.0)
        return float((self.Wnope2 @ h1 + self.bnope2)[0]), (ext, h1)

    def nope_backward(self, d_logit, a2, nope_ctx, cache):
        ext, h1 = cache
        dh1  = (self.Wnope2.T @ np.array([d_logit])) * (h1 > 0)
        dext = self.Wnope1.T @ dh1
        da2  = dext[:H2]
        return da2, {
            'Wnope1': np.outer(dh1, ext), 'bnope1': dh1.copy(),
            'Wnope2': np.outer([d_logit], h1), 'bnope2': np.array([d_logit]),
        }

    # ---- Give head ----

    def give_forward(self, a2):
        return self.Wgive @ a2 + self.bgive

    def give_backward(self, dlogits, a2):
        return self.Wgive.T @ dlogits, {'Wgive': np.outer(dlogits, a2), 'bgive': dlogits.copy()}

    # ---- Place head (context-aware: parity) ----

    def place_forward(self, a2, deck_parity):
        ext = np.append(a2, float(deck_parity))
        return self.Wplace @ ext + self.bplace, ext

    def place_backward(self, dlogits, ext):
        da2 = (self.Wplace.T @ dlogits)[:H2]
        return da2, {'Wplace': np.outer(dlogits, ext), 'bplace': dlogits.copy()}

    # ---- Optimizer (Adam) ----

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
            mh = m / (1.0 - 0.9  ** t)
            vh = v / (1.0 - 0.999 ** t)
            getattr(self, k)[...] -= lr * mh / (np.sqrt(vh) + 1e-8)

    # ---- I/O ----

    def policy_weights(self):
        return {k: getattr(self, k).tolist() for k in POLICY_KEYS}

    def full_weights(self):
        return {k: getattr(self, k).tolist() for k in ALL_KEYS}

    def load_weights(self, d):
        for k in ALL_KEYS:
            if k in d:
                arr = np.array(d[k])
                if arr.shape == getattr(self, k).shape:
                    getattr(self, k)[...] = arr
                    self._m[k] = np.zeros_like(arr)
                    self._v[k] = np.zeros_like(arr)

    def save_policy(self, path):
        tmp = path + '.tmp'
        with open(tmp, 'w') as f: json.dump(self.policy_weights(), f)
        os.replace(tmp, path)

    def save_full(self, path):
        tmp = path + '.tmp'
        with open(tmp, 'w') as f: json.dump(self.full_weights(), f)
        os.replace(tmp, path)
