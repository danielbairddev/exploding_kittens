"""GRU + Actor-Critic network for Rhino (numpy).

Architecture:
  - GRU(N_EVENT=39 -> GRU_H=64): processes the game event sequence
  - MLP(GRU_H + N_SNAP=52 -> 64 -> 32 -> N_ACTIONS=8 + 1 value)

The GRU hidden state is a running summary of all public events seen this game.
At each decision point, it's concatenated with the current snapshot features
and passed through the MLP for policy + value.

Inference weights (everything except Wv/bv) are saved in Orangutan-compatible
JSON format for the deployed agent's pure-Python forward pass.
"""
import json
import os
import numpy as np

from agents.orangutan_features import N_FEATURES as N_SNAP, N_ACTIONS
from rhino.event_encode import N_EVENT

GRU_H = 64
H1, H2 = 64, 32
N_MLP_IN = GRU_H + N_SNAP   # 116

GRU_KEYS = ('Wz', 'Uz', 'bz', 'Wr', 'Ur', 'br', 'Wn', 'Un', 'bn')
MLP_KEYS = ('W1', 'b1', 'W2', 'b2', 'W3', 'b3', 'Wv', 'bv')
ALL_KEYS = GRU_KEYS + MLP_KEYS
POLICY_KEYS = GRU_KEYS + ('W1', 'b1', 'W2', 'b2', 'W3', 'b3')  # no value head


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20.0, 20.0)))


def _orth(rows, cols, rng):
    """Orthogonal matrix init (good for recurrent weights)."""
    m = rng.standard_normal((max(rows, cols), min(rows, cols)))
    u, _, vt = np.linalg.svd(m, full_matrices=False)
    w = u if rows >= cols else vt
    return w[:rows, :cols]


class GRUActorCritic:
    def __init__(self, seed=0):
        rng = np.random.default_rng(seed)
        s = np.sqrt(2.0 / N_EVENT)

        # GRU: input weights Xavier, recurrent weights orthogonal
        for g in ('z', 'r', 'n'):
            setattr(self, f'W{g}', rng.standard_normal((GRU_H, N_EVENT)) * s)
            setattr(self, f'U{g}', _orth(GRU_H, GRU_H, rng))
            setattr(self, f'b{g}', np.zeros(GRU_H))
        self.bz += 1.0   # bias update gate open initially — helps early gradient flow

        # MLP
        self.W1 = rng.standard_normal((H1, N_MLP_IN)) * np.sqrt(2.0 / N_MLP_IN)
        self.b1 = np.zeros(H1)
        self.W2 = rng.standard_normal((H2, H1)) * np.sqrt(2.0 / H1)
        self.b2 = np.zeros(H2)
        self.W3 = rng.standard_normal((N_ACTIONS, H2)) * np.sqrt(0.01)
        self.b3 = np.zeros(N_ACTIONS)
        self.Wv = rng.standard_normal((1, H2)) * np.sqrt(0.01)
        self.bv = np.zeros(1)

        # Adam state
        self._m = {k: np.zeros_like(getattr(self, k)) for k in ALL_KEYS}
        self._v = {k: np.zeros_like(getattr(self, k)) for k in ALL_KEYS}
        self._t = 0

    # ---- GRU forward / backward ----

    def gru_step(self, x, h):
        """Single GRU step. Returns (h_new, cache) for backprop."""
        z = _sigmoid(self.Wz @ x + self.Uz @ h + self.bz)
        r = _sigmoid(self.Wr @ x + self.Ur @ h + self.br)
        rh = r * h
        n = np.tanh(self.Wn @ x + self.Un @ rh + self.bn)
        h_new = (1.0 - z) * h + z * n
        return h_new, (x, h, z, r, rh, n)

    def gru_step_backward(self, dh_new, cache):
        """Backprop through one GRU step. Returns (dh_prev, weight_grads_dict)."""
        x, h, z, r, rh, n = cache

        # h_new = (1-z)*h + z*n
        dz_raw = dh_new * (n - h)
        dn = dh_new * z
        dh_direct = dh_new * (1.0 - z)

        # n = tanh(...)
        dn_pre = dn * (1.0 - n * n)

        # n gate path through r*h
        drh = self.Un.T @ dn_pre
        dr_raw = drh * h
        dh_n = drh * r

        # gate sigmoid derivatives
        dz_pre = dz_raw * z * (1.0 - z)
        dr_pre = dr_raw * r * (1.0 - r)

        dh_prev = dh_direct + dh_n + self.Uz.T @ dz_pre + self.Ur.T @ dr_pre

        grads = {
            'Wz': np.outer(dz_pre, x), 'Uz': np.outer(dz_pre, h), 'bz': dz_pre,
            'Wr': np.outer(dr_pre, x), 'Ur': np.outer(dr_pre, h), 'br': dr_pre,
            'Wn': np.outer(dn_pre, x), 'Un': np.outer(dn_pre, rh), 'bn': dn_pre,
        }
        return dh_prev, grads

    def run_gru(self, event_vecs):
        """Run GRU over a full event sequence.
        Returns (hs, caches) where hs[i] is state after i events (hs[0]=zeros).
        """
        h = np.zeros(GRU_H)
        hs = [h]
        caches = []
        for ev in event_vecs:
            h, cache = self.gru_step(ev, h)
            hs.append(h)
            caches.append(cache)
        return hs, caches

    # ---- MLP forward / backward ----

    def mlp_forward(self, h, snap):
        """Returns (logits, value, cache)."""
        x = np.concatenate([h, snap])
        z1 = self.W1 @ x + self.b1;  a1 = np.maximum(z1, 0.0)
        z2 = self.W2 @ a1 + self.b2; a2 = np.maximum(z2, 0.0)
        logits = self.W3 @ a2 + self.b3
        value = float((self.Wv @ a2 + self.bv)[0])
        return logits, value, (x, z1, a1, z2, a2)

    def mlp_backward(self, dlogits, dvalue, cache):
        """Returns (dh, weight_grads_dict)."""
        x, z1, a1, z2, a2 = cache

        gW3 = np.outer(dlogits, a2); gb3 = dlogits.copy()
        gWv = np.outer([dvalue], a2); gbv = np.array([dvalue])

        da2 = self.W3.T @ dlogits + self.Wv.T @ np.array([dvalue])
        dz2 = da2 * (z2 > 0); gW2 = np.outer(dz2, a1); gb2 = dz2.copy()

        da1 = self.W2.T @ dz2
        dz1 = da1 * (z1 > 0); gW1 = np.outer(dz1, x); gb1 = dz1.copy()

        dx = self.W1.T @ dz1
        return dx[:GRU_H], {'W1': gW1, 'b1': gb1, 'W2': gW2, 'b2': gb2,
                             'W3': gW3, 'b3': gb3, 'Wv': gWv, 'bv': gbv}

    # ---- Optimizer ----

    def step(self, grads, lr, max_norm=1.0):
        """Adam step with gradient clipping by global norm."""
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
        """GRU + policy MLP (no value head) — format read by RhinoAgent."""
        return {k: getattr(self, k).tolist() for k in POLICY_KEYS}

    def full_weights(self):
        return {k: getattr(self, k).tolist() for k in ALL_KEYS}

    def load_weights(self, d):
        for k in ALL_KEYS:
            if k in d:
                arr = np.array(d[k])
                param = getattr(self, k)
                if arr.shape == param.shape:
                    param[...] = arr
                    self._m[k] = np.zeros_like(param)
                    self._v[k] = np.zeros_like(param)

    def save_policy(self, path):
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(self.policy_weights(), f)
        os.replace(tmp, path)

    def save_full(self, path):
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(self.full_weights(), f)
        os.replace(tmp, path)
