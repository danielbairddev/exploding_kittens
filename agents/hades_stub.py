"""Hades stub — benched noop skeleton. No ML, no weights.

Drop-in placeholder for the arena roster while the real architecture is
being designed. All decisions fall back to safe defaults:
  - choose_action: play any non-DRAW action first, else DRAW
  - want_to_nope:  never nope
  - give_card:     give the first card in hand
  - place_exploding_kitten: bury at bottom
  - see_future:    no-op

To activate: replace HadesStubAgent with HadesAgent in ARENA_BOTS once
agents/hades_agent.py has trained weights.
"""
import random

from agents.base import Agent
from game.actions import Action, ActionType
from game.cards import CardType


class HadesStubAgent(Agent):
    ARENA = {
        'name':  'Hades',
        'emoji': '💀',
        'color': '#1e293b',
        'blurb': 'Lord of the underworld. Coming soon.',
        'stats_version': 1,
    }

    def __init__(self, name='Hades', seed=None):
        self.name = name
        self._rng = random.Random(seed)

    def game_start(self, state):
        pass

    def choose_action(self, state, valid_actions):
        # Play anything other than DRAW if possible, else DRAW
        non_draw = [a for a in valid_actions if a.action_type != ActionType.DRAW]
        if non_draw:
            return self._rng.choice(non_draw)
        return Action(ActionType.DRAW)

    def want_to_nope(self, state, action, currently_noped=False):
        return False

    def give_card(self, state, requester_id):
        return state.my_hand[0].card_type if state.my_hand else CardType.DEFUSE

    def place_exploding_kitten(self, state, deck_size):
        return deck_size

    def see_future(self, state, top3):
        pass
