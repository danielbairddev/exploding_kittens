from enum import Enum, auto


class CardType(Enum):
    EXPLODING_KITTEN = auto()
    DEFUSE = auto()
    ATTACK = auto()
    SKIP = auto()
    FAVOR = auto()
    SHUFFLE = auto()
    SEE_THE_FUTURE = auto()
    NOPE = auto()
    # Cat cards (used in pairs/triples to steal)
    TACO_CAT = auto()
    HAIRY_POTATO_CAT = auto()
    BEARD_CAT = auto()
    RAINBOW_CAT = auto()
    CATTERMELON = auto()


CAT_CARDS = {
    CardType.TACO_CAT,
    CardType.HAIRY_POTATO_CAT,
    CardType.BEARD_CAT,
    CardType.RAINBOW_CAT,
    CardType.CATTERMELON,
}


class Card:
    def __init__(self, card_type: CardType):
        self.card_type = card_type

    def __repr__(self):
        return f"Card({self.card_type.name})"

    def __eq__(self, other):
        return isinstance(other, Card) and self.card_type == other.card_type

    def __hash__(self):
        return hash(self.card_type)


def build_deck(n_players: int) -> list[Card]:
    """Build and return a shuffled deck (without exploding kittens/defuses — added separately)."""
    counts = {
        CardType.ATTACK: 4,
        CardType.SKIP: 4,
        CardType.FAVOR: 4,
        CardType.SHUFFLE: 4,
        CardType.SEE_THE_FUTURE: 5,
        CardType.NOPE: 5,
        CardType.TACO_CAT: 4,
        CardType.HAIRY_POTATO_CAT: 4,
        CardType.BEARD_CAT: 4,
        CardType.RAINBOW_CAT: 4,
        CardType.CATTERMELON: 4,
        # Extra defuses go in the deck (each player gets 1 dealt separately)
        CardType.DEFUSE: max(0, 6 - n_players),
    }
    return [Card(ct) for ct, n in counts.items() for _ in range(n)]
