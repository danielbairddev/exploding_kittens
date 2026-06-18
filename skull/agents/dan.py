import random

from skull.agents.base import SkullAgent
from skull.state import ObservableState, Phase
from skull.actions import Action, ActionType, DiscType


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

    def return_normal_action(self, action, valid_actions):
        self.last_action_say_say = False
        if action.action_type() == ActionType.SAY:
            raise Exception("Attempting to say a non-say action" + action)
        if action is None:
            return self.rng.choice(valid_actions)
        return action

    def has_bomb(self, discs: list[DiscType]):
        for disc in discs:
            if disc == disc.SKULL:
                return True
        return False


    def handle_placing(self, state, valid_actions):
        if self.has_bomb(state.my_hand) and len(state.alive_players) > 2:
            # Jokar mode
            return Action(action_type=ActionType.PLACE, disc_type=DiscType.SKULL)
        return None

    def handle_bidding(self, state, valid_actions):
        return None

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        if not self.last_action_say_say:
            return self.return_say_action()

        if state.phase == Phase.BIDDING:
            return self.return_normal_action(self.handle_bidding(state, valid_actions), valid_actions)
        elif state.phase == Phase.PLACING:
            return self.return_normal_action(self.handle_placing(state, valid_actions), valid_actions)

        return self.return_normal_action(self.rng.choice(valid_actions), valid_actions)

    def game_over(self, state: ObservableState, won: bool) -> Action | None:
        return Action.say("Yehaw") if won else None
