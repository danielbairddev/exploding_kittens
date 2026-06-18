import random

from skull.agents.base import SkullAgent
from skull.state import ObservableState, Phase
from skull.actions import Action, ActionType, DiscType


class SafeStackerBot(SkullAgent):
    """always places ROSE, stacks, and only bets it's stacks size."""

    ARENA = {"name": "Safety Stacker", "emoji": "🩹🥞", "color": "#c3925b",
             "blurb": "always be stackin (but within my means)", "author": "Tanner"}

    def __init__(self, name: str | None = None, seed: int | None = None):
        self.name = name or self.ARENA["name"]
        self.rng = random.Random(seed)
        self.last_action_say_say = False

    def return_say_action(self):
        self.last_action_say_say = True
        return Action.say("STACK!")

    def return_normal_action(self, action, valid_actions):
        self.last_action_say_say = False
        if action is None:
            return self.rng.choice(valid_actions)
        if action.action_type == ActionType.SAY:
            raise Exception(f"Attempting to say a non-say action {action!r}")
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

    def handle_placing(self, state: ObservableState):
        def place(disc_type: DiscType):
            return Action(action_type=ActionType.PLACE, disc_type=disc_type)

        if DiscType.ROSE in state.my_hand:
            return place(DiscType.ROSE)
        return self.handle_bidding(state)

    def handle_bidding(self, state: ObservableState):
        def bid(amount: int):
            return Action(action_type=ActionType.BID, amount=amount)

        if len(state.my_stack) > 1:
            shouldBid = len(state.my_stack) < state.total_on_table
            return bid(len(state.my_stack)) if shouldBid else Action(action_type=ActionType.PASS)
        return None

    def handle_reveal(self, _: ObservableState):
        # Return none will result in a random valid action (IE flip mine)
        return None

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        # if not self.last_action_say_say:
        #     return self.return_say_action()

        if state.phase == Phase.BIDDING:
            return self.return_normal_action(self.handle_bidding(state), valid_actions)
        elif state.phase == Phase.PLACING:
            return self.return_normal_action(self.handle_placing(state), valid_actions)
        elif state.phase == Phase.REVEAL:
            return self.return_normal_action(self.handle_reveal(state), valid_actions)

        return self.return_normal_action(self.rng.choice(valid_actions), valid_actions)

    def game_over(self, state: ObservableState, won: bool) -> Action | None:
        return Action.say("It's Stacking Time!") if won else Action.say("NOT ENOUGH STACKING!!!")
