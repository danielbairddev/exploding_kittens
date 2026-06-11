from abc import ABC, abstractmethod
from game.state import ObservableState
from game.actions import Action
from game.cards import CardType


class Agent(ABC):
    """
    Interface all agents must implement.
    Every method receives an ObservableState — only public information.
    """

    def game_start(self, state: ObservableState):
        """Called once at the start of a game with the agent's initial hand."""
        pass

    @abstractmethod
    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        """
        Called on your turn. Return one of the valid_actions.
        DRAW ends your play phase and draws a card.
        """

    def want_to_nope(self, state: ObservableState, action: Action, currently_noped: bool = False) -> bool:
        """
        Called during the Nope window after any card is played.
        currently_noped: True means the action is presently cancelled — returning True counter-Nopes it (restores it).
        Called repeatedly in rounds until nobody plays a Nope; each call costs one Nope card.
        """
        return False

    def give_card(self, state: ObservableState, requester_id: int) -> CardType:
        """Called when forced to give a card via Favor. Return a CardType from your hand."""
        return state.my_hand[0].card_type

    def place_exploding_kitten(self, state: ObservableState, deck_size: int) -> int:
        """Called after defusing. Return index to insert EK (0=top, deck_size=bottom)."""
        return deck_size  # default: bury at bottom

    def see_future(self, state: ObservableState, top3: list):
        """Called after playing See the Future. top3 is a list of Card."""
        pass
