"""Actor-Critic network for Gorilla (numpy).

Shared MLP base -> policy head (action logits) + value head (scalar). Kept the
same shape as Orangutan's policy net (35 -> 64 -> 32 -> 8) so the trained policy
loads straight into agents/orangutan_weights.json.
"""
import json
import os

import numpy as np

from agents.orangutan_features import N_FEATURES, N_ACTIONS

H1, H2 = 64, 32
NEG = -1e9
PARAM_KEYS = ("W1", "b1", "W2", "b2", "W3", "b3", "Wv", "bv")


class ActorCritic:
    def __init__(self, seed=0, n_features=N_FEATURES):
        rng = np.random.default_rng(seed)
        self.n_features = n_features
        self.W1 = rng.standard_normal((H1, n_features)) * np.sqrt(2 / n_features)
        self.b1 = np.zeros(H1)
        self.W2 = rng.standard_normal((H2, H1)) * np.sqrt(2 / H1)
        self.b2 = np.zeros(H2)
        self.W3 = rng.standard_normal((N_ACTIONS, H2)) * np.sqrt(0.01)   # policy head
        self.b3 = np.zeros(N_ACTIONS)
        self.Wv = rng.standard_normal((1, H2)) * np.sqrt(0.01)           # value head
        self.bv = np.zeros(1)
        self._adam = {k: [np.zeros_like(getattr(self, k)), np.zeros_like(getattr(self, k))]
                      for k in PARAM_KEYS}
        self._t = 0

    # ---- forward (batched) ----
    def forward(self, X):
        Z1 = X @ self.W1.T + self.b1; A1 = np.maximum(Z1, 0)
        Z2 = A1 @ self.W2.T + self.b2; A2 = np.maximum(Z2, 0)
        logits = A2 @ self.W3.T + self.b3
        value = (A2 @ self.Wv.T + self.bv)[..., 0]
        return logits, value, (X, Z1, A1, Z2, A2)

    def step(self, grads, lr):
        """Adam descent (grads are dLoss/dParam)."""
        self._t += 1
        for k, g in grads.items():
            m, v = self._adam[k]
            m[:] = 0.9 * m + 0.1 * g
            v[:] = 0.999 * v + 0.001 * (g * g)
            mh = m / (1 - 0.9 ** self._t); vh = v / (1 - 0.999 ** self._t)
            getattr(self, k)[...] -= lr * mh / (np.sqrt(vh) + 1e-8)

    # ---- weights I/O ----
    def policy_weights(self):
        """Just the policy MLP, in Orangutan's format."""
        return {k: getattr(self, k).tolist() for k in ("W1", "b1", "W2", "b2", "W3", "b3")}

    def full_weights(self):
        return {k: getattr(self, k).tolist() for k in PARAM_KEYS}

    def load_full(self, d):
        for k in PARAM_KEYS:
            if k in d:
                getattr(self, k)[...] = np.array(d[k])

    def load_bc(self, path):
        """Warm-start the base + policy head from Orangutan BC weights."""
        with open(path) as f:
            d = json.load(f)
        for k in ("W1", "b1", "W2", "b2", "W3", "b3"):
            getattr(self, k)[...] = np.array(d[k])

    def save_policy(self, path):
        d = self.policy_weights(); d["arch"] = [self.n_features, H1, H2, N_ACTIONS]
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f)
        os.replace(tmp, path)

    def save_full(self, path):
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.full_weights(), f)
        os.replace(tmp, path)


def masked_softmax(logits, mask):
    z = np.where(mask > 0, logits, NEG)
    z = z - z.max(axis=-1, keepdims=True)
    e = np.exp(z) * mask
    return e / e.sum(axis=-1, keepdims=True)
