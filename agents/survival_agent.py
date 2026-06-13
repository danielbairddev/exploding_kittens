import random
from dataclasses import replace
from agents.base import Agent
from game.state import ObservableState
from game.actions import Action, ActionType
from game.cards import CardType, CAT_CARDS

# Cards we're happiest to give away (junk first), and would never hand over.
_GIVE_PRIORITY = [
    CardType.TACO_CAT, CardType.HAIRY_POTATO_CAT, CardType.BEARD_CAT,
    CardType.RAINBOW_CAT, CardType.CATTERMELON,
    CardType.SHUFFLE, CardType.FAVOR, CardType.SEE_THE_FUTURE,
    CardType.NOPE, CardType.SKIP, CardType.ATTACK,
]


class SurvivalAgent(Agent):
    """
    Survival-first, information-driven strategy built around the engine's real
    incentives:

    * See the Future is used purely as a draw-gate — know the top card before
      committing to a draw.
    * It never draws a KNOWN Exploding Kitten: it Attacks (dumps the loaded deck
      on the next player), Skips (leaving the kitten on top for them), or
      Shuffles — in that order.
    * A safe top is drawn for free, conserving Skips/Attacks for when they matter.
    * With a Defuse in hand, an unknown top is drawn rather than wasting a Skip
      (the Defuse is the insurance). Defuse-less, it avoids blind draws.
    * EK PLACEMENT IS A WEAPON: after defusing it puts the kitten back on TOP so
      the next player draws it — unless it's still mid-turn (under Attack) and
      would draw it itself.
    * It hunts Defuses with cat triples (naming DEFUSE) and protects its own with
      Nopes; Nopes are otherwise hoarded for attacks aimed at it and endgame
      denial.
    """

    ARENA = {"name": "Sly", "emoji": "\U0001F98A", "color": "#22d3ee",
             "blurb": "Survives by any means.", "author": "Daniel Baird",
             "llm_assisted": True, "stats_version": 23}

    def __init__(self, name: str = "Survival", seed: int | None = None):
        self.name = name
        self.rng = random.Random(seed)
        self._top: list | None = None      # known top cards (CardType), from See the Future
        self._seen_deck: int = -1          # deck size when we looked

    # ---- info tracking -------------------------------------------------
    def game_start(self, state: ObservableState):
        self._top = None
        self._seen_deck = -1

    def see_future(self, state: ObservableState, top3: list):
        self._top = [c.card_type for c in top3]
        self._seen_deck = state.deck_size

    def _known_top(self, state: ObservableState):
        """Return the known top CardType, or None if our knowledge is stale."""
        if self._top is not None and state.deck_size == self._seen_deck and self._top:
            return self._top[0]
        return None

    def _next_alive_id(self, state: ObservableState, after: int) -> int:
        order = sorted(state.alive_players)
        if after in order:
            i = order.index(after)
            return order[(i + 1) % len(order)]
        # `after` is dead/unknown — first alive after it in ring order
        for off in range(1, max(order) + 2):
            cand = (after + off) % (max(order) + 1)
            if cand in order:
                return cand
        return order[0]

    # ---- main turn logic ----------------------------------------------
    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        by_type: dict = {}
        for a in valid_actions:
            by_type.setdefault(a.action_type, []).append(a)

        def has(t):
            return t in by_type

        def first(t):
            return by_type[t][0]

        hand = [c.card_type for c in state.my_hand]
        n_defuse = hand.count(CardType.DEFUSE)
        alive = len(state.alive_players)
        deck = max(1, state.deck_size)
        under_attack = state.turns_remaining > 1
        top = self._known_top(state)
        top_ek = top == CardType.EXPLODING_KITTEN
        top_safe = top is not None and top != CardType.EXPLODING_KITTEN

        # --- Phase 1: non-terminal value plays (don't end the turn) ------
        # Gate behind the threat of an EK on top — survive first, then scheme.
        if not top_ek:
            # Peek before deciding to draw.
            if top is None and has(ActionType.PLAY_SEE_THE_FUTURE):
                return first(ActionType.PLAY_SEE_THE_FUTURE)

            # Steal a Defuse (or anything) with a cat triple — pure upside.
            if has(ActionType.PLAY_CAT_TRIPLE):
                act = self._best_target(by_type[ActionType.PLAY_CAT_TRIPLE], state)
                return replace(act, named_card=CardType.DEFUSE)

            # Cat pair: random steal from the biggest hand, used sparingly.
            if has(ActionType.PLAY_CAT_PAIR) and self.rng.random() < 0.55:
                return self._best_target(by_type[ActionType.PLAY_CAT_PAIR], state)

        # --- Phase 2: terminal decision (draw / skip / attack) ----------
        if top_ek:
            # Never draw a known kitten.
            if has(ActionType.PLAY_ATTACK):
                return first(ActionType.PLAY_ATTACK)   # dump the loaded deck on next player
            if has(ActionType.PLAY_SKIP):
                return first(ActionType.PLAY_SKIP)     # leave it on top for them
            if has(ActionType.PLAY_SHUFFLE):
                return first(ActionType.PLAY_SHUFFLE)  # re-randomise the certain death
            return Action(ActionType.DRAW)             # defuse if we can; else doomed

        if under_attack:
            if has(ActionType.PLAY_ATTACK):
                return first(ActionType.PLAY_ATTACK)   # bounce all forced turns onward
            if top_safe:
                return Action(ActionType.DRAW)
            if has(ActionType.PLAY_SKIP):
                return first(ActionType.PLAY_SKIP)     # cancel one forced turn
            if n_defuse > 0:
                return Action(ActionType.DRAW)
            if has(ActionType.PLAY_SHUFFLE):
                return first(ActionType.PLAY_SHUFFLE)
            return Action(ActionType.DRAW)

        if top_safe:
            return Action(ActionType.DRAW)             # free card, no risk — save the Skips

        # Unknown top, not under attack.
        if n_defuse > 0:
            return Action(ActionType.DRAW)             # the Defuse is our insurance

        # Defuse-less and flying blind: dodge the draw if we can.
        p_ek = (alive - 1) / deck
        if has(ActionType.PLAY_ATTACK):
            return first(ActionType.PLAY_ATTACK)       # pass the risk along for free
        if has(ActionType.PLAY_SKIP) and p_ek >= 0.10:
            return first(ActionType.PLAY_SKIP)
        return Action(ActionType.DRAW)

    def _best_target(self, actions: list[Action], state: ObservableState) -> Action:
        """Target the live opponent holding the most cards (biggest threat / loot)."""
        best, best_n = actions[0], -1
        for a in actions:
            n = state.hand_sizes.get(a.target_player, 0)
            if n > best_n:
                best, best_n = a, n
        return best

    # ---- nope policy ---------------------------------------------------
    def want_to_nope(self, state: ObservableState, action: Action, currently_noped: bool = False) -> bool:
        if not any(c.card_type == CardType.NOPE for c in state.my_hand):
            return False

        me = state.my_id
        actor = state.current_player
        i_am_actor = me == actor
        at = action.action_type

        # Restore my own cancelled escape/steal.
        if i_am_actor:
            if not currently_noped:
                return False
            if at in (ActionType.PLAY_ATTACK, ActionType.PLAY_SKIP):
                return True
            if at == ActionType.PLAY_CAT_TRIPLE:
                return self.rng.random() < 0.6
            return self.rng.random() < 0.3

        # Someone else's action. Only ever spend the FIRST nope (don't re-cancel).
        if currently_noped:
            return False

        # An Attack that lands on me — block it.
        if at == ActionType.PLAY_ATTACK and self._next_alive_id(state, actor) == me:
            return True
        # Protect my hand (and Defuse) from theft aimed at me.
        if at in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
            if action.target_player == me:
                return self.rng.random() < 0.7
        # Endgame denial: stop the last opponent from escaping a draw.
        if len(state.alive_players) == 2 and at in (ActionType.PLAY_SKIP, ActionType.PLAY_ATTACK):
            return self.rng.random() < 0.7
        return False

    def give_card(self, state: ObservableState, requester_id: int) -> CardType:
        hand_types = {c.card_type for c in state.my_hand}
        for ct in _GIVE_PRIORITY:
            if ct in hand_types:
                return ct
        safe = [c for c in state.my_hand if c.card_type != CardType.DEFUSE]
        pool = safe if safe else state.my_hand
        return self.rng.choice(pool).card_type

    # ---- the weapon ----------------------------------------------------
    def place_exploding_kitten(self, state: ObservableState, deck_size: int) -> int:
        # If we're still mid-turn (under Attack) we'd just draw it again — bury it.
        if state.turns_remaining > 1:
            return deck_size
        # Otherwise put it back on top so the NEXT player draws it.
        return 0
