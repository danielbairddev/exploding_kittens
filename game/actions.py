from dataclasses import dataclass, field
from enum import Enum, auto
from .cards import CardType


class ActionType(Enum):
    DRAW = auto()
    PLAY_ATTACK = auto()
    PLAY_SKIP = auto()
    PLAY_FAVOR = auto()         # requires target
    PLAY_SHUFFLE = auto()
    PLAY_SEE_THE_FUTURE = auto()
    PLAY_NOPE = auto()
    PLAY_CAT_PAIR = auto()      # requires cat_type + target
    DEFUSE = auto()             # internal — triggered automatically on explode


@dataclass
class Action:
    action_type: ActionType
    target_player: int | None = None        # for FAVOR, CAT_PAIR
    cat_type: CardType | None = None        # for CAT_PAIR
    defuse_position: int | None = None      # for DEFUSE (where to reinsert EK)

    def __repr__(self):
        parts = [self.action_type.name]
        if self.target_player is not None:
            parts.append(f"target={self.target_player}")
        if self.cat_type is not None:
            parts.append(f"cat={self.cat_type.name}")
        return f"Action({', '.join(parts)})"
