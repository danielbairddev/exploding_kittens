import random
from agents.base import Agent
from game.state import ObservableState
from game.actions import Action, ActionType
from game.cards import CardType


class RandomAgent(Agent):
    """Plays randomly — useful as a baseline."""

    def __init__(self, name: str = "Random", seed: int | None = None):
        self.name = name
        self.rng = random.Random(seed)

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        return self.rng.choice(valid_actions)

    def want_to_nope(self, state: ObservableState, action: Action) -> bool:
        return self.rng.random() < 0.2 if state.my_hand and any(
            c.card_type == CardType.NOPE for c in state.my_hand
        ) else False

    def give_card(self, state: ObservableState, requester_id: int) -> CardType:
        # Give a random non-Defuse card if possible
        safe = [c for c in state.my_hand if c.card_type != CardType.DEFUSE]
        pool = safe if safe else state.my_hand
        return self.rng.choice(pool).card_type

    def place_exploding_kitten(self, state: ObservableState, deck_size: int) -> int:
        return self.rng.randint(0, deck_size)
