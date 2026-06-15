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

    def game_over(self, state: ObservableState, won: bool) -> Action | None:
        """Called once when the game ends. Return ``Action.say(...)`` to post a
        parting message to the log, or ``None`` to stay silent."""
        return None

    @abstractmethod
    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        """Return one of ``valid_actions``."""
