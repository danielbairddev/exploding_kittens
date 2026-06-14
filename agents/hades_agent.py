"""Hades — loser-fleet bot. Architecture TBD by design iteration.

Goal: not be the last survivor. Reward = +1 for any non-winner finish.

This file is a template. Replace the TODO sections with the designed architecture.
The interface contract (methods, ARENA dict) must be preserved exactly.

Weights loaded from agents/hades_weights.json at import time.
"""
import json
import math
import os

from agents.base import Agent
from game.actions import Action, ActionType
from game.cards import CardType

try:
    import numpy as _np
    _HAS_NP = True
except ImportError:
    _np = None
    _HAS_NP = False

# TODO: replace with actual imports once training modules exist
# from training.hades.event_encode import encode_event, N_EVENT, CARD_NAMES
# from training.hades.features import encode as snap_encode, N_SNAP
# from training.hades.net import GRU_H, N_ACTIONS, N_TARGETS, N_CARD_TYPES, N_BUCKETS, NOPE_CTX_DIM, BUCKET_FRACS

_WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hades_weights.json')

# ---- Placeholder constants — update when architecture is finalised ----
GRU_H        = 0   # TODO
N_SNAP       = 0   # TODO
N_EVENT      = 0   # TODO
N_ACTIONS    = 8   # DRAW/SKIP/ATTACK/SHUFFLE/STF/FAVOR/CAT_PAIR/CAT_TRIPLE
N_TARGETS    = 5   # relative opponent seats
N_CARD_TYPES = 13
N_BUCKETS    = 0   # TODO: number of placement buckets (or continuous)
NOPE_CTX_DIM = 0   # TODO: nope context dimensions

CARD_NAMES = [
    'DEFUSE','ATTACK','SKIP','FAVOR','SHUFFLE','SEE_THE_FUTURE','NOPE',
    'TACO_CAT','HAIRY_POTATO_CAT','BEARD_CAT','RAINBOW_CAT','CATTERMELON',
    'EXPLODING_KITTEN',
]

# Action ordering must match training
ACTIONS = [
    ActionType.DRAW, ActionType.PLAY_SKIP, ActionType.PLAY_ATTACK,
    ActionType.PLAY_SHUFFLE, ActionType.PLAY_SEE_THE_FUTURE,
    ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE,
]


def _load():
    try:
        with open(_WEIGHTS_PATH) as f:
            w = json.load(f)
        if not w:
            return None
        if _HAS_NP:
            return {k: _np.array(v, dtype=_np.float32) for k, v in w.items()}
        return w
    except (OSError, ValueError):
        return None


class HadesAgent(Agent):
    ARENA = {
        'name':  'Hades',       # TODO: rename
        'emoji': '💀',           # TODO
        'color': '#1e293b',      # TODO
        'blurb': 'Lord of the underworld. Here to lose.',  # TODO
        'stats_version': 1,
    }

    _WEIGHTS = _load()

    def __init__(self, name='Hades', seed=None):
        self.name = name
        self._h = None           # GRU hidden state
        self._last_eid = -1
        self._top = None         # known top-deck cards (from STF)
        self._opp_defuses_used = {}
        self._pending_give = None
        self._reset_state()

    def _reset_state(self):
        if _HAS_NP and GRU_H:
            self._h = _np.zeros(GRU_H, dtype=_np.float32)
        else:
            self._h = [0.0] * GRU_H if GRU_H else []
        self._last_eid = -1
        self._top = None
        self._opp_defuses_used = {}
        self._pending_give = None

    def game_start(self, state):
        self._reset_state()

    def see_future(self, state, top3):
        self._top = [c.card_type for c in top3]

    def _known_list(self):
        return self._top if self._top else None

    def _absorb(self, state):
        """Process new events into GRU hidden state."""
        if self._WEIGHTS is None or not GRU_H:
            return
        new = sorted(
            [e for e in state.recent_events if e.get('event_id', 0) > self._last_eid],
            key=lambda e: e.get('event_id', 0),
        )
        for ev in new:
            t = ev.get('type')
            # Maintain STF window
            if t == 'draw' and self._top:
                self._top = self._top[1:] or None
            elif t in ('shuffle', 'defuse'):
                self._top = None
            # Track opponent defuse usage
            if t == 'defuse':
                p = ev.get('player')
                if p is not None and p != state.my_id:
                    self._opp_defuses_used[p] = self._opp_defuses_used.get(p, 0) + 1
            # Inject card_given when we were the giver
            if (self._pending_give and t in ('favor', 'cat_steal')
                    and ev.get('from_player') == state.my_id):
                ev = dict(ev, card_given=self._pending_give)
                self._pending_give = None
            # TODO: encode event and step GRU
            # vec = encode_event(ev, state.my_id)
            # self._h = gru_step(vec, self._h, self._WEIGHTS)
            self._last_eid = ev.get('event_id', self._last_eid)

    def _snap(self, state):
        """Build snapshot feature vector."""
        if not N_SNAP:
            return []
        # TODO: return snap_encode(state, self._known_list(), self._opp_defuses_used,
        #                          ek_count=state.deck_exploding_kittens_count)
        return [0.0] * N_SNAP

    def _forward(self, state):
        """Run trunk forward pass → a2."""
        # TODO: implement trunk forward
        return None

    # ------------------------------------------------------------------ interface

    def choose_action(self, state, valid_actions):
        if self._WEIGHTS is None:
            return Action(ActionType.DRAW)
        self._absorb(state)
        a2 = self._forward(state)
        if a2 is None:
            return Action(ActionType.DRAW)

        by = {}
        for a in valid_actions:
            by.setdefault(a.action_type, []).append(a)

        # TODO: policy head → masked argmax → return action
        # mask = [1.0 if at in by else 0.0 for at in ACTIONS]
        # logits = policy_head(a2, self._WEIGHTS)
        # idx = masked_argmax(logits, mask)
        # at = ACTIONS[idx]
        # ...handle target selection for FAVOR/CAT...
        return Action(ActionType.DRAW)

    def want_to_nope(self, state, action, currently_noped=False):
        if self._WEIGHTS is None:
            return False
        self._absorb(state)
        a2 = self._forward(state)
        if a2 is None:
            return False
        # TODO: build nope context, run nope head
        # ctx = build_nope_ctx(action, state.my_id, currently_noped)
        # prob = nope_head(a2, ctx, self._WEIGHTS)
        # return prob > 0.5
        return False

    def give_card(self, state, requester_id):
        if not state.my_hand:
            return state.my_hand[0].card_type if state.my_hand else CardType.DEFUSE
        self._absorb(state)
        a2 = self._forward(state)
        if a2 is None or self._WEIGHTS is None:
            return state.my_hand[0].card_type
        # TODO: give head → masked argmax over hand
        # scores = give_head(a2, self._WEIGHTS)
        # ...
        ct = state.my_hand[0].card_type
        self._pending_give = ct.name
        return ct

    def place_exploding_kitten(self, state, deck_size):
        self._absorb(state)
        if self._WEIGHTS is None or not deck_size:
            return 0
        a2 = self._forward(state)
        if a2 is None:
            return 0
        # TODO: place head → position
        # parity = deck_size % 2
        # probs = place_head(a2, parity, self._WEIGHTS)
        # bucket = argmax(probs)
        # return min(deck_size, round(BUCKET_FRACS[bucket] * deck_size))
        return 0
