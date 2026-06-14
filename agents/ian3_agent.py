"""Ian1 — a starter bot template.

Ian: this is your sandbox. The logic below is intentionally simple — peek when
you can, dodge a kitten you can see, otherwise draw. Edit any of the methods to
build your strategy. Each method has a TODO pointing at an easy first improvement.

Run a quick test of your bot vs the others:
    python3 main.py --agent ian1        # (after wiring it into main.py's map)
or just watch it on the live arena once it's in the roster.
"""
import random
from agents.base import Agent
from game.state import ObservableState
from game.actions import Action, ActionType
from game.cards import CardType

EK = CardType.EXPLODING_KITTEN
DEFUSE = CardType.DEFUSE


class Ian3Agent(Agent):
    # Shows up on the live leaderboard. Tweak name/emoji/color/blurb as you like.
    ARENA = {"name": "Ian The Bomb", "emoji": "💣", "color": "#8E27F5",
             "blurb": "Ian's Bomb bot. It's trying to die", "author": "Ian",
             "llm_assisted": False,  # True if weights/logic were LLM-assisted
             "stats_version": 2,
             }

    def __init__(self, name: str = "Ian1", seed: int | None = None):
        self.name = name
        self.rng = random.Random(seed)
        self._top = None          # the top cards we've peeked at (or None)
        self._top_deck = -1       # deck size when we peeked (to know if it's stale)

    def game_start(self, state: ObservableState):
        self._top = None
        self._top_deck = -1

    def see_future(self, state: ObservableState, top3: list):
        # Remember what we saw on top of the deck.
        self._top = [c.card_type for c in top3]
        self._top_deck = state.deck_size

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        return Action(ActionType.DRAW)

    def want_to_nope(self, state: ObservableState, action: Action, currently_noped: bool = False) -> bool:
        return False

    def give_card(self, state: ObservableState, requester_id: int) -> CardType:
        # Give away anything that isn't our Defuse.
        for c in state.my_hand:
            if c.card_type != DEFUSE:
                return c.card_type
        return state.my_hand[0].card_type

    def place_exploding_kitten(self, state: ObservableState, deck_size: int) -> int:
        return len(state.alive_players) - 1
