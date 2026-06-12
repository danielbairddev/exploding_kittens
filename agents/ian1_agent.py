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


class Ian1Agent(Agent):
    # Shows up on the live leaderboard. Tweak name/emoji/color/blurb as you like.
    ARENA = {"name": "Ian1", "emoji": "\U0001F331", "color": "#14b8a6",
             "blurb": "Ian's bot — a work in progress.", "author": "Ian"}

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

    # --- the main decision: what to do on your turn ---
    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        by_type = {a.action_type: a for a in valid_actions}

        # Our peek is only valid if the deck hasn't changed since we looked.
        top = self._top if state.deck_size == self._top_deck else None

        have_defuse = any(c.card_type == DEFUSE for c in state.my_hand)

        # 1) Peek at the deck if we have a See the Future and haven't already.
        if top is None and ActionType.PLAY_SEE_THE_FUTURE in by_type:
            return by_type[ActionType.PLAY_SEE_THE_FUTURE]

        # 2) If we can see a kitten on top, dodge it with Skip/Attack.
        if top and top[0] == EK:
            if ActionType.PLAY_SKIP in by_type:
                return by_type[ActionType.PLAY_SKIP]
            if ActionType.PLAY_ATTACK in by_type:
                return by_type[ActionType.PLAY_ATTACK]
            return Action(ActionType.DRAW)   # forced — our Defuse will save us

        # 3) Top is known safe → draw the free card.
        if top and top[0] != EK:
            return Action(ActionType.DRAW)

        # 4) Top unknown. If we hold a Defuse it's our insurance, so drawing is fine.
        if have_defuse:
            return Action(ActionType.DRAW)

        # 5) No Defuse and flying blind — dodge if we can, else draw and hope.
        # TODO Ian: this is the core trade-off to tune. Try cat-pair steals or Favor too.
        if ActionType.PLAY_SKIP in by_type:
            return by_type[ActionType.PLAY_SKIP]
        if ActionType.PLAY_ATTACK in by_type:
            return by_type[ActionType.PLAY_ATTACK]
        return Action(ActionType.DRAW)

    def want_to_nope(self, state: ObservableState, action: Action, currently_noped: bool = False) -> bool:
        # TODO Ian: return True (when you hold a Nope) to cancel an opponent's play —
        # e.g. an Attack aimed at you. For now we never Nope.
        return False

    def give_card(self, state: ObservableState, requester_id: int) -> CardType:
        # Give away anything that isn't our Defuse.
        for c in state.my_hand:
            if c.card_type != DEFUSE:
                return c.card_type
        return state.my_hand[0].card_type

    def place_exploding_kitten(self, state: ObservableState, deck_size: int) -> int:
        # Bury it at the bottom so it's safe for a while.
        # TODO Ian: returning 0 puts it on TOP — the next player draws it. Risky but mean.
        return deck_size
