"""Perdition — a neural-network agent trained to lose.

Same MLP architecture as Orangutan, but weights are trained with an inverted
reward: 0.0 for winning, 1.0 for any loss.  The behavioural hooks that the RL
loop never touches are hard-coded to be self-sabotaging:

  * place_exploding_kitten → always index 0 (bomb back on top; draw it next turn)
  * give_card              → donate Defuses first, then whatever
  * want_to_nope           → never Nope (let attacks land, let favors steal)

Falls back to the sabotage hooks even without trained weights.
"""
import json
import os
from agents.coyote_agent import CoyoteAgent
from agents.orangutan_features import encode, ACTIONS
from game.actions import Action, ActionType
from game.cards import CardType

DEF = CardType.DEFUSE
_WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "perdition_weights.json")


def _load_weights():
    try:
        with open(_WEIGHTS_PATH) as f:
            w = json.load(f)
        if all(k in w for k in ("W1", "b1", "W2", "b2", "W3", "b3")):
            return w
    except (OSError, ValueError):
        pass
    return None


class PerditionAgent(CoyoteAgent):
    ARENA = {"name": "Perdition", "emoji": "\U0001F979", "color": "#8b0000",
             "blurb": "\"It would be better for him if he had not been born.\" — Matt 26:24", "author": "Daniel Baird",
             "llm_assisted": True, "stats_version": 11}

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

    # --- self-sabotage hooks (not covered by RL training) ---

    def place_exploding_kitten(self, state, deck_size):
        """Put the bomb back on top — we'll draw it on our very next turn."""
        return 0

    def give_card(self, state, requester_id):
        """Hand over Defuses first; then fall back to the first card."""
        for card in state.my_hand:
            if card.card_type == DEF:
                return DEF
        return state.my_hand[0].card_type

    def want_to_nope(self, state, action, currently_noped=False):
        """Never Nope anything — let attacks land, let steals go through."""
        return False
