import random

from pyexpat.errors import messages

from skull.agents.base import SkullAgent
from skull.discs import DiscType
from skull.state import ObservableState, Phase
from skull.actions import Action, ActionType

"""
Always place skull. Always place max bet

Test with:

python -m skull.run --agent "Ian1"
"""


class SkullPlacementToMaxBidProvider:
    def __init__(self, skullPlacementToPercentage: dict[bool, int]):
        self.skullPlacementToPercentage = skullPlacementToPercentage

    def get_percentage(self, is_skull_placed: bool) -> int:
        percentage = self.skullPlacementToPercentage.get(is_skull_placed)
        if percentage is None:
            raise Exception("missing case is_skull_placed condition")
        return percentage

class MaxBidPercentageProvider:
    def __init__(self, bid_to_percentage_map: dict[int, SkullPlacementToMaxBidProvider]):
        self.bidToPercentageMap = bid_to_percentage_map

    def get_max_bid(self, rng, is_skull_placed: bool) -> int:
        rolling_bid_percentage = [0]
        for bid, skull_placement_to_max_bid_provider in sorted(self.bidToPercentageMap.items()):
            percentage: int = skull_placement_to_max_bid_provider.get_percentage(is_skull_placed)
            rolling_bid_percentage.append(
                rolling_bid_percentage[len(rolling_bid_percentage) - 1] + percentage)
        if rolling_bid_percentage[len(rolling_bid_percentage) -  1] != 100:
            raise Exception(f"Percentages do not add to 100")
        rand_int = rng.randint(1, 100)
        for index, rolling_percentage in enumerate(rolling_bid_percentage):
            if rolling_percentage >= rand_int:
                # First number was 0 (not a bid just a baseline) so subtract by 1
                desired_bid_index = index - 1
                for bid_index, bid  in enumerate(sorted(self.bidToPercentageMap.keys())):
                    if bid_index == desired_bid_index:
                        return bid
        raise Exception("Bid not found")


class PlayersToMaxBidPercentageProvider:
    def __init__(self, playerCountToBidMap: dict[int, MaxBidPercentageProvider]):
        self.playerCountToBidMap = playerCountToBidMap

    def get_max_bid(self, rng: random.Random, player_count: int, isSkullPlaced: bool) -> int:
        max_bid_percentage_provider: MaxBidPercentageProvider | None = self.playerCountToBidMap.get(player_count)
        if max_bid_percentage_provider is None:
            raise Exception("Invalid player count")
        return max_bid_percentage_provider.get_max_bid(rng, isSkullPlaced)

class Ian1(SkullAgent):
    ARENA = {"name": "Ian1", "emoji": "🐼", "color": "#D9D9D9",
             "blurb": "Ian's Fist Attempt", "author": "Ian Brobin"}
    SECRET_META_VALUES1: list[int] = [0, 10, 20 , 30, 40, 50, 60, 70, 80, 90, 100]
    # Map of player count to bid as a percentage. Starting at 2
    SECRET_META_VALUES2: PlayersToMaxBidPercentageProvider = PlayersToMaxBidPercentageProvider({
        2: MaxBidPercentageProvider({
            1 : SkullPlacementToMaxBidProvider({
                True: 90,
                False: 90
            }),
            2: SkullPlacementToMaxBidProvider({
                True: 10,
                False: 10
            })}),
        3: MaxBidPercentageProvider({
            1 : SkullPlacementToMaxBidProvider({
                True: 80,
                False: 80
            }),
            2: SkullPlacementToMaxBidProvider({
                True: 10,
                False: 10
            }),
            3: SkullPlacementToMaxBidProvider({
                True: 10,
                False: 10
            })}),
        4: MaxBidPercentageProvider({
            1 : SkullPlacementToMaxBidProvider({
                True: 70,
                False: 70
            }),
            2: SkullPlacementToMaxBidProvider({
                True: 10,
                False: 10
            }),
            3: SkullPlacementToMaxBidProvider({
                True: 10,
                False: 10
            }),
            4: SkullPlacementToMaxBidProvider({
                True: 10,
                False: 10
            })}),
    })

    def __init__(self, name: str | None = None,
                 seed: int | None = None,
                 secret_meta_value1: int = 20,
                 secret_meta_value2: PlayersToMaxBidPercentageProvider  = SECRET_META_VALUES2):
        self.name = name or self.ARENA["name"]
        self.rng: random.Random = random.Random(seed)
        self.bomb_placement_percentage = secret_meta_value1
        self.bet_placement_percentage_map = secret_meta_value2

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        if self.rng.randint(0, 100) <= 50:
            return Action(ActionType.SAY, message="You'll pay for this")
        match state.phase:
            case Phase.PLACING:
                return self._get_placing_action(state, valid_actions)
            case Phase.BIDDING:
                return self._get_bidding_action(state, valid_actions)
            case Phase.REVEAL:
                return self._get_reveal_action(state, valid_actions)
            case Phase.DISCARD:
                return self._get_discard_action(state, valid_actions)
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
        desired_bid = self.bet_placement_percentage_map.get_max_bid(self.rng, len(state.alive_players),
                                                                    self._is_skull_placed(state))

        for action in valid_actions:
            if action.amount is not None and action.amount == desired_bid:
                return action
        return self._pass(valid_actions)

    def _pass(self, valid_actions):
        for action in valid_actions:
            if action.action_type == ActionType.PASS:
                return action
        raise Exception("Unable to find pass action")

    def _is_skull_placed(self, state: ObservableState):
        for discType in state.my_stack:
            if discType == DiscType.SKULL:
                return True
        return False

    def _get_reveal_action(self, state: ObservableState, valid_actions: list[Action]):
        for action in valid_actions:
            if action.target_player == state.my_id:
                return action
        return valid_actions[0]

    def _get_discard_action(self, state: ObservableState, valid_actions: list[Action]):
        # We flipped our own skull and must give up a disc. Keep the skull (it
        # lets us threaten challengers next round); sacrifice a rose if we can.
        for action in valid_actions:
            if action.disc_type == DiscType.ROSE:
                return action
        return valid_actions[0]

