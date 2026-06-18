import random

from skull.agents.base import SkullAgent
from skull.state import ObservableState, Phase
from skull.actions import Action, ActionType, DiscType


RANDOM_ACTION = -1

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
        #return Action.say("I'm the joker...")
        return Action.say("")

    def return_normal_action(self, action, valid_actions):
        self.last_action_say_say = False
        if action is RANDOM_ACTION:
            return self.rng.choice(valid_actions)
        if action.action_type == ActionType.SAY:
            raise Exception(f"Attempting to say a non-say action {action!r}")
        if action not in valid_actions:
            print("Invalid action ", valid_actions, action)
        return action

    def has_bomb(self, discs: list[DiscType]):
        for disc in discs:
            if disc == disc.SKULL:
                return True
        return False

    def has_rose(self, discs: list[DiscType]):
        for disc in discs:
            if disc == disc.ROSE:
                return True
        return False

    def handle_placing(self, state):
        # If we have a stack lets start bidding...
        if len(state.my_stack) > 0:
            return self.handle_bidding(state)

        if self.has_bomb(state.my_hand) and len(state.alive_players) > 2:
            # Jokar mode
            return Action(action_type=ActionType.PLACE, disc_type=DiscType.SKULL)

        # Either no bomb, or 2 players... try to win
        if not self.has_rose(state.my_hand):
            return Action(action_type=ActionType.PLACE, disc_type=DiscType.SKULL)
        return Action(action_type=ActionType.PLACE, disc_type=DiscType.ROSE)

    def handle_bidding(self, state):
        if state.my_stack[0] is DiscType.ROSE:
            print(state.current_bid)
            if state.current_bid >= 2:
                return Action(action_type=ActionType.PASS)
            return Action(action_type=ActionType.BID, amount=2)
        return Action(action_type=ActionType.PASS)

    def handle_reveal(self, state):
        # Return none will result in a random valid action (IE flip mine)
        return RANDOM_ACTION

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        if not self.last_action_say_say:
            return self.return_say_action()

        if state.phase == Phase.BIDDING:
            return self.return_normal_action(self.handle_bidding(state), valid_actions)
        elif state.phase == Phase.PLACING:
            return self.return_normal_action(self.handle_placing(state), valid_actions)
        elif state.phase == Phase.REVEAL:
            return self.return_normal_action(self.handle_reveal(state), valid_actions)

        return self.return_normal_action(self.rng.choice(valid_actions), valid_actions)

    def game_over(self, state: ObservableState, won: bool) -> Action | None:
        return Action.say("Yehaw") if won else None
