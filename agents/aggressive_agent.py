import random
from agents.base import Agent
from game.state import ObservableState
from game.actions import Action, ActionType
from game.cards import CardType


class AggressiveAgent(Agent):
    """
    Dumps its entire hand every turn — plays every possible card before drawing.
    On each choose_action call, picks a random non-DRAW action if one exists.
    Only draws when there is literally nothing left to play.
    """

    ARENA = {"name": "Maverick", "emoji": "\U0001F4A5", "color": "#f97316",
             "blurb": "Attack first, ask never.", "author": "Daniel Baird",
             "llm_assisted": True, "stats_version": 13}

    def __init__(self, name: str = "Aggressive", seed: int | None = None):
        self.name = name
        self.rng = random.Random(seed)

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        non_draw = [a for a in valid_actions if a.action_type != ActionType.DRAW]
        if non_draw:
            action = self.rng.choice(non_draw)
            # For triple combos, demand a Defuse if possible — otherwise any card
            if action.action_type == ActionType.PLAY_CAT_TRIPLE:
                from dataclasses import replace
                action = replace(action, named_card=CardType.DEFUSE)
            return action
        return Action(ActionType.DRAW)

    def want_to_nope(self, state: ObservableState, action: Action, currently_noped: bool = False) -> bool:
        # Always spend a Nope if we have one — don't care whether it's a Nope or counter-Nope
        return any(c.card_type == CardType.NOPE for c in state.my_hand)

    def give_card(self, state: ObservableState, requester_id: int) -> CardType:
        safe = [c for c in state.my_hand if c.card_type != CardType.DEFUSE]
        pool = safe if safe else state.my_hand
        return self.rng.choice(pool).card_type

    def place_exploding_kitten(self, state: ObservableState, deck_size: int) -> int:
        return deck_size
