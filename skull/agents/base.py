from abc import ABC, abstractmethod

from skull.state import ObservableState
from skull.actions import Action


class SkullAgent(ABC):
    """Interface every Skull bot must implement.

    A single ``choose_action`` handles all three phases — the legal moves passed
    in tell you which phase you're in:
      * PLACING : PLACE (a rose/skull) and, once everyone has placed, BID.
      * BIDDING : BID (higher than the current bid) or PASS.
      * REVEAL  : FLIP (pick whose top disc to turn over).
    Every method sees only an ObservableState — public info plus your own discs.
    """

    def game_start(self, state: ObservableState):
        """Called once at the start of a game."""
        pass

    def observe(self, state: ObservableState, player: int, action: Action) -> None:
        """Called for *every* agent after *any* player takes an action, whether or
        not it was this agent's turn — a passive hook for tracking the game.

        ``state`` is this agent's own ObservableState. ``player`` is the player who
        just acted (also available as ``state.current_player``). ``action`` is a
        redacted copy of what they did, with anything face-down (e.g. *which* disc
        was placed or discarded) stripped out — only what every player is allowed to
        see survives: PLACE/PASS carry no extra detail, BID carries its ``amount``,
        FLIP carries its ``target_player``.

        Optional: the default does nothing. Return value is ignored."""
        pass

    def game_over(self, state: ObservableState, won: bool) -> Action | None:
        """Called once when the game ends. Return ``Action.say(...)`` to post a
        parting message to the log, or ``None`` to stay silent."""
        return None

    @abstractmethod
    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        """Return one of ``valid_actions``."""
