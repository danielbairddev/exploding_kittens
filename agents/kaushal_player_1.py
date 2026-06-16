from agents.kaushal_base_player import KaushalBasePlayer
from game.state import ObservableState
from game.actions import Action, ActionType
from game.cards import CardType


EK = CardType.EXPLODING_KITTEN
DEFUSE = CardType.DEFUSE
NOPE = CardType.NOPE
ATTACK = CardType.ATTACK
SKIP = CardType.SKIP
SEE_THE_FUTURE = CardType.SEE_THE_FUTURE

_GIVE_AWAY_PRIORITY = [
    CardType.TACO_CAT,
    CardType.HAIRY_POTATO_CAT,
    CardType.BEARD_CAT,
    CardType.RAINBOW_CAT,
    CardType.CATTERMELON,
    CardType.FAVOR,
    CardType.SHUFFLE,
    CardType.SEE_THE_FUTURE,
    CardType.NOPE,
    CardType.SKIP,
    CardType.ATTACK,
    CardType.DEFUSE,
]


class KaushalPlayer1(KaushalBasePlayer):
    ARENA = {"name": "k_player_1", "emoji": "\U0001F331", "color": "#14b8a6",
             "blurb": "Kaushal bot 1", "author": "Kaushal",
             "stats_version": 2,
             }

    def __init__(self, name: str = "k_player_1", seed: int | None = None):
        super().__init__(name=name, seed=seed)

    def game_start(self, state: ObservableState):
        super().game_start(state)

    def see_future(self, state: ObservableState, top3: list):
        super().see_future(state, top3)

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        self.observe_state(state)
        by_type = self.actions_by_type(valid_actions)
        hand = self.hand_counter(state)
        defuses = hand[DEFUSE]
        under_attack = state.turns_remaining > 1
        alive = len(state.alive_players)
        deck = max(1, state.deck_size)
        risk_details = self.top_bomb_risk_details(state)
        top_risk = risk_details["estimated"]
        baseline_risk = risk_details["baseline"]
        top = self.known_top_card(state)

        def first(action_type: ActionType) -> Action | None:
            return self.first_action(valid_actions, action_type)

        def escape_draw() -> Action | None:
            for action_type in (
                ActionType.PLAY_ATTACK,
                ActionType.PLAY_SKIP,
                ActionType.PLAY_SHUFFLE,
            ):
                action = first(action_type)
                if action:
                    return action
            return None

        def attack_or_skip() -> Action | None:
            return first(ActionType.PLAY_ATTACK) or first(ActionType.PLAY_SKIP)

        # If the top card is certainly or probably lethal, spend an escape card.
        # Prefer Attack/Skip over Shuffle so the next player gets the problem.
        if top == EK or top_risk >= 0.65:
            action = attack_or_skip() or first(ActionType.PLAY_SHUFFLE)
            if action:
                return action
            return Action(ActionType.DRAW)

        # When attacked, get information first. If the card is safe, draw it;
        # if it is bad, bounce the stack with Attack or spend Skip.
        if under_attack:
            if top is None and ActionType.PLAY_SEE_THE_FUTURE in by_type:
                return by_type[ActionType.PLAY_SEE_THE_FUTURE][0]
            if top is not None and top != EK:
                return Action(ActionType.DRAW)
            if top == EK or top_risk >= 0.50:
                action = attack_or_skip() or first(ActionType.PLAY_SHUFFLE)
                if action:
                    return action
            if defuses > 0:
                return Action(ActionType.DRAW)
            if defuses == 0 or top_risk > baseline_risk + 0.10:
                action = attack_or_skip() or first(ActionType.PLAY_SHUFFLE)
                if action:
                    return action
            return Action(ActionType.DRAW)

        # Peek when information changes the decision: no Defuse, endgame, small
        # deck, or public events suggest the top card is riskier than baseline.
        if top is None and ActionType.PLAY_SEE_THE_FUTURE in by_type:
            should_peek = (
                defuses == 0
                or alive <= 2
                or deck <= 8
                or top_risk >= baseline_risk + 0.15
            )
            if should_peek:
                return by_type[ActionType.PLAY_SEE_THE_FUTURE][0]

        # When no immediate draw danger is showing, build card economy and hunt
        # Defuses. Favor comes first because it does not shrink our hand; pairs
        # are mostly follow-up after the same player has handed over junk.
        safe_to_loot = top is None or top != EK
        if safe_to_loot:
            favor_actions = by_type.get(ActionType.PLAY_FAVOR, [])
            if favor_actions:
                return self.best_target_action(favor_actions, state, prefer_defuse=True)

            triple_actions = by_type.get(ActionType.PLAY_CAT_TRIPLE, [])
            if triple_actions and (defuses == 0 or alive <= 2):
                target = self.best_target_action(triple_actions, state, prefer_defuse=True)
                if defuses == 0 or self.player_defuse_estimate(target.target_player) >= 1.25:
                    return self.demand_defuse(target)

            pair_actions = by_type.get(ActionType.PLAY_CAT_PAIR, [])
            if pair_actions:
                favored_target = self._target_we_favored_this_turn(state)
                followup_pairs = [
                    action for action in pair_actions
                    if action.target_player == favored_target
                ]
                if followup_pairs:
                    return self.best_target_action(followup_pairs, state, prefer_defuse=True)
                if defuses == 0 or alive <= 2:
                    return self.best_target_action(pair_actions, state, prefer_defuse=True)

        # Known safe top: take the free card and save escape cards.
        if top is not None and top != EK:
            return Action(ActionType.DRAW)

        # Blind draw. A Defuse is insurance unless public history makes this
        # much scarier than the raw deck odds. Without a Defuse, dodge if the
        # risk is meaningful.
        if defuses > 0 and top_risk < 0.50:
            return Action(ActionType.DRAW)

        if defuses == 0 and top_risk >= 0.12:
            action = escape_draw()
            if action:
                return action

        return Action(ActionType.DRAW)

    def want_to_nope(self, state: ObservableState, action: Action, currently_noped: bool = False) -> bool:
        self.observe_state(state)
        if not self.has_card(state, NOPE):
            return False

        me = state.my_id
        actor = state.current_player
        action_type = action.action_type
        i_am_actor = me == actor

        # Restore our own cancelled survival moves and high-value Defuse hunts.
        if i_am_actor:
            if not currently_noped:
                return False
            if action_type in (ActionType.PLAY_ATTACK, ActionType.PLAY_SKIP, ActionType.PLAY_SHUFFLE):
                return True
            if action_type == ActionType.PLAY_CAT_TRIPLE and action.named_card == DEFUSE:
                return self.count_hand(state, NOPE) > 1 or len(state.alive_players) <= 3
            return False

        # Once someone else already cancelled the action, avoid spending a Nope
        # to restore an opponent's play.
        if currently_noped:
            return False

        top_risk = self.estimated_top_bomb_chance(state)
        top_is_bomb = self.do_we_know_a_bomb_is_on_top(state)
        actor_is_before_me = self.next_alive_id(state, actor) == me

        # Prefer answering attacks with our own Attack card. Nope only if the
        # attack lands on us and we lack that clean counter.
        if action_type == ActionType.PLAY_ATTACK and self.next_alive_id(state, actor) == me:
            if self.has_card(state, ATTACK):
                return False
            return self.count_hand(state, DEFUSE) == 0 or top_risk >= 0.45

        # Protect genuinely high-value hands, not every average steal.
        if action_type in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
            if action.target_player == me and self._should_nope_steal(state, action):
                return True

        # If the previous player saw/created a bomb and is trying to pass it to
        # us, spend the Nope. Otherwise do not waste it on generic defense.
        if (
            actor_is_before_me
            and action_type == ActionType.PLAY_SKIP
            and (top_is_bomb or top_risk >= 0.55)
        ):
            return True

        # Heads-up is different: deny the opponent's escape from a dangerous top
        # card and fight for every edge.
        if len(state.alive_players) == 2:
            if action_type in (ActionType.PLAY_ATTACK, ActionType.PLAY_SKIP):
                return top_is_bomb or top_risk >= 0.45
            if action_type == ActionType.PLAY_SHUFFLE:
                return top_is_bomb
            if action_type == ActionType.PLAY_SEE_THE_FUTURE:
                return self.count_hand(state, NOPE) > 1

        return False

    def give_card(self, state: ObservableState, requester_id: int) -> CardType:
        self.observe_state(state)
        hand = self.hand_counter(state)
        for card_type in _GIVE_AWAY_PRIORITY:
            if hand[card_type] <= 0:
                continue
            if card_type == DEFUSE and len(state.my_hand) > hand[DEFUSE]:
                continue
            return card_type
        return state.my_hand[0].card_type

    def place_exploding_kitten(self, state: ObservableState, deck_size: int) -> int:
        self.observe_state(state)
        if state.turns_remaining > 1:
            return deck_size
        return 0

    def _target_we_favored_this_turn(self, state: ObservableState) -> int | None:
        for event in reversed(state.recent_events):
            if event.get("type") == "turn_start":
                return None
            if event.get("type") == "favor" and event.get("player") == state.my_id:
                return event.get("from_player")
        return None

    def _should_nope_steal(self, state: ObservableState, action: Action) -> bool:
        hand_size = max(1, len(state.my_hand))
        defuses = self.count_hand(state, DEFUSE)

        if action.action_type == ActionType.PLAY_FAVOR:
            # Favor is usually fine because we choose the junk card. Only stop it
            # when there is effectively no junk to hand over.
            return hand_size == defuses

        if action.action_type == ActionType.PLAY_CAT_TRIPLE:
            if action.named_card == DEFUSE and defuses > 0:
                return True
            if action.named_card == NOPE and self.count_hand(state, NOPE) <= 1:
                return True
            return False

        if action.action_type == ActionType.PLAY_CAT_PAIR:
            defuse_loss_risk = defuses / hand_size
            premium_cards = (
                defuses
                + self.count_hand(state, NOPE)
                + self.count_hand(state, ATTACK)
                + self.count_hand(state, SKIP)
                + self.count_hand(state, SEE_THE_FUTURE)
            )
            return defuse_loss_risk >= 0.25 or (premium_cards >= 3 and hand_size <= 5)

        return False
