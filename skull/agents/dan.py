import random

from skull.agents.base import SkullAgent
from skull.state import ObservableState
from skull.actions import Action, ActionType


class DanBot(SkullAgent):
    """Plays a uniformly random legal move — the floor every bot should beat."""

    ARENA = {"name": "Bongos", "emoji": "😀", "color": "#ff7800",
             "blurb": "#1 Bot on site", "author": "Dan"}

    def __init__(self, name: str | None = None, seed: int | None = None):
        self.name = name or self.ARENA["name"]
        self.rng = random.Random(seed)

        self.last_action_say_say = False

    def return_say_action(self):
        self.last_action_say_say = True
        return Action.say("I'm the joker...")

    def return_non_say_action(self, action):
        self.last_action_say_say = False
        if action.action_type() == ActionType.SAY:
            raise Exception("Attempting to say a non-say action" + action)
        return action

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        if not self.last_action_say_say:
            return self.return_say_action()

        self.last_action_say_say = False
        return self.rng.choice(valid_actions)

    def game_over(self, state: ObservableState, won: bool) -> Action | None:
        return Action.say("I'm lucky") if won else None
