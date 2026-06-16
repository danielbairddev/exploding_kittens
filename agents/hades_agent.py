"""Hades — Transformer anti-agent trained to intentionally lose (HADES_PLAN.md).

Successor to the Orpheus/Gabriel "loser" family: the GRU memory module is replaced
by a Transformer encoder over the last 128 public events (see ian_folder/hades/). The
greedy forward pass here mirrors ian_folder/hades/rollout.py exactly, so ian_folder and
inference see identical features and architecture.

Inference needs numpy + trained weights. If either is missing the agent degrades to
a safe no-op style fallback (play a non-DRAW action if available, else DRAW) so the
arena never crashes on a cold deploy.

Currently BENCHED — not added to web/dashboard_server.py ARENA_BOTS. Re-enable only
once trained weights beat the loser fleet (target survival < 2%).
"""
import json
import os
from dataclasses import replace

from agents.base import Agent
from game.actions import Action, ActionType
from game.cards import CardType

_WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hades_weights.json')

try:
    import numpy as np
    from training.hades.net import (TransformerActorCritic, CONTEXT_WINDOW, N_ACTIONS,
                                    N_TARGETS, N_CARD_TYPES, N_PLACE, NOPE_CTX)
    from training.hades import features as F
    from training.hades.event_encode import encode_event, new_context
    from agents.orangutan_features import ACTIONS
    _IMPORT_OK = True
except Exception:   # numpy or ian_folder package unavailable
    _IMPORT_OK = False

DEF = CardType.DEFUSE


def _load_net(path=_WEIGHTS_PATH):
    """Load a TransformerActorCritic from a weights JSON. Returns None on any
    failure (missing numpy/ian_folder pkg, missing/corrupt file) so the agent can
    fall back safely. Shared by HadesAgent and its win-seeking sibling ZeusAgent."""
    if not _IMPORT_OK:
        return None
    try:
        with open(path) as f:
            w = json.load(f)
        # sanity: at least the input projection must be present
        if 'inp_W' not in w:
            return None
        net = TransformerActorCritic()
        net.load_weights(w)
        return net
    except (OSError, ValueError):
        return None


# Nope-head context lives in features.nope_context (shared with training,
# target-aware: real attack target + "is this my action being noped").


def _masked_argmax(logits, mask):
    masked = np.where(np.asarray(mask) > 0, logits, -1e9)
    idx = int(np.argmax(masked))
    return idx if mask[idx] else None


class HadesAgent(Agent):
    ARENA = {
        'name': 'Hades',
        'emoji': '💀',
        'color': '#1e293b',
        'blurb': 'Lord of the underworld',
        'author': 'Daniel Baird',
        'llm_assisted': True,
        'stats_version': 1,
    }

    _NET = _load_net()

    def __init__(self, name='Hades', seed=None):
        self.name = name

    # ---- lifecycle ----

    def game_start(self, state):
        self._ev_log = []
        self._ctx = new_context() if _IMPORT_OK else None
        self._tracker = F.OpponentTracker(state.my_id) if _IMPORT_OK else None
        self._last_eid = -1
        self._top = None
        self._top_deck = -1

    def see_future(self, state, top3):
        self._top = [c.card_type for c in top3]
        self._top_deck = state.deck_size

    # ---- forward plumbing ----

    def _known_top(self, state):
        if self._top is not None and state.deck_size == self._top_deck:
            return self._top
        return None

    def _absorb(self, state):
        new = sorted([e for e in state.recent_events
                      if e.get('event_id', 0) > self._last_eid],
                     key=lambda e: e.get('event_id', 0))
        for ev in new:
            self._ev_log.append(encode_event(ev, state.my_id, self._ctx))
            self._last_eid = ev.get('event_id', self._last_eid)
        self._tracker.update(state)

    def _forward(self, state):
        hmem, _ = self._NET.encode(self._ev_log[-CONTEXT_WINDOW:])
        snap = F.encode(state, self._tracker, self._known_top(state))
        a2, _ = self._NET.trunk(hmem, np.asarray(snap, dtype=np.float64))
        return a2

    # ---- decisions ----

    def choose_action(self, state, valid_actions):
        if self._NET is None:
            non_draw = [a for a in valid_actions if a.action_type != ActionType.DRAW]
            return non_draw[0] if non_draw else Action(ActionType.DRAW)
        self._absorb(state)
        a2 = self._forward(state)
        by = {}
        for a in valid_actions:
            by.setdefault(a.action_type, []).append(a)
        mask = [1.0 if at in by else 0.0 for at in ACTIONS]
        if sum(mask) == 0:
            return Action(ActionType.DRAW)
        idx = _masked_argmax(self._NET.policy(a2), mask)
        if idx is None:
            return Action(ActionType.DRAW)
        at = ACTIONS[idx]
        acts = by.get(at) or [Action(ActionType.DRAW)]
        chosen = acts[0]
        if at in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
            tgt_scores = self._NET.target(a2)
            by_rel, tgt_mask = {}, [0.0] * N_TARGETS
            for a in acts:
                if a.target_player is not None:
                    rel = (a.target_player - state.my_id) % N_TARGETS
                    tgt_mask[rel] = 1.0
                    by_rel[rel] = a
            rel = _masked_argmax(tgt_scores, tgt_mask)
            chosen = by_rel.get(rel, acts[0])
            if at == ActionType.PLAY_CAT_TRIPLE:
                chosen = replace(chosen, named_card=DEF)
        return chosen

    def want_to_nope(self, state, action, currently_noped=False):
        if self._NET is None:
            return False
        self._absorb(state)
        a2 = self._forward(state)
        nctx = F.nope_context(state, action, currently_noped)
        logit, _ = self._NET.nope_logit(a2, np.asarray(nctx, dtype=np.float64))
        return bool(1.0 / (1.0 + np.exp(-np.clip(logit, -20, 20))) > 0.5)

    def give_card(self, state, requester_id):
        if self._NET is None or not state.my_hand:
            return state.my_hand[0].card_type if state.my_hand else DEF
        self._absorb(state)
        a2 = self._forward(state)
        hand_names = {c.card_type.name for c in state.my_hand}
        mask = [1.0 if n in hand_names else 0.0 for n in F.CARD_NAMES] + [0.0]
        idx = _masked_argmax(self._NET.give(a2), mask)
        if idx is None:
            return state.my_hand[0].card_type
        try:
            return CardType[F.CARD_NAMES[idx]]
        except (KeyError, IndexError):
            return state.my_hand[0].card_type

    def place_exploding_kitten(self, state, deck_size):
        if self._NET is None:
            return deck_size
        a2 = self._forward(state)
        mask = [0.0] * N_PLACE
        for i in range(min(deck_size + 1, N_PLACE)):
            mask[i] = 1.0
        idx = _masked_argmax(self._NET.place(a2), mask)
        if idx is None:
            return deck_size
        return min(idx, deck_size)
