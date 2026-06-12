"""
Ian2 — a starter bot template.
"""
import random

from requests.packages import target

from agents.base import Agent
from game.state import ObservableState
from game.actions import Action, ActionType
from game.cards import CardType, Card

EK = CardType.EXPLODING_KITTEN
DEFUSE = CardType.DEFUSE

"""
Run a quick test of your bot vs the others:
    python3 main.py --agent ian1        # (after wiring it into main.py's map)
or just watch it on the live arena once it's in the roster.
"""
STEALING_ACTION_PRIORITY: list[ActionType] = [ActionType.PLAY_CAT_TRIPLE, ActionType.PLAY_FAVOR,
                                              ActionType.PLAY_CAT_PAIR]
REMAINING_ACTION_PRIORITY: list[ActionType] = [ActionType.PLAY_ATTACK, ActionType.PLAY_SKIP]
CARD_GIVE_AWAY_PRIORITY: list[CardType] = [CardType.EXPLODING_KITTEN, CardType.TACO_CAT, CardType.HAIRY_POTATO_CAT,
                                           CardType.BEARD_CAT, CardType.RAINBOW_CAT, CardType.CATTERMELON,
                                           CardType.FAVOR, CardType.SHUFFLE, CardType.SEE_THE_FUTURE, CardType.SKIP,
                                           CardType.ATTACK, CardType.NOPE, CardType.DEFUSE]



class Ian2Agent(Agent):
    # Shows up on the live leaderboard. Tweak name/emoji/color/blurb as you like.
    ARENA = {"name": "Ian2", "emoji": "🫦", "color": "#14b8a6",
             "blurb": "Yum", "author": "Ian",
             # TODO: set llm_assisted once Ian confirms
             }


    def __init__(self, name: str = "Ian1", seed: int | None = None):
        self.name = name
        self.rng = random.Random(seed)
        self._top_3_cards_on_peek: list[Card] | None = None          # the top cards we've peeked at (or None)
        self._deck_size_on_peek = -1       # deck size when we peeked (to know if it's stale)

    def game_start(self, state: ObservableState):
        self._top_3_cards_on_peek = None
        self._deck_size_on_peek = -1

    def see_future(self, state: ObservableState, top3: list[Card]):
        # Remember what we saw on top of the deck.
        self._top_3_cards_on_peek = [c.card_type for c in top3]
        self._deck_size_on_peek = state.deck_size

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        players_size = len(state.alive_players)
        exploding_kittens_in_deck = state.deck_exploding_kittens_count
        deck_size = state.deck_size
        chance_of_getting_bombed = exploding_kittens_in_deck / deck_size
        chance_of_randomly_wining = 1 / players_size

        we_expect_a_bomb_on_top = self.do_we_expect_a_bomb_on_top(state)

        if not we_expect_a_bomb_on_top and chance_of_randomly_wining > chance_of_getting_bombed:
            return Action(ActionType.DRAW)

        players_defuse_count: dict[int, int] = self.get_players_defuse_count(state)
        playerWithHighestDefuseRatio = None
        highestDefuseRatio = -1
        for player, defuses in players_defuse_count.items():
            if defuses > 1:
                hand_size = state.hand_sizes[player]
                ratio = hand_size / defuses
                if ratio > highestDefuseRatio:
                    highestDefuseRatio = ratio
                    playerWithHighestDefuseRatio = player

        if highestDefuseRatio > 0:
            for preferred_action_type in STEALING_ACTION_PRIORITY:
                for action in valid_actions:
                    if (action.action_type == preferred_action_type and
                            action.target_player == playerWithHighestDefuseRatio):
                        if action.action_type == ActionType.PLAY_CAT_TRIPLE:
                            if action.named_card == CardType.DEFUSE:
                                return action
                        else:
                            return action
        for action in valid_actions:
            if action.action_type == ActionType.PLAY_SEE_THE_FUTURE:
                return action
        if self.do_we_know_a_bomb_is_on_top(state):
            for action in valid_actions:
                if action.action_type == ActionType.DRAW:
                    return action
        for preferred_action_type in REMAINING_ACTION_PRIORITY:
            for action in valid_actions:
                if action.action_type == preferred_action_type:
                    return action

        return Action(ActionType.DRAW)

    def do_we_expect_a_bomb_on_top(self, state: ObservableState) -> bool:
        if self.do_we_know_a_bomb_is_on_top(state) or self.did_the_last_player_get_exploded(state):
            return True
        return False

    def do_we_know_a_bomb_is_on_top(self, state: ObservableState) -> bool:
        if (state.deck_size == self._deck_size_on_peek and
                self._top_3_cards_on_peek is not None and len(self._top_3_cards_on_peek) > 1 and
                self._top_3_cards_on_peek[0] == CardType.EXPLODING_KITTEN):
            return True
        return False

    @staticmethod
    def did_the_last_player_get_exploded(state: ObservableState) -> bool:
        for event in state.recent_events:
            if "action_type" in event and event["player"] == state.my_id:
                continue
            if "action_type" in event and event["action_type"] == "explode":
                return True

        return False

    def get_players_defuse_count(self, state: ObservableState) -> dict[int, int]:
        defuse_count_map = {}
        for player in state.alive_players:
            defuse_count_map[player] = 1
        for event in state.recent_events[::-1]:
            if "action_type" in event and event["action_type"] == "defuse":
                exploded_player = event["player"]
                if exploded_player in defuse_count_map:
                    defuse_count_map[exploded_player] += 1
            elif "action_type" in event and event["action_type"] == "cat_steal":
                if "named_card" in event and event["named_card"] == DEFUSE.name:
                    target_player = event["target_player"]
                    steal_player = event["player"]
                    if target_player in defuse_count_map:
                        defuse_count_map[target_player] -= 1
                    if steal_player in defuse_count_map:
                        steal_player += 1

        return defuse_count_map



    def want_to_nope(self, state: ObservableState, action: Action, currently_noped: bool = False) -> bool:
        return False

    def give_card(self, state: ObservableState, requester_id: int) -> CardType:
        # Give away anything that isn't our Defuse.
        for preferredCardType in CARD_GIVE_AWAY_PRIORITY:
            for c in state.my_hand:
                if c.card_type == preferredCardType:
                    return c.card_type

        return state.my_hand[0].card_type

    def place_exploding_kitten(self, state: ObservableState, deck_size: int) -> int:
        return 0
