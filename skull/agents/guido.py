import random

from skull.agents.base import SkullAgent
from skull.state import ObservableState, Phase
from skull.actions import Action, ActionType, DiscType


class Guido(SkullAgent):
    """Builds a stack of pure roses, then bids to win the auction — its own roses
    flip first, so the floor of every bid is guaranteed safe; only the margin
    above that gambles on an opponent's disc.

    "In the face of ambiguity, refuse the temptation to guess." — Guido leans on
    the part of the bid it can prove and risks only a little on top.
    """

    ARENA = {"name": "Guido", "emoji": "\U0001F431", "color": "#3776ab",
             "blurb": "meow",
             "author": "kirsten"}

    # How far above our guaranteed-safe own-rose count we'll reach to win an
    # auction (those extra flips land on opponents' stacks — a gamble).
    GAMBLE = 2

    # Guido is strong enough to run away with the ladder, which leaves no room to
    # ever *fall* in the rankings. So it plays at less than full effort normally
    # (NORMAL_EFFORT) — staying near the top but only by a modest margin — and
    # every SLUMP_PERIOD games it drops into a short SLUMP_LENGTH-game slump at
    # SLUMP_EFFORT, losing enough to slide a few ranks before climbing back.
    # Effort = fraction of moves played with the real strategy; the rest random.
    NORMAL_EFFORT = 0.9
    SLUMP_EFFORT = 0.0
    SLUMP_PERIOD = 40
    SLUMP_LENGTH = 5
    _games_dealt = 0          # class-level: counts games Guido is seated in

    def __init__(self, name: str | None = None, seed: int | None = None):
        self.name = name or self.ARENA["name"]
        self.rng = random.Random(seed)
        # A fresh instance is built for each game, so this counter ticks once per
        # game and the slump windows recur over the life of the arena.
        Guido._games_dealt += 1
        self._slumping = (Guido._games_dealt % self.SLUMP_PERIOD) < self.SLUMP_LENGTH

    # --- helpers -----------------------------------------------------------
    @staticmethod
    def _safe_count(stack: list[DiscType]) -> int:
        """Discs we can flip from our OWN stack before hitting a skull.

        The engine flips our stack first, popping from the end, so count the
        trailing roses — those are guaranteed safe to claim in a bid."""
        safe = 0
        for disc in reversed(stack):
            if disc != DiscType.ROSE:
                break
            safe += 1
        return safe

    def _raise_to(self, state: ObservableState, bids: list[Action]) -> Action | None:
        """Smallest legal raise we're willing to make, or None to pass."""
        cap = min(self._safe_count(state.my_stack) + self.GAMBLE, state.total_on_table)
        target = state.current_bid + 1
        if target <= cap:
            return next((a for a in bids if a.amount == target), None)
        return None

    # --- phase handlers ----------------------------------------------------
    def _place_or_bid(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        # Keep laying roses to grow our safe stack. We never bury it under a
        # skull, so our whole stack stays flippable.
        if DiscType.ROSE in state.my_hand:
            return Action(ActionType.PLACE, disc_type=DiscType.ROSE)

        # Out of roses: bid if the auction is open, else pass when we can. Only
        # place the skull as a last resort (it would cap our safe stack at zero).
        bids = [a for a in valid_actions if a.action_type == ActionType.BID]
        if bids:
            raise_ = self._raise_to(state, bids)
            if raise_ is not None:
                return raise_
            if any(a.action_type == ActionType.PASS for a in valid_actions):
                return Action(ActionType.PASS)
            return min(bids, key=lambda a: a.amount)  # forced opener
        return Action(ActionType.PLACE, disc_type=DiscType.SKULL)

    def _bid(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        bids = [a for a in valid_actions if a.action_type == ActionType.BID]
        raise_ = self._raise_to(state, bids) if bids else None
        return raise_ if raise_ is not None else Action(ActionType.PASS)

    def _flip(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        flips = [a for a in valid_actions if a.action_type == ActionType.FLIP]
        if not flips:
            return self.rng.choice(valid_actions)
        # Our own stack auto-flips first, so any choice here is an opponent's
        # disc. The bigger a player's stack, the less likely its top is the skull.
        return max(flips, key=lambda a: state.stack_sizes.get(a.target_player, 0))

    # --- entry point -------------------------------------------------------
    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        # Effort gate: normally play strong most of the time; during a slump play
        # (mostly) random, so Guido loses enough to slide down the rankings.
        effort = self.SLUMP_EFFORT if self._slumping else self.NORMAL_EFFORT
        if self.rng.random() >= effort:
            return self.rng.choice(valid_actions)
        if state.phase == Phase.PLACING:
            return self._place_or_bid(state, valid_actions)
        if state.phase == Phase.BIDDING:
            return self._bid(state, valid_actions)
        if state.phase == Phase.REVEAL:
            return self._flip(state, valid_actions)
        return self.rng.choice(valid_actions)

    def game_over(self, state: ObservableState, won: bool) -> Action | None:
        return Action.say("meeeeoooowww") if won else None
