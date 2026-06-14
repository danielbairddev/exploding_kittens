from dataclasses import dataclass
from enum import Enum, auto

from .discs import DiscType


class ActionType(Enum):
    PLACE = auto()    # put one of your discs face-down on your own stack
    BID = auto()      # claim you can flip `amount` roses without hitting a skull
    PASS = auto()     # drop out of the bidding for this round
    FLIP = auto()     # during the reveal: flip the top disc of `target_player`


@dataclass
class Action:
    action_type: ActionType
    disc_type: DiscType | None = None     # for PLACE
    amount: int | None = None             # for BID (number of discs claimed)
    target_player: int | None = None      # for FLIP (whose stack to flip)

    # Identity used for de-duplication and validation against the legal set.
    def key(self):
        return (self.action_type, self.disc_type, self.amount, self.target_player)

    def __repr__(self):
        parts = [self.action_type.name]
        if self.disc_type is not None:
            parts.append(f"disc={self.disc_type.name}")
        if self.amount is not None:
            parts.append(f"amount={self.amount}")
        if self.target_player is not None:
            parts.append(f"target={self.target_player}")
        return f"Action({', '.join(parts)})"
