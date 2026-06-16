"""Perdition 2.1 — neural-net loser, trained to avoid winning.

Same architecture and self-sabotage hooks as Perdition2, with weights
from a longer ian_folder run that achieved a lower win rate. Handicap tuned
to narrowly beat Ian's bots in the Biggest Loser arena (first-to-explode).
"""
import json
import os
import random
from agents.coyote_agent import CoyoteAgent
from agents.orangutan_features import encode, ACTIONS
from game.actions import Action, ActionType
from game.cards import CardType

DEF = CardType.DEFUSE

# Fraction of turns replaced with a random action.
# At 0% the trained policy is ~57% first-out; Ian1 sits at ~41%.
# At 62% the trained policy barely edges Ian1 (~+1-2pp).
_ARENA_HANDICAP = 0.0

_WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "perdition2_weights.json")


def _load_weights():
    try:
        with open(_WEIGHTS_PATH) as f:
            w = json.load(f)
        if all(k in w for k in ("W1", "b1", "W2", "b2", "W3", "b3")):
            return w
    except (OSError, ValueError):
        pass
    return None


class Perdition2Agent(CoyoteAgent):
    ARENA = {
        'name': 'Perdition 2', 'emoji': '\U0001F975', 'color': '#5c0000',
        'blurb': '"And he went and hanged himself." — Matt 27:5',
        'author': 'Daniel Baird',
        'stats_version': 30,   # reset stats — renamed + retuned
    }

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
        if _ARENA_HANDICAP > 0.0 and not getattr(self, '_play_mode', False) and random.random() < _ARENA_HANDICAP:
            return random.choice(valid_actions)
        if self._WEIGHTS is None:
            return super().choose_action(state, valid_actions)

        by_type = {}
        for a in valid_actions:
            by_type.setdefault(a.action_type, []).append(a)

        feats = encode(state, self._known_list(state))
        logits = self._policy_logits(feats)

        best_idx, best_val = None, None
        for i, at in enumerate(ACTIONS):
            if at in by_type and (best_val is None or logits[i] > best_val):
                best_idx, best_val = i, logits[i]
        if best_idx is None:
            return Action(ActionType.DRAW)

        at = ACTIONS[best_idx]
        acts = by_type[at]
        if at in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
            chosen = self._best_target(acts, state)
            if at == ActionType.PLAY_CAT_TRIPLE:
                from dataclasses import replace
                chosen = replace(chosen, named_card=DEF)
            return chosen
        return acts[0]

    def place_exploding_kitten(self, state, deck_size):
        return 0

    def give_card(self, state, requester_id):
        for card in state.my_hand:
            if card.card_type == DEF:
                return DEF
        return state.my_hand[0].card_type

    def want_to_nope(self, state, action, currently_noped=False):
        return False
