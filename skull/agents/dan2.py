import random

from skull.agents.base import SkullAgent
from skull.state import ObservableState, Phase
from skull.events import *
from skull.actions import Action, ActionType, DiscType


RANDOM_ACTION = -1

# K -> Crunch state
# V -> action probability tuples
CRUNCH_MAP = {}
# 1234 -> sorted(Action, 0.2%, Action 0.5%, Action None

class DanBot(SkullAgent):

    ARENA = {"name": "CrunchWrap", "emoji": "😊", "color": "#ff7811",
             "blurb": "Yum yum!", "author": "Dan"}

    def crunch(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        global CRUNCH_MAP
        crunch_hash = hash((  # Notice the double parenthesis here
            tuple(state.my_hand),
            tuple(state.my_stack),
            tuple(sorted(state.stack_sizes.items())),
            state.current_bid,  # Int (already hashable)
            state.round_starting_player,  # Int (already hashable)
            tuple(sorted(state.points.items())),
            tuple(sorted(state.disc_counts.items())),
        ))  # Notice the closing double parenthesis
        print(crunch_hash)

        existing_mapping = CRUNCH_MAP.get(crunch_hash)
        if not existing_mapping:
            INIT_WIN = 0
            INIT_LOSS = 0
            existing_mapping = {action: (INIT_WIN, INIT_LOSS) for action in valid_actions}
            CRUNCH_MAP[crunch_hash] = existing_mapping

        for action, (wins, losses) in existing_mapping.items():
            MIN_EXPLORE_TRIES = 1
            if wins + losses < MIN_EXPLORE_TRIES:
                # Under-sampled action give it another look before trusting its rate
                self._explore.append((crunch_hash, action))
                return action

        actions = []
        weights = []

        for action, (wins, losses) in existing_mapping.items():
            total_games = wins + losses
            win_rate = wins / total_games if total_games > 0 else 0.0
            actions.append(action)
            weights.append(win_rate)
        if sum(weights) == 0:
            return random.choice(actions)
        selected_action = random.choices(actions, weights=weights, k=1)[0]
        self._explore.append((crunch_hash, selected_action))
        return selected_action


    def __init__(self, name: str | None = None, seed: int | None = None):
        self.name = name or self.ARENA["name"]
        self.rng = random.Random(seed)
        self.last_action_say_say = False
        self._explore = []   # (crunch_hash, action) this game; stashed into CRUNCH_MAP at game over

    def game_start(self, state: ObservableState):
        self._explore = []

    def return_say_action(self):
        self.last_action_say_say = True
        #return Action.say("I'm the joker...")
        return Action.say("")

    def analyze_full_game(self, gamelog: list[Event]):
        for event in gamelog:
            if isinstance(event, PlaceEvent):
                print(event)

    def return_normal_action(self, action, valid_actions):
        self.last_action_say_say = False
        if action is RANDOM_ACTION:
            random_action = self.rng.choice(valid_actions)
            print("Intended Random. ", random_action)
            return random_action
        if action.action_type == ActionType.SAY:
            raise Exception(f"Attempting to say a non-say action {action!r}")
        if action not in valid_actions:
            print("Invalid action ", valid_actions, action)
        print(action)
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
            if state.current_bid >= 2:
                return Action(action_type=ActionType.PASS)

            return Action(action_type=ActionType.BID, amount=2)

        if state.current_bid == 0:
            # We are turn player, and therefore need to bid something...
            return Action(action_type=ActionType.BID, amount=1)

        return Action(action_type=ActionType.PASS)

    def handle_reveal(self, state):
        # Return none will result in a random valid action (IE flip mine)
        return RANDOM_ACTION

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:

        # Start crunching when 3handed
        if len(state.alive_players) <= 3:
            return self.crunch(state, valid_actions)

        #self.analyze_full_game(state.recent_events)
        #print(state.disc_counts)

        #if not self.last_action_say_say:
            #return self.return_say_action()

        if state.phase == Phase.BIDDING:
            return self.return_normal_action(self.handle_bidding(state), valid_actions)
        elif state.phase == Phase.PLACING:
            return self.return_normal_action(self.handle_placing(state), valid_actions)
        elif state.phase == Phase.REVEAL:
            return self.return_normal_action(self.handle_reveal(state), valid_actions)

        print("Missing handling for ", state.phase)
        return self.return_normal_action(self.rng.choice(valid_actions), valid_actions)

    # So we need to improve the explore ingestion, fwiw when we explore we may explode the results that came before.
    # This punishes exploring A LOT
    # Therefore when we explore in later stages of the game, we should try a variant that invalidates the results prior
    def ingest_game_state(self, won: bool):
        global CRUNCH_MAP

        for crunch, action in self._explore:
            crunch_win, crunch_loss = CRUNCH_MAP[crunch][action]
            if won:
                crunch_win += 1
            else:
                crunch_loss += 1
            CRUNCH_MAP[crunch][action] = (crunch_win, crunch_loss)
        self._explore = []

    def game_over(self, state: ObservableState, won: bool) -> Action | None:
        self.ingest_game_state(won)
        return Action.say("I'm still hungry!") if won else None
