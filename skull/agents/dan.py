import random

from skull.agents.base import SkullAgent
from skull.state import ObservableState
from skull.actions import Action


class DanBot(SkullAgent):
    """Plays a uniformly random legal move — the floor every bot should beat."""

    ARENA = {"name": "Bongos", "emoji": "😀", "color": "#ff7800",
             "blurb": "idk", "author": "Dan"}

    def __init__(self, name: str | None = None, seed: int | None = None):
        self.name = name or self.ARENA["name"]
        self.rng = random.Random(seed)

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        Action.say("I'm the joker!")
        return self.rng.choice(valid_actions)

    def game_over(self, state: ObservableState, won: bool) -> Action | None:
        return Action.say("I'm lucky") if won else None
