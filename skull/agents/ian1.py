import copy
import math
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

NUMBER_OF_FIELDS_TO_MUTATE = 4
MAX_CHANGE_IN_MUTATION = 50



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


class Genes:
    def __init__(self, values: list[float], rng: random.Random):
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
        new_values = copy.deepcopy(self.values)
        for index_to_mutate in indexes_to_mutate:
            delta = self.rng.randint(-MAX_CHANGE_IN_MUTATION, MAX_CHANGE_IN_MUTATION)
            new_values[index_to_mutate] += delta
        return Genes(new_values, self.rng)

    def normalize(self) -> "Genes":
        new_values = copy.deepcopy(self.values)
        for i in range(len(new_values)):
            if new_values[i] > 100:
                new_values[i] = 100
            elif new_values[i] < 0:
                new_values[i] = 0
        index = 1
        for pair_size in range(2,5):
            sum_true_values = 0
            for i in range(pair_size):
                sum_true_values += new_values[index + (i * 2)]
            for i in range(pair_size):
                index_to_normalize = index + (i * 2)
                new_values[index_to_normalize] = new_values[index_to_normalize] / sum_true_values * 100
            sum_false_values = 0
            for i in range(pair_size):
                sum_false_values += new_values[index + 1 + (i * 2)]
            for i in range(pair_size):
                index_to_normalize = index + 1 + (i * 2)
                new_values[index_to_normalize] = new_values[index_to_normalize] / sum_false_values * 100
            index += pair_size * 2
        return Genes(new_values, self.rng)

    def __str__(self):
        return str(self.values)


'''
19 tunable values. If we have 10 options, we get 

'''
class Ian1(SkullAgent):
    ARENA = {"name": "Ian1", "emoji": "🐼", "color": "#D9D9D9",
             "blurb": "Ian's Fist Attempt", "author": "Ian Brobin"}
    SECRET_META_VALUES1: list[Genes] = [
        Genes([98, 44.230769230769226, 42.028985507246375, 55.769230769230774, 57.971014492753625, 39.74895397489539,
               10.218978102189782, 36.82008368200837, 21.897810218978105, 23.430962343096233, 67.88321167883211,
               36.61971830985916, 22.885572139303484, 7.042253521126761, 22.388059701492537, 50.0, 31.8407960199005,
               6.338028169014084, 22.885572139303484],
              random.Random()),
        Genes([100, 62.0, 35.333333333333336, 38.0, 64.66666666666666, 46.71052631578947, 15.822784810126583,
               28.289473684210524, 12.658227848101266, 25.0, 71.51898734177216, 22.666666666666664, 16.10738255033557,
               32.0, 19.463087248322147, 44.0, 17.449664429530202, 1.3333333333333335, 46.97986577181208],
              random.Random()),
        Genes([100, 54.54545454545454, 29.577464788732392, 45.45454545454545, 70.4225352112676, 40.52287581699346,
                4.225352112676056, 33.33333333333333, 25.352112676056336, 26.143790849673206, 70.4225352112676,
                29.333333333333332, 19.10828025477707, 36.666666666666664, 25.477707006369428, 34.0,
                19.745222929936308, 0.0, 35.6687898089172], random.Random()),
        Genes([100, 20.634920634920633, 0.9900990099009901, 79.36507936507937, 99.00990099009901,
               9.917355371900827, 3.8461538461538463, 82.64462809917356, 0.0, 7.43801652892562, 96.15384615384616,
               48.18652849740933, 5.88235294117647, 51.813471502590666, 10.457516339869281, 0.0, 18.30065359477124,
               0.0, 65.359477124183],
              random.Random())]

    def __init__(self, name: str | None = None,
                 seed: int | None = None,
                 secret_meta_value1: Genes = SECRET_META_VALUES1[0]):
        self.name = name or self.ARENA["name"]
        self.seed = seed
        self.rng: random.Random = random.Random(seed)
        if secret_meta_value1 is None:
            raise Exception("Must pass in gene")
        self.gene = secret_meta_value1
        self.bomb_placement_percentage = secret_meta_value1.values[0]
        self.bet_placement_percentage_map = PlayersToMaxBidPercentageProvider.from_list(secret_meta_value1.values[1:])

    def breed(self, other: "Ian1") -> "Ian1":
        return Ian1(self.name, self.seed, self.gene.breed(other.gene))

    def mutate(self):
        return Ian1(self.name, self.seed, self.gene.mutate())

    def normalize(self):
        return Ian1(self.name, self.seed, self.gene.normalize())

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
