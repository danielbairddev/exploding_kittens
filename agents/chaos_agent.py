import random
from agents.base import Agent
from game.state import ObservableState
from game.actions import Action, ActionType
from game.cards import CardType


class ChaosAgent(Agent):
    """
    Totally random on every decision — no heuristics whatsoever.
    - choose_action: uniform random pick from all valid actions (including DRAW)
    - want_to_nope: 50/50 coin flip if holding a Nope
    - give_card: truly random, will give away Defuses
    - place_exploding_kitten: random position in deck
    """

    ARENA = {"name": "Gremlin", "emoji": "\U0001F300", "color": "#4ade80",
             "blurb": "An agent of pure chaos.", "author": "Daniel Baird",
             "llm_assisted": True, "stats_version": 9}

    def __init__(self, name: str = "Chaos", seed: int | None = None):
        self.name = name
        self.rng = random.Random(seed)

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        return self.rng.choice(valid_actions)

    def want_to_nope(self, state: ObservableState, action: Action, currently_noped: bool = False) -> bool:
        has_nope = any(c.card_type == CardType.NOPE for c in state.my_hand)
        return has_nope and self.rng.random() < 0.5

    def give_card(self, state: ObservableState, requester_id: int) -> CardType:
        return self.rng.choice(state.my_hand).card_type

    def place_exploding_kitten(self, state: ObservableState, deck_size: int) -> int:
        return self.rng.randint(0, deck_size)
