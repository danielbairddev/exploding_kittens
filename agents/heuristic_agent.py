import random
from agents.base import Agent
from game.state import ObservableState
from game.actions import Action, ActionType
from game.cards import CardType, CAT_CARDS


# Card value ordering for "give_card" — give cheapest first
_GIVE_PRIORITY = [
    CardType.TACO_CAT, CardType.HAIRY_POTATO_CAT, CardType.BEARD_CAT,
    CardType.RAINBOW_CAT, CardType.CATTERMELON,
    CardType.NOPE, CardType.SKIP, CardType.SEE_THE_FUTURE,
    CardType.SHUFFLE, CardType.ATTACK, CardType.FAVOR,
]


class HeuristicAgent(Agent):
    """
    Basic heuristic agent. Strategy:
    - Always See the Future when possible (info advantage)
    - Shuffle or Skip if EK is known to be at top of deck
    - Counter-attack attacks with Nope ~70% of the time
    - Bury EK as deep as possible after defusing
    - Give the least valuable card when forced
    """

    ARENA = {"name": "Professor", "emoji": "\U0001F9E0", "color": "#818cf8",
             "blurb": "Counts cards, plays the odds.", "author": "Daniel Baird",
             "llm_assisted": True, "stats_version": 7}

    def __init__(self, name: str = "Heuristic", seed: int | None = None):
        self.name = name
        self.rng = random.Random(seed)
        self._known_top3: list | None = None
        self._last_deck_size: int = 0

    def game_start(self, state: ObservableState):
        self._known_top3 = None
        self._last_deck_size = state.deck_size

    def see_future(self, state: ObservableState, top3: list):
        self._known_top3 = top3
        self._last_deck_size = state.deck_size

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        # Invalidate future knowledge if deck has changed since we looked
        if self._known_top3 is not None and state.deck_size != self._last_deck_size:
            self._known_top3 = None

        ek_on_top = (
            self._known_top3 is not None and
            len(self._known_top3) > 0 and
            self._known_top3[0].card_type == CardType.EXPLODING_KITTEN
        )

        by_type = {a.action_type: a for a in valid_actions}

        if ek_on_top:
            # Don't draw — escape in priority order
            for escape in [ActionType.PLAY_SHUFFLE, ActionType.PLAY_SKIP, ActionType.PLAY_ATTACK]:
                if escape in by_type:
                    return by_type[escape]

        # Always take See the Future when available — pure upside
        if ActionType.PLAY_SEE_THE_FUTURE in by_type:
            return by_type[ActionType.PLAY_SEE_THE_FUTURE]

        # Burn off extra Attack turns with Skip
        if state.turns_remaining > 1 and ActionType.PLAY_SKIP in by_type:
            return by_type[ActionType.PLAY_SKIP]

        # Occasionally attack (30%) to offload our draw to someone else
        attack_actions = [a for a in valid_actions if a.action_type == ActionType.PLAY_ATTACK]
        if attack_actions and self.rng.random() < 0.30:
            return self.rng.choice(attack_actions)

        # Occasionally steal with cat pairs (20%)
        cat_actions = [a for a in valid_actions if a.action_type in (ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE)]
        if cat_actions and self.rng.random() < 0.20:
            chosen = self.rng.choice(cat_actions)
            if chosen.action_type == ActionType.PLAY_CAT_TRIPLE:
                from dataclasses import replace
                chosen = replace(chosen, named_card=CardType.DEFUSE)
            return chosen

        return Action(ActionType.DRAW)

    def want_to_nope(self, state: ObservableState, action: Action, currently_noped: bool = False) -> bool:
        if not any(c.card_type == CardType.NOPE for c in state.my_hand):
            return False

        i_am_actor = (state.my_id == state.current_player)

        # Counter-Nope: my action was cancelled — restore it
        if i_am_actor and currently_noped:
            if action.action_type in (ActionType.PLAY_ATTACK, ActionType.PLAY_SEE_THE_FUTURE,
                                      ActionType.PLAY_SHUFFLE, ActionType.PLAY_SKIP):
                return self.rng.random() < 0.80
            return self.rng.random() < 0.50

        # Don't Nope things that don't affect us, and don't Nope if action is already cancelled
        if currently_noped:
            return False

        # First Nope: block harmful actions aimed at us
        if action.action_type == ActionType.PLAY_ATTACK:
            return self.rng.random() < 0.70
        if action.action_type == ActionType.PLAY_FAVOR and action.target_player == state.my_id:
            return self.rng.random() < 0.50
        if action.action_type in (ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
            if action.target_player == state.my_id:
                return self.rng.random() < 0.40
        return False

    def give_card(self, state: ObservableState, requester_id: int) -> CardType:
        hand_types = {c.card_type for c in state.my_hand}
        for ct in _GIVE_PRIORITY:
            if ct in hand_types:
                return ct
        # Fallback: anything except Defuse
        safe = [c for c in state.my_hand if c.card_type != CardType.DEFUSE]
        pool = safe if safe else state.my_hand
        return self.rng.choice(pool).card_type

    def place_exploding_kitten(self, state: ObservableState, deck_size: int) -> int:
        # Bury as deep as possible
        return deck_size
