"""GameTracker — reconstructs game history from an agent's own callbacks.

Foundation for Gorilla's belief state and Abaddon's opponent modeling. An agent
sees more than the per-turn snapshot: `want_to_nope` fires for EVERY card played
by EVERY player (with the actor = current_player), so the agent can log the full
action stream and build per-opponent behavior profiles + refined card counts.

Wire it from a CoyoteAgent subclass:
    game_start -> tracker.reset(state)
    want_to_nope -> tracker.observe_play(state); (then your nope logic)
    see_future  -> tracker.observe_future(top3, state.deck_size)
    choose_action / any -> tracker.observe_state(state)
"""
from collections import Counter, defaultdict

from game.actions import ActionType
from game.cards import CardType

_COUNT_TYPES = [
    CardType.DEFUSE, CardType.ATTACK, CardType.SKIP, CardType.FAVOR,
    CardType.SHUFFLE, CardType.SEE_THE_FUTURE, CardType.NOPE,
    CardType.TACO_CAT, CardType.HAIRY_POTATO_CAT, CardType.BEARD_CAT,
    CardType.RAINBOW_CAT, CardType.CATTERMELON,
]
_TOTALS = {
    CardType.DEFUSE: 6, CardType.ATTACK: 4, CardType.SKIP: 4, CardType.FAVOR: 4,
    CardType.SHUFFLE: 4, CardType.SEE_THE_FUTURE: 5, CardType.NOPE: 5,
    CardType.TACO_CAT: 4, CardType.HAIRY_POTATO_CAT: 4, CardType.BEARD_CAT: 4,
    CardType.RAINBOW_CAT: 4, CardType.CATTERMELON: 4,
}
EK = CardType.EXPLODING_KITTEN
DEF = CardType.DEFUSE
# Action types we profile per opponent.
_PROFILE = [ActionType.PLAY_ATTACK, ActionType.PLAY_SKIP, ActionType.PLAY_FAVOR,
            ActionType.PLAY_SHUFFLE, ActionType.PLAY_SEE_THE_FUTURE,
            ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE]


class GameTracker:
    def __init__(self):
        self.reset(None)

    def reset(self, state):
        self.plays = defaultdict(Counter)     # player_id -> Counter(ActionType)
        self.total_plays = Counter()          # player_id -> total observed plays
        self.nope_flips = 0                    # observed nope/counter-nope events
        self._last_action_id = None           # de-dupe a play across nope rounds
        self._top = None                       # known top cards (CardType list)
        self._top_deck = -1
        self.my_id = state.my_id if state is not None else 0

    # ---- observation hooks ----
    def observe_state(self, state):
        self.my_id = state.my_id

    def observe_play(self, state):
        """Call from want_to_nope. Attributes the action to current_player once."""
        # nope chains present the same Action object repeatedly; count it once.
        # (We can't see the Action here directly in this signature — callers pass
        # it via observe_action; kept split so state-only callers still work.)
        self.observe_state(state)

    def observe_action(self, state, action, currently_noped):
        self.observe_state(state)
        if currently_noped:
            # a flip happened since the action went active -> someone Noped
            pass
        if id(action) != self._last_action_id:
            self._last_action_id = id(action)
            actor = state.current_player
            self.plays[actor][action.action_type] += 1
            self.total_plays[actor] += 1

    def observe_future(self, top3, deck_size):
        self._top = [c.card_type if hasattr(c, "card_type") else c for c in top3]
        self._top_deck = deck_size

    # ---- derived knowledge ----
    def known_top(self, state):
        if self._top is not None and state.deck_size == self._top_deck and self._top:
            return self._top
        return None

    def unseen(self, state):
        """Counts of each tracked type not in my hand or the discard."""
        seen = Counter(c.card_type for c in state.my_hand)
        seen.update(c.card_type for c in state.discard_pile)
        return {t: max(0, _TOTALS[t] - seen.get(t, 0)) for t in _COUNT_TYPES}

    def ek_in_deck(self, state):
        return max(0, len(state.alive_players) - 1)

    def opp_profile(self, pid):
        """Action-type rates for an opponent (fraction of their observed plays)."""
        total = self.total_plays.get(pid, 0)
        if total == 0:
            return {a: 0.0 for a in _PROFILE}
        return {a: self.plays[pid].get(a, 0) / total for a in _PROFILE}
