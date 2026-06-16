import math
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
        if not math.isclose(rolling_bid_percentage[len(rolling_bid_percentage) -  1], 100):
            raise Exception(f"Percentages do not add to 100, they add to {rolling_bid_percentage[len(rolling_bid_percentage) -  1]}")
        rand_int = rng.randint(1, 100)
        for index, rolling_percentage in enumerate(rolling_bid_percentage):
            if rolling_percentage >= rand_int:
                # First number was 0 (not a bid just a baseline) so subtract by 1
                desired_bid_index = index - 1
                for bid_index, bid  in enumerate(sorted(self.bidToPercentageMap.keys())):
                    if bid_index == desired_bid_index:
                        return bid
        return sorted(self.bidToPercentageMap.items())[-1][0]


class PlayersToMaxBidPercentageProvider:
    def __init__(self, playerCountToBidMap: dict[int, MaxBidPercentageProvider]):
        self.playerCountToBidMap = playerCountToBidMap

    @classmethod
    def from_list(cls, values: list[int]):
        if len(values) != 18:
            raise Exception("Must pass in list of 18 items")
        return cls({
        2: MaxBidPercentageProvider({
            1 : SkullPlacementToMaxBidProvider({
                True: values[0],
                False: values[1]
            }),
            2: SkullPlacementToMaxBidProvider({
                True: values[2],
                False: values[3]
            })}),
        3: MaxBidPercentageProvider({
            1 : SkullPlacementToMaxBidProvider({
                True: values[4],
                False: values[5]
            }),
            2: SkullPlacementToMaxBidProvider({
                True: values[6],
                False: values[7]
            }),
            3: SkullPlacementToMaxBidProvider({
                True: values[8],
                False: values[9]
            })}),
        4: MaxBidPercentageProvider({
            1 : SkullPlacementToMaxBidProvider({
                True: values[10],
                False: values[11]
            }),
            2: SkullPlacementToMaxBidProvider({
                True: values[12],
                False: values[13]
            }),
            3: SkullPlacementToMaxBidProvider({
                True: values[14],
                False: values[15]
            }),
            4: SkullPlacementToMaxBidProvider({
                True: values[16],
                False: values[17]
            })}),
    })

    def get_max_bid(self, rng: random.Random, player_count: int, isSkullPlaced: bool) -> int:
        max_bid_percentage_provider: MaxBidPercentageProvider | None = self.playerCountToBidMap.get(player_count)
        if max_bid_percentage_provider is None:
            raise Exception("Invalid player count")
        return max_bid_percentage_provider.get_max_bid(rng, isSkullPlaced)

NUMBER_OF_FIELDS_TO_MUTATE = 4
MAX_CHANGE_IN_MUTATION = 10

class Genes:
    def __init__(self, values: list[int], rng: random.Random):
        self.values: list[int] = values
        self.rng = rng

    def breed(self, partner: "Genes") -> "Genes":
        new_values: list[int] = []
        for val1, val2 in zip(self.values, partner.values):
            new_val: int = round(val1 + val2 / 2)
            new_values.append(new_val)
        return Genes(new_values, self.rng)

    def mutate(self) -> "Genes":
        indexes_to_mutate = self.rng.sample(range(len(self.values)), NUMBER_OF_FIELDS_TO_MUTATE)
        for index_to_mutate in indexes_to_mutate:
            delta = self.rng.randint(-MAX_CHANGE_IN_MUTATION, MAX_CHANGE_IN_MUTATION)
            self.values[index_to_mutate] += delta
        return self

    def normalize(self) -> "Genes":
        if self.values[0] > 100:
            self.values[0] = 100
        if self.values[0] < 0:
            self.values[0] = 0
        index = 1
        for pair_size in range(2,5):
            sum_true_values = 0
            for i in range(pair_size):
                sum_true_values += self.values[index + (i * 2)]
            for i in range(pair_size):
                index_to_normalize = index + (i * 2)
                self.values[index_to_normalize] = self.values[index_to_normalize] / sum_true_values * 100
            sum_false_values = 0
            for i in range(pair_size):
                sum_false_values += self.values[index + 1 + (i * 2)]
            for i in range(pair_size):
                index_to_normalize = index + 1 + (i * 2)
                self.values[index_to_normalize] = self.values[index_to_normalize] / sum_false_values * 100
            index += pair_size * 2
        return self

    def __str__(self):
        return str(self.values)


'''
19 tunable values. If we have 10 options, we get 

'''
class Ian1(SkullAgent):
    ARENA = {"name": "Ian1", "emoji": "🐼", "color": "#D9D9D9",
             "blurb": "Ian's Fist Attempt", "author": "Ian Brobin"}
    SECRET_META_VALUES1: list[int] = [0, 10, 20 , 30, 40, 50, 60, 70, 80, 90, 100]
    # Map of player count to bid as a percentage. Starting at 2
    SECRET_META_VALUES2: Genes = Genes([98, 44.230769230769226, 42.028985507246375, 55.769230769230774, 57.971014492753625, 39.74895397489539, 10.218978102189782, 36.82008368200837, 21.897810218978105, 23.430962343096233, 67.88321167883211, 36.61971830985916, 22.885572139303484, 7.042253521126761, 22.388059701492537, 50.0, 31.8407960199005, 6.338028169014084, 22.885572139303484],
                                       random.Random())

    def __init__(self, name: str | None = None,
                 seed: int | None = None,
                 gene: Genes = SECRET_META_VALUES2):
        self.name = name or self.ARENA["name"]
        self.seed = seed
        self.rng: random.Random = random.Random(seed)
        if gene is None:
            raise Exception("Must pass in gene")
        self.gene = gene
        self.bomb_placement_percentage = gene.values[0]
        self.bet_placement_percentage_map = PlayersToMaxBidPercentageProvider.from_list(gene.values[1:])

    def breed(self, other: "Ian1") -> "Ian1":
        return Ian1(self.name, self.seed, self.gene.breed(other.gene))

    def mutate(self):
        return Ian1(self.name, self.seed, self.gene.mutate())

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
        if state.disc_counts[state.my_id] < 2:
            return self._discard_rose(valid_actions)
        return self._discard_skull(valid_actions)

    def _discard_rose(self, valid_actions: list[Action]) -> Action:
        for action in valid_actions:
            if action.disc_type == DiscType.ROSE:
                return action
        return valid_actions[0]

    def _discard_skull(self, valid_actions: list[Action]) -> Action:
        for action in valid_actions:
            if action.disc_type == DiscType.SKULL:
                return action
        return valid_actions[0]
