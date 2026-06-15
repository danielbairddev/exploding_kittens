import random

from skull.agents.base import SkullAgent
from skull.state import ObservableState
from skull.actions import Action


class RandomSkullAgent(SkullAgent):
    """Plays a uniformly random legal move — the floor every bot should beat."""

    ARENA = {"name": "Lucky", "emoji": "\U0001F3B2", "color": "#f472b6",
             "blurb": "No plan. Flips and hopes.", "author": "Ian Brobin"}

    def __init__(self, name: str | None = None, seed: int | None = None):
        self.name = name or self.ARENA["name"]
        self.rng = random.Random(seed)

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        return self.rng.choice(valid_actions)

    def game_over(self, state: ObservableState, won: bool) -> Action | None:
        return Action.say("I'm lucky") if won else None
