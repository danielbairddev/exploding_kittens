"""Rhino — GRU-based neural-net agent.

Unlike Orangutan (which sees only a per-turn snapshot), Rhino maintains a GRU
hidden state across the whole game, processing every public event as it arrives.
The hidden state is concatenated with the standard snapshot features and fed to
a small MLP for the policy.

Falls back to Coyote logic if weights aren't present yet.
Inference is pure Python — no third-party dependencies.
"""
import json
import math
import os

from agents.coyote_agent import CoyoteAgent
from agents.orangutan_features import encode as snap_encode, ACTIONS
from game.actions import Action, ActionType
from game.cards import CardType

DEF = CardType.DEFUSE
_WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rhino_weights.json')

# Must match rhino/net.py constants
_GRU_H = 64


def _load_weights():
    try:
        with open(_WEIGHTS_PATH) as f:
            w = json.load(f)
        required = ('Wz', 'Uz', 'bz', 'Wr', 'Ur', 'br', 'Wn', 'Un', 'bn',
                    'W1', 'b1', 'W2', 'b2', 'W3', 'b3')
        if all(k in w for k in required):
            return w
    except (OSError, ValueError):
        pass
    return None


def _matvec(W, v):
    return [sum(w * vi for w, vi in zip(row, v)) for row in W]


def _sigmoid(v):
    return [1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, x)))) for x in v]


def _tanh_v(v):
    return [math.tanh(x) for x in v]


def _add(a, b):
    return [x + y for x, y in zip(a, b)]


def _gru_step(x, h, w):
    """Pure-Python single GRU step."""
    z = _sigmoid(_add(_add(_matvec(w['Wz'], x), _matvec(w['Uz'], h)), w['bz']))
    r = _sigmoid(_add(_add(_matvec(w['Wr'], x), _matvec(w['Ur'], h)), w['br']))
    rh = [ri * hi for ri, hi in zip(r, h)]
    n = _tanh_v(_add(_add(_matvec(w['Wn'], x), _matvec(w['Un'], rh)), w['bn']))
    return [(1.0 - zi) * hi + zi * ni for zi, hi, ni in zip(z, h, n)]


def _mlp_forward(h, snap, w):
    x = h + snap
    a1 = [max(0.0, v) for v in _add(_matvec(w['W1'], x), w['b1'])]
    a2 = [max(0.0, v) for v in _add(_matvec(w['W2'], a1), w['b2'])]
    return _add(_matvec(w['W3'], a2), w['b3'])


def _masked_argmax(logits, mask):
    best_i, best_v = None, None
    for i, (l, m) in enumerate(zip(logits, mask)):
        if m and (best_v is None or l > best_v):
            best_i, best_v = i, l
    return best_i


class RhinoAgent(CoyoteAgent):
    ARENA = {
        'name': 'Rhino', 'emoji': '🦏', 'color': '#6b7280',
        'blurb': 'Reads the room. Remembers everything.',
        'author': 'Daniel Baird', 'llm_assisted': True, 'stats_version': 1,
    }

    _WEIGHTS = _load_weights()

    def __init__(self, name='Rhino', seed=None):
        super().__init__(name=name, seed=seed)
        self._h = [0.0] * _GRU_H
        self._last_eid = -1

    def game_start(self, state):
        super().game_start(state)
        self._h = [0.0] * _GRU_H
        self._last_eid = -1

    def _absorb_events(self, state):
        if self._WEIGHTS is None:
            return
        from rhino.event_encode import encode_event
        new = sorted(
            [e for e in state.recent_events if e.get('event_id', 0) > self._last_eid],
            key=lambda e: e.get('event_id', 0),
        )
        for ev in new:
            vec = encode_event(ev, state.my_id).tolist()
            self._h = _gru_step(vec, self._h, self._WEIGHTS)
            self._last_eid = ev.get('event_id', self._last_eid)

    def choose_action(self, state, valid_actions):
        if self._WEIGHTS is None:
            return super().choose_action(state, valid_actions)

        self._absorb_events(state)

        by = {}
        for a in valid_actions:
            by.setdefault(a.action_type, []).append(a)
        mask = [1.0 if at in by else 0.0 for at in ACTIONS]
        snap = snap_encode(state, self._known_list(state))

        logits = _mlp_forward(self._h, snap, self._WEIGHTS)
        idx = _masked_argmax(logits, mask)
        if idx is None:
            return Action(ActionType.DRAW)

        at = ACTIONS[idx]
        acts = by.get(at) or [Action(ActionType.DRAW)]
        if at in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
            chosen = self._best_target(acts, state)
            if at == ActionType.PLAY_CAT_TRIPLE:
                from dataclasses import replace
                chosen = replace(chosen, named_card=DEF)
            return chosen
        return acts[0]
