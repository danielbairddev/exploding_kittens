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
    PLAY_CAT_PAIR = auto()      # 2 matching cats — steals a random card from target
    PLAY_CAT_TRIPLE = auto()    # 3 matching cats — demands a named card from target
    DEFUSE = auto()             # internal — triggered automatically on explode


@dataclass
class Action:
    action_type: ActionType
    target_player: int | None = None        # for FAVOR, CAT_PAIR, CAT_TRIPLE
    cat_type: CardType | None = None        # for CAT_PAIR, CAT_TRIPLE
    named_card: CardType | None = None      # for CAT_TRIPLE (card being demanded)
    defuse_position: int | None = None      # for DEFUSE (where to reinsert EK)

    def __repr__(self):
        parts = [self.action_type.name]
        if self.target_player is not None:
            parts.append(f"target={self.target_player}")
        if self.cat_type is not None:
            parts.append(f"cat={self.cat_type.name}")
        if self.named_card is not None:
            parts.append(f"want={self.named_card.name}")
        return f"Action({', '.join(parts)})"
