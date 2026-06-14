"""Perdition 2.1 — calibrated draw-aggressive loser.

58% of turns: ignores hand and draws immediately.
42% of turns: defers to Coyote's full strategy (the "defensive noise").
Gives away defuse cards on demand. Never nopes. Places EKs at top of deck.

Tuned so Biggest Loser first-out rate sits ~3pp above Ian1's natural rate.
"""
import random
from agents.coyote_agent import CoyoteAgent
from game.actions import ActionType
from game.cards import CardType


class Perdition2Agent(CoyoteAgent):
    ARENA = {
        'name': 'Perdition 2.1', 'emoji': '\U0001F975', 'color': '#5c0000',
        'blurb': '"And he went and hanged himself." — Matt 27:5',
        'author': 'Daniel Baird',
        'stats_version': 30,   # resets arena stats — new strategy
    }

    _P_COYOTE = 0.42   # fraction of turns that use Coyote's full strategy

    def choose_action(self, state, valid_actions):
        if random.random() < self._P_COYOTE:
            return super().choose_action(state, valid_actions)
        for a in valid_actions:
            if a.action_type == ActionType.DRAW:
                return a
        return valid_actions[0]

    def give_card(self, state, requester_id):
        for card in state.my_hand:
            if card.card_type == CardType.DEFUSE:
                return CardType.DEFUSE
        return state.my_hand[0].card_type

    def want_to_nope(self, state, action, currently_noped=False):
        return False

    def place_exploding_kitten(self, state, deck_size):
        return 0
