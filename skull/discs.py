from enum import Enum, auto


class DiscType(Enum):
    ROSE = auto()     # safe — flip these to win a challenge
    SKULL = auto()    # deadly — flipping one fails the challenge


class Disc:
    def __init__(self, disc_type: DiscType):
        self.disc_type = disc_type

    def __repr__(self):
        return f"Disc({self.disc_type.name})"

    def __eq__(self, other):
        return isinstance(other, Disc) and self.disc_type == other.disc_type

    def __hash__(self):
        return hash(self.disc_type)


# Every player starts with the same set: three roses and a single skull.
ROSES_PER_PLAYER = 3
SKULLS_PER_PLAYER = 1


def build_starting_hand() -> list[Disc]:
    """The four discs every player begins with: 3 roses + 1 skull."""
    return ([Disc(DiscType.ROSE)] * ROSES_PER_PLAYER
            + [Disc(DiscType.SKULL)] * SKULLS_PER_PLAYER)
