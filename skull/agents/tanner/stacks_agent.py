import random

from skull.agents.base import SkullAgent
from skull.state import ObservableState, Phase
from skull.actions import Action, ActionType, DiscType
from skull.agents.tanner.SafeStacker import SafeStackerBot


class StacksBot(SkullAgent):
    """always places ROSE and stacks everything else is random."""

    ARENA = {"name": "Stacks", "emoji": "🥞", "color": "#c3925b",
             "blurb": "always be stackin", "author": "Tanner", "version": '1.4'}

    def __init__(self, name: str | None = None, seed: int | None = None):
        self.name = name or self.ARENA["name"]
        self.rng = random.Random(seed)

    def return_normal_action(self, action, valid_actions):
        if action is None:
            return self.rng.choice(valid_actions)
        if action.action_type == ActionType.SAY:
            raise Exception(f"Attempting to say a non-say action {action!r}")
        return action

    def has_bomb(self, discs: list[DiscType]):
        return DiscType.SKULL in discs

    def has_rose(self, discs: list[DiscType]):
        return DiscType.ROSE in discs

    def handle_placing(self, state: ObservableState):
        def place(disc_type: DiscType):
            return Action(action_type=ActionType.PLACE, disc_type=disc_type)

        if DiscType.ROSE in state.my_hand:
            return place(DiscType.ROSE)
        elif DiscType.SKULL in state.my_hand:
            # add SKULL on top if max ROSE is ever reached
            return place(DiscType.SKULL)
        return self.handle_bidding(state)

    def handle_bidding(self, state: ObservableState):
        def bid(amount: int):
            return Action(action_type=ActionType.BID, amount=amount)
        
        if state.my_stack[-1] == DiscType.SKULL:
            return Action(action_type=ActionType.PASS)

        if len(state.my_stack) > 1:
            SafetyStackerID = None
            for id in state.stack_sizes:
                if state.bot_names[id] == SafeStackerBot.ARENA['name']:
                    SafetyStackerID = id
            safety_stacker_bonus = state.stack_sizes[SafetyStackerID] if SafetyStackerID != None else 0

            base_bid = len(state.my_stack) + safety_stacker_bonus
            aggressiveness = self.rng.choice(range(state.total_on_table - base_bid))
            shouldBid = base_bid + aggressiveness < state.total_on_table
            return bid(base_bid + aggressiveness) if shouldBid else Action(action_type=ActionType.PASS)
        return None

    def handle_reveal(self, _: ObservableState):
        # Return none will result in a random valid action (IE flip mine)
        return None

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        if state.phase == Phase.BIDDING:
            return self.return_normal_action(self.handle_bidding(state), valid_actions)
        elif state.phase == Phase.PLACING:
            return self.return_normal_action(self.handle_placing(state), valid_actions)
        elif state.phase == Phase.REVEAL:
            return self.return_normal_action(self.handle_reveal(state), valid_actions)

        return self.return_normal_action(self.rng.choice(valid_actions), valid_actions)

    def game_over(self, state: ObservableState, won: bool) -> Action | None:
        return Action.say("It's Stacking Time!") if won else Action.say("NOT ENOUGH STACKING!!!")
