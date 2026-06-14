import random

from skull.agents.base import SkullAgent
from skull.discs import DiscType
from skull.state import ObservableState, Phase
from skull.actions import Action, ActionType



"""
Always place skull. Always place max bet

Test with:
 
python -m skull.run --agent "Ian's Bomber"
"""
class IanLosingAgent(SkullAgent):

    ARENA = {"name": "Ian's Bomber", "emoji": "💣", "color": "#8E27F5",
             "blurb": "I'm trying to die", "author": "Ian Brobin"}

    def __init__(self, name: str | None = None, seed: int | None = None):
        self.name = name or self.ARENA["name"]

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        match state.phase:
            case Phase.PLACING:
                return self._get_placing_action(state, valid_actions)
            case Phase.BIDDING:
                return self._get_bidding_action(state, valid_actions)
            case Phase.REVEAL:
                return self._get_reveal_action(state, valid_actions)
        return valid_actions[0]

    def _get_placing_action(self, state: ObservableState, valid_actions: list[Action]):
        if self._can_bid(valid_actions):
            return self._get_bidding_action(state, valid_actions)
        if DiscType.SKULL in state.my_hand:
            for action in valid_actions:
                if action.disc_type == DiscType.SKULL:
                    return action
        return valid_actions[0]

    def _can_bid(self,  valid_actions: list[Action]) -> bool:
        for action in valid_actions:
            if action.action_type == ActionType.BID:
                return True
        return False

    def _get_bidding_action(self, state:ObservableState, valid_actions: list[Action]):
        max_bid: int = -1
        max_bid_action: Action = None
        for action in valid_actions:
            if action.amount is not None and action.amount > max_bid:
                max_bid = action.amount
                max_bid_action = action
        if max_bid_action is not None:
            return max_bid_action
        return valid_actions[0]

    def _get_reveal_action(self,  state:ObservableState, valid_actions: list[Action]):
        for action in valid_actions:
            if action.target_player == state.my_id:
                return action
        return valid_actions[0]