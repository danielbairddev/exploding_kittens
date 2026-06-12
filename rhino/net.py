"""GRU + Actor-Critic network for Rhino (numpy).

Architecture:
  GRU(N_EVENT=39 -> GRU_H=64): processes the full public event sequence.
  Trunk(GRU_H + N_SNAP=52 -> H1=64 -> H2=32): shared representation.
  Five heads on top of the H2 representation:
    - Policy:  H2 -> N_ACTIONS=8 logits
    - Value:   H2 -> 1 scalar
    - Target:  H2 -> N_TARGETS=5 logits  (which opponent to target)
    - Nope:    H2+1 -> 1 logit            (want to nope? +currently_noped flag)
    - Give:    H2 -> N_CARD_TYPES=13      (which card type to give)
    - Place:   H2 -> N_BUCKETS=5          (where in deck to reinsert EK)
"""
import json
import os
import numpy as np

from agents.orangutan_features import N_FEATURES as N_SNAP, N_ACTIONS
from rhino.event_encode import N_EVENT

GRU_H = 64
H1, H2 = 64, 32
N_MLP_IN = GRU_H + N_SNAP  # 116

N_TARGETS    = 5   # relative player positions 0-4 (0=self; valid = 1-4)
N_CARD_TYPES = 13  # DEFUSE ATTACK SKIP FAVOR SHUFFLE STF NOPE + 5 cat types + EK
N_BUCKETS    = 5   # top / 25% / 50% / 75% / bottom of deck
BUCKET_FRACS = [0.0, 0.25, 0.5, 0.75, 1.0]

GRU_KEYS    = ('Wz','Uz','bz','Wr','Ur','br','Wn','Un','bn')
TRUNK_KEYS  = ('W1','b1','W2','b2')
POLICY_KEYS_H = ('W3','b3','Wv','bv')
AUX_KEYS    = ('Wtgt','btgt','Wnope','bnope','Wgive','bgive','Wplace','bplace')
ALL_KEYS    = GRU_KEYS + TRUNK_KEYS + POLICY_KEYS_H + AUX_KEYS
POLICY_KEYS = GRU_KEYS + TRUNK_KEYS + ('W3','b3') + AUX_KEYS  # shipped to agent (no Wv/bv)


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20.0, 20.0)))


def _orth(rows, cols, rng):
    m = rng.standard_normal((max(rows, cols), min(rows, cols)))
    u, _, vt = np.linalg.svd(m, full_matrices=False)
    w = u if rows >= cols else vt
    return w[:rows, :cols]


class GRUActorCritic:
    def __init__(self, seed=0):
        rng = np.random.default_rng(seed)
        s = np.sqrt(2.0 / N_EVENT)

        for g in ('z', 'r', 'n'):
            setattr(self, f'W{g}', rng.standard_normal((GRU_H, N_EVENT)) * s)
            setattr(self, f'U{g}', _orth(GRU_H, GRU_H, rng))
            setattr(self, f'b{g}', np.zeros(GRU_H))
        self.bz += 1.0  # open update gate early for gradient flow

        # Trunk
        self.W1 = rng.standard_normal((H1, N_MLP_IN)) * np.sqrt(2.0 / N_MLP_IN)
        self.b1 = np.zeros(H1)
        self.W2 = rng.standard_normal((H2, H1)) * np.sqrt(2.0 / H1)
        self.b2 = np.zeros(H2)

        # Policy + value heads
        self.W3 = rng.standard_normal((N_ACTIONS, H2)) * np.sqrt(0.01)
        self.b3 = np.zeros(N_ACTIONS)
        self.Wv = rng.standard_normal((1, H2)) * np.sqrt(0.01)
        self.bv = np.zeros(1)

        # Aux heads
        s2 = np.sqrt(0.01)
        self.Wtgt   = rng.standard_normal((N_TARGETS, H2))     * s2; self.btgt   = np.zeros(N_TARGETS)
        self.Wnope  = rng.standard_normal((1, H2 + 1))         * s2; self.bnope  = np.zeros(1)
        self.Wgive  = rng.standard_normal((N_CARD_TYPES, H2))  * s2; self.bgive  = np.zeros(N_CARD_TYPES)
        self.Wplace = rng.standard_normal((N_BUCKETS, H2))     * s2; self.bplace = np.zeros(N_BUCKETS)

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
        dz_raw   = dh_new * (n - h)
        dn       = dh_new * z
        dh_dir   = dh_new * (1.0 - z)
        dn_pre   = dn * (1.0 - n * n)
        drh      = self.Un.T @ dn_pre
        dr_raw   = drh * h;  dh_n = drh * r
        dz_pre   = dz_raw * z * (1.0 - z)
        dr_pre   = dr_raw * r * (1.0 - r)
        dh_prev  = dh_dir + dh_n + self.Uz.T @ dz_pre + self.Ur.T @ dr_pre
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
        """Shared trunk. Returns (a2, trunk_cache)."""
        x  = np.concatenate([h, snap])
        z1 = self.W1 @ x + self.b1;  a1 = np.maximum(z1, 0.0)
        z2 = self.W2 @ a1 + self.b2; a2 = np.maximum(z2, 0.0)
        return a2, (x, z1, a1, z2, a2)

    def trunk_backward(self, da2, trunk_cache):
        """da2 = accumulated da2 from all heads. Returns (dh, trunk_grads)."""
        x, z1, a1, z2, a2 = trunk_cache
        dz2 = da2 * (z2 > 0)
        gW2 = np.outer(dz2, a1); gb2 = dz2.copy()
        da1 = self.W2.T @ dz2
        dz1 = da1 * (z1 > 0)
        gW1 = np.outer(dz1, x);  gb1 = dz1.copy()
        dx  = self.W1.T @ dz1
        return dx[:GRU_H], {'W1': gW1, 'b1': gb1, 'W2': gW2, 'b2': gb2}

    # ---- Policy + value head ----

    def policy_forward(self, a2):
        logits = self.W3 @ a2 + self.b3
        value  = float((self.Wv @ a2 + self.bv)[0])
        return logits, value

    def policy_backward(self, dlogits, dvalue, a2):
        gW3 = np.outer(dlogits, a2); gb3 = dlogits.copy()
        gWv = np.outer([dvalue],  a2); gbv = np.array([dvalue])
        da2 = self.W3.T @ dlogits + self.Wv.T @ np.array([dvalue])
        return da2, {'W3': gW3, 'b3': gb3, 'Wv': gWv, 'bv': gbv}

    # ---- Target head ----

    def target_forward(self, a2):
        return self.Wtgt @ a2 + self.btgt

    def target_backward(self, dlogits, a2):
        da2 = self.Wtgt.T @ dlogits
        return da2, {'Wtgt': np.outer(dlogits, a2), 'btgt': dlogits.copy()}

    # ---- Nope head ----

    def nope_forward(self, a2, currently_noped):
        ext = np.append(a2, float(currently_noped))
        return float((self.Wnope @ ext + self.bnope)[0])

    def nope_backward(self, d_logit, a2, currently_noped):
        ext  = np.append(a2, float(currently_noped))
        da2  = (self.Wnope.T @ np.array([d_logit]))[:H2]
        return da2, {'Wnope': np.outer([d_logit], ext), 'bnope': np.array([d_logit])}

    # ---- Give head ----

    def give_forward(self, a2):
        return self.Wgive @ a2 + self.bgive

    def give_backward(self, dlogits, a2):
        da2 = self.Wgive.T @ dlogits
        return da2, {'Wgive': np.outer(dlogits, a2), 'bgive': dlogits.copy()}

    # ---- Place head ----

    def place_forward(self, a2):
        return self.Wplace @ a2 + self.bplace

    def place_backward(self, dlogits, a2):
        da2 = self.Wplace.T @ dlogits
        return da2, {'Wplace': np.outer(dlogits, a2), 'bplace': dlogits.copy()}

    # ---- Convenience: full forward (used in training) ----

    def mlp_forward(self, h, snap):
        """Trunk + policy head. Returns (logits, value, a2, trunk_cache)."""
        a2, tcache = self.trunk_forward(h, snap)
        logits, value = self.policy_forward(a2)
        return logits, value, a2, tcache

    # ---- Optimizer ----

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
            getattr(self, k)[...] -= lr * mh / (np.sqrt(vh) + 1e-8)

    # ---- Weights I/O ----

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
                    self._m[k] = np.zeros_like(getattr(self, k))
                    self._v[k] = np.zeros_like(getattr(self, k))

    def save_policy(self, path):
        tmp = path + '.tmp'
        with open(tmp, 'w') as f: json.dump(self.policy_weights(), f)
        os.replace(tmp, path)

    def save_full(self, path):
        tmp = path + '.tmp'
        with open(tmp, 'w') as f: json.dump(self.full_weights(), f)
        os.replace(tmp, path)
