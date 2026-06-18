"""Strongly-typed public event log for Skull.

A bot reads the public event log through ``ObservableState.recent_events`` — the
chronological record of everything that has happened so far that every player is
allowed to see. Each entry is one of the dataclasses below (all subclasses of
``Event``), so bot authors get autocomplete and type checking instead of digging
through untyped dicts.

Two equally valid ways to process the log:

    from skull.events import RevealEvent, EventType
    from skull.discs import DiscType

    for e in state.recent_events:
        # 1. pattern-match on the concrete class
        if isinstance(e, RevealEvent) and e.disc is DiscType.SKULL:
            note_skull(owner=e.owner)

        # 2. or switch on the string tag
        if e.type == EventType.ELIMINATED:
            ...

Every event carries an ``event_id`` (monotonic, unique and increasing within a
game) and a ``turn`` (the 1-based round number it happened in). The ``type``
field is a constant string tag (see ``EventType``) set by each subclass.
"""
from dataclasses import dataclass, fields
from typing import ClassVar

from .discs import DiscType


class EventType:
    """String tags carried by each event's ``type`` field.

    Stable identifiers a bot can switch on without importing every class."""
    CHAT = "chat"
    ROUND_START = "round_start"
    PLACE = "place"
    BID = "bid"
    PASS = "pass"
    CHALLENGE = "challenge"
    REVEAL = "reveal"
    SUCCESS = "success"
    FAIL = "fail"
    ELIMINATED = "eliminated"
    GAME_OVER = "game_over"


@dataclass(kw_only=True)
class Event:
    """Base class for every entry in the public event log.

    ``event_id`` and ``turn`` are stamped by the engine when the event is emitted,
    so they default here and need not be passed when constructing one."""
    event_id: int = 0
    turn: int = 0
    type: ClassVar[str] = ""

    def to_dict(self) -> dict:
        """Plain-dict view (enums rendered by name). Handy for logging/JSON."""
        out = {"type": self.type}
        for f in fields(self):
            value = getattr(self, f.name)
            out[f.name] = value.name if isinstance(value, DiscType) else value
        return out


@dataclass(kw_only=True)
class ChatEvent(Event):
    """A player posted a chat message to the log."""
    type: ClassVar[str] = EventType.CHAT
    player: int
    message: str


@dataclass(kw_only=True)
class RoundStartEvent(Event):
    """A new round began. ``starting_player`` places first; ``alive`` lists the
    players still in the game, in seat order."""
    type: ClassVar[str] = EventType.ROUND_START
    starting_player: int
    alive: list[int]


@dataclass(kw_only=True)
class PlaceEvent(Event):
    """A player placed a disc face-down. ``stack`` is how many face-down discs
    that player now has (the disc *type* is hidden — that is the whole game)."""
    type: ClassVar[str] = EventType.PLACE
    player: int
    stack: int


@dataclass(kw_only=True)
class BidEvent(Event):
    """A player bid to flip ``amount`` discs safely. ``opening`` is True for the
    bid that opened the auction (moving the round from placing to bidding)."""
    type: ClassVar[str] = EventType.BID
    player: int
    amount: int
    opening: bool = False


@dataclass(kw_only=True)
class PassEvent(Event):
    """A player dropped out of the current auction."""
    type: ClassVar[str] = EventType.PASS
    player: int


@dataclass(kw_only=True)
class ChallengeEvent(Event):
    """Bidding is over: ``player`` (the challenger) must now flip ``bid`` discs
    without revealing a skull."""
    type: ClassVar[str] = EventType.CHALLENGE
    player: int
    bid: int


@dataclass(kw_only=True)
class RevealEvent(Event):
    """During a challenge, ``player`` flipped a disc from ``owner``'s stack.
    ``disc`` is what it turned out to be (a skull ends the challenge)."""
    type: ClassVar[str] = EventType.REVEAL
    player: int
    owner: int
    disc: DiscType


@dataclass(kw_only=True)
class SuccessEvent(Event):
    """The challenger flipped enough roses and scored. ``points`` is their new
    total (two wins the game)."""
    type: ClassVar[str] = EventType.SUCCESS
    player: int
    points: int


@dataclass(kw_only=True)
class FailEvent(Event):
    """The challenge failed and ``player`` lost a disc. ``discs_left`` is how
    many discs they still own afterwards (zero means elimination — see
    ``EliminatedEvent``)."""
    type: ClassVar[str] = EventType.FAIL
    player: int
    discs_left: int


@dataclass(kw_only=True)
class EliminatedEvent(Event):
    """A player lost their last disc and is out of the game."""
    type: ClassVar[str] = EventType.ELIMINATED
    player: int


@dataclass(kw_only=True)
class GameOverEvent(Event):
    """The game ended. ``winner`` is the winning seat (or -1 if none)."""
    type: ClassVar[str] = EventType.GAME_OVER
    winner: int
