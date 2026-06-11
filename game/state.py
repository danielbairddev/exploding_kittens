from dataclasses import dataclass, field
from .cards import Card, CardType


@dataclass
class PlayerState:
    player_id: int
    hand: list[Card] = field(default_factory=list)
    alive: bool = True

    def has(self, card_type: CardType) -> bool:
        return any(c.card_type == card_type for c in self.hand)

    def remove(self, card_type: CardType) -> Card:
        for i, c in enumerate(self.hand):
            if c.card_type == card_type:
                return self.hand.pop(i)
        raise ValueError(f"Card {card_type} not in hand")


@dataclass
class GameState:
    """Full game state — only the engine and the owning agent see everything."""
    players: list[PlayerState]
    draw_pile: list[Card]          # index 0 = top
    discard_pile: list[Card]
    current_player: int
    turns_remaining: int = 1       # >1 when under Attack
    turn_number: int = 0

    @property
    def alive_players(self) -> list[PlayerState]:
        return [p for p in self.players if p.alive]

    @property
    def deck_size(self) -> int:
        return len(self.draw_pile)


@dataclass
class ObservableState:
    """What an agent is allowed to see."""
    my_id: int
    my_hand: list[Card]
    hand_sizes: dict[int, int]      # player_id -> card count
    alive_players: list[int]
    deck_size: int
    discard_pile: list[Card]
    turns_remaining: int
    current_player: int
    # Populated after See the Future
    known_top3: list[Card] | None = None
