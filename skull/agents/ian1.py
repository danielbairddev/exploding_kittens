import random

from skull.agents.base import SkullAgent
from skull.discs import DiscType
from skull.state import ObservableState, Phase
from skull.actions import Action, ActionType

"""
Always place skull. Always place max bet

Test with:

python -m skull.run --agent "Ian1"
"""


class Ian1(SkullAgent):
    ARENA = {"name": "Ian1", "emoji": "🐼", "color": "#D9D9D9",
             "blurb": "Ian's Fist Attempt", "author": "Ian Brobin"}
    SECRET_META_VALUES1: list[int] = [0, 10, 20 , 30, 40, 50, 60, 70, 80, 90, 100]
    # Map of player count to bid as a percentage. Starting at 2
    SECRET_META_VALUES2: dict[int, dict[int, int]] = {
        2: {0 : 80, 1 : 10, 2: 10},
        3: {0: 70, 1: 10, 2: 10, 3: 10},
        4: {0: 60, 1: 10, 2: 10, 3: 10, 4: 10}
    }

    def __init__(self, name: str | None = None,
                 seed: int | None = None,
                 secret_meta_value1: int = 20,
                 secret_meta_value2: dict[int, dict[int, int]] = SECRET_META_VALUES2):
        self.name = name or self.ARENA["name"]
        self.rng = random.Random(seed)
        self.bomb_placement_percentage = secret_meta_value1
        self.bet_placement_percentage_map = secret_meta_value2

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        match state.phase:
            case Phase.PLACING:
                return self._get_placing_action(state, valid_actions)
            case Phase.BIDDING:
                return self._get_bidding_action(state, valid_actions)
            case Phase.REVEAL:
                return self._get_reveal_action(state, valid_actions)
        return valid_actions[0]

    def _get_placing_action(self, state: ObservableState, valid_actions: list[Action]):
        if self._can_bid(valid_actions):
            return self._get_bidding_action(state, valid_actions)
        if self._should_place_skull():
            return self._place_skull(valid_actions)
        else:
            return self._place_rose(valid_actions)

    def _should_place_skull(self):
        rand_int = self.rng.randint(1, 100)
        if rand_int <= self.bomb_placement_percentage:
            return True
        return False

    def _place_skull(self, valid_actions: list[Action]) -> Action:
        for action in valid_actions:
            if action.disc_type == DiscType.SKULL:
                return action
        return valid_actions[0]

    def _place_rose(self, valid_actions: list[Action]) -> Action:
        for action in valid_actions:
            if action.disc_type == DiscType.ROSE:
                return action
        return valid_actions[0]

    def _can_bid(self, valid_actions: list[Action]) -> bool:
        for action in valid_actions:
            if action.action_type == ActionType.BID:
                return True
        return False

    def _get_bidding_action(self, state: ObservableState, valid_actions: list[Action]):
        placement_map = self.bet_placement_percentage_map.get(len(state.alive_players), None)
        if placement_map is None:
            print("ERROR: Value missing from placement map")
            return valid_actions[0]

        max_bid: int = -1
        max_bid_action: Action = None
        for action in valid_actions:
            if action.amount is not None and action.amount > max_bid:
                max_bid = action.amount
                max_bid_action = action
        if max_bid_action is not None:
            return max_bid_action
        return valid_actions[0]

    def _get_reveal_action(self, state: ObservableState, valid_actions: list[Action]):
        for action in valid_actions:
            if action.target_player == state.my_id:
                return action
        return valid_actions[0]