from dataclasses import dataclass
from enum import Enum, auto

from .discs import DiscType


class ActionType(Enum):
    PLACE = auto()    # put one of your discs face-down on your own stack
    BID = auto()      # claim you can flip `amount` roses without hitting a skull
    PASS = auto()     # drop out of the bidding for this round
    FLIP = auto()     # during the reveal: flip the top disc of `target_player`
    DISCARD = auto()  # after flipping your own skull: pick which disc to give up
    SAY = auto()      # speak in the chat log; never offered as a legal move


@dataclass
class Action:
    action_type: ActionType
    disc_type: DiscType | None = None     # for PLACE
    amount: int | None = None             # for BID (number of discs claimed)
    target_player: int | None = None      # for FLIP (whose stack to flip)
    message: str | None = None            # for SAY (chat text to post to the log)

    # Identity used for de-duplication and validation against the legal set.
    # SAY is never validated against the legal set, so `message` is omitted here.
    def key(self):
        return (self.action_type, self.disc_type, self.amount, self.target_player)

    @classmethod
    def say(cls, message: str) -> "Action":
        """A chat message. Return this from ``choose_action`` to speak: the engine
        posts it to the event log and then asks you again for a real move."""
        return cls(ActionType.SAY, message=message)

    def __repr__(self):
        parts = [self.action_type.name]
        if self.disc_type is not None:
            parts.append(f"disc={self.disc_type.name}")
        if self.amount is not None:
            parts.append(f"amount={self.amount}")
        if self.target_player is not None:
            parts.append(f"target={self.target_player}")
        return f"Action({', '.join(parts)})"
