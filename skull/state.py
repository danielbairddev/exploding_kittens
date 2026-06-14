from dataclasses import dataclass, field

from .discs import Disc, DiscType


class Phase:
    """The three sub-phases of a Skull round."""
    PLACING = "placing"   # players lay discs face-down
    BIDDING = "bidding"   # players claim how many they can flip safely
    REVEAL = "reveal"     # the high bidder flips discs, hoping to avoid a skull


@dataclass
class PlayerState:
    player_id: int
    hand: list[Disc] = field(default_factory=list)    # discs not yet placed
    stack: list[Disc] = field(default_factory=list)   # placed face-down (index -1 = top)
    points: int = 0                                    # successful challenges
    alive: bool = True                                 # False once out of discs
    passed: bool = False                               # passed in the current bidding

    @property
    def disc_count(self) -> int:
        """Total discs the player still owns (in hand + on the table)."""
        return len(self.hand) + len(self.stack)

    def take_from_hand(self, disc_type: DiscType) -> Disc:
        for i, d in enumerate(self.hand):
            if d.disc_type == disc_type:
                return self.hand.pop(i)
        raise ValueError(f"Disc {disc_type} not in hand")


@dataclass
class GameState:
    """Full game state — only the engine and the owning agent see everything."""
    players: list[PlayerState]
    current_player: int
    starting_player: int = 0
    phase: str = Phase.PLACING
    current_bid: int = 0
    highest_bidder: int | None = None
    round_number: int = 0

    @property
    def alive_players(self) -> list[PlayerState]:
        return [p for p in self.players if p.alive]

    @property
    def discs_on_table(self) -> int:
        return sum(len(p.stack) for p in self.players if p.alive)


@dataclass
class ObservableState:
    """What an agent is allowed to see on its turn."""
    my_id: int
    phase: str
    my_hand: list[DiscType]              # your own undealt discs (you know these)
    my_stack: list[DiscType]            # your own face-down discs (you placed them)
    stack_sizes: dict[int, int]          # player_id -> face-down disc count
    disc_counts: dict[int, int]          # player_id -> total discs still owned
    points: dict[int, int]               # player_id -> challenges won
    alive_players: list[int]
    current_bid: int
    highest_bidder: int | None
    total_on_table: int
    current_player: int
    recent_events: list[dict] = field(default_factory=list)
