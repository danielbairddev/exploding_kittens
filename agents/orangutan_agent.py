"""Orangutan — a neural-network agent.

A small MLP chooses the action type each turn; everything else (Nopes, giving
cards, kitten placement, See-the-Future tracking) is inherited from Coyote so
the bot is competent while the policy learns the hard part. Inference is pure
Python (no numpy), reading weights trained offline by train_orangutan.py. If no
trained weights are present yet, it transparently falls back to Coyote's logic.
"""
import json
import os
import random
from agents.coyote_agent import CoyoteAgent
from agents.orangutan_features import encode, ACTIONS, resolve_action
from game.actions import Action, ActionType
from game.cards import CardType

DEF = CardType.DEFUSE

# ---- Exploration (controls play diversity) ----
_EXPLORE_RATE = 0.30  # fraction of turns that explore randomly

_WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orangutan_weights.json")


def _load_weights():
    try:
        with open(_WEIGHTS_PATH) as f:
            w = json.load(f)
        if all(k in w for k in ("W1", "b1", "W2", "b2", "W3", "b3")):
            return w
    except (OSError, ValueError):
        pass
    return None


class OrangutanAgent(CoyoteAgent):
    # Blurb intentionally says nothing about what's under the hood.
    ARENA = {"name": "Orangutan", "emoji": "\U0001F9A7", "color": "#d2691c",
             "blurb": "Ooo ooo aah aah. 🍌", "author": "Daniel Baird",
             "llm_assisted": True, "stats_version": 27}

    # Loaded once and shared by every instance (fresh agents are made per game).
    _WEIGHTS = _load_weights()

    @staticmethod
    def _matvec(W, x, b):
        return [sum(wij * xj for wij, xj in zip(row, x)) + bi for row, bi in zip(W, b)]

    @staticmethod
    def _relu(v):
        return [x if x > 0 else 0.0 for x in v]

    def _policy_logits(self, feats):
        w = self._WEIGHTS
        h = self._relu(self._matvec(w["W1"], feats, w["b1"]))
        h = self._relu(self._matvec(w["W2"], h, w["b2"]))
        return self._matvec(w["W3"], h, w["b3"])

    def choose_action(self, state, valid_actions):
        if _EXPLORE_RATE > 0.0 and random.random() < _EXPLORE_RATE:
            return random.choice(valid_actions)
        if self._WEIGHTS is None:
            return super().choose_action(state, valid_actions)

        by_type = {}
        for a in valid_actions:
            by_type.setdefault(a.action_type, []).append(a)

        feats = encode(state, self._known_list(state))
        logits = self._policy_logits(feats)

        # Mask to legal action types, pick the best-scoring one.
        best_idx, best_val = None, None
        for i, at in enumerate(ACTIONS):
            if at in by_type and (best_val is None or logits[i] > best_val):
                best_idx, best_val = i, logits[i]
        if best_idx is None:
            return Action(ActionType.DRAW)

        at = ACTIONS[best_idx]
        acts = by_type[at]
        # Resolve target/named heuristically (biggest hand; triples demand Defuse).
        if at in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
            chosen = self._best_target(acts, state)
            if at == ActionType.PLAY_CAT_TRIPLE:
                from dataclasses import replace
                chosen = replace(chosen, named_card=DEF)
            return chosen
        return acts[0]
