import random
from collections import Counter, defaultdict, deque
from dataclasses import replace

from agents.base import Agent
from game.actions import Action, ActionType
from game.cards import CAT_CARDS, CardType
from game.state import ObservableState


EK = CardType.EXPLODING_KITTEN
DEFUSE = CardType.DEFUSE

_ACTION_CARD_COSTS = {
    "PLAY_ATTACK": Counter({CardType.ATTACK: 1}),
    "PLAY_SKIP": Counter({CardType.SKIP: 1}),
    "PLAY_FAVOR": Counter({CardType.FAVOR: 1}),
    "PLAY_SHUFFLE": Counter({CardType.SHUFFLE: 1}),
    "PLAY_SEE_THE_FUTURE": Counter({CardType.SEE_THE_FUTURE: 1}),
}

class KaushalBasePlayer(Agent):
    """Shared memory and risk helpers for Kaushal bots.

    Subclasses should call ``self.observe_state(state)`` at the start of every
    decision method. This consumes only public events with event_id greater than
    the last one seen, so scanning stays cheap even late in a long game.
    """

    def __init__(self, name: str = "KaushalBase", seed: int | None = None):
        self.name = name
        self.rng = random.Random(seed)
        self._reset_memory()

    # ------------------------------------------------------------------ setup
    def game_start(self, state: ObservableState):
        self._reset_memory()
        self.my_id = state.my_id
        self.defuse_estimate = {pid: 1.0 for pid in state.alive_players}
        self.defuse_estimate[state.my_id] = self.count_hand(state, DEFUSE)
        self._last_hand = self.hand_counter(state)
        self.observe_state(state)

    def see_future(self, state: ObservableState, top3: list):
        self.observe_state(state)
        self._known_top = [c.card_type for c in top3]
        self._known_top_deck_size = state.deck_size

    def _reset_memory(self):
        self.my_id = None
        self._last_event_id = 0
        self._last_hand = Counter()
        self._known_top: list[CardType] | None = None
        self._known_top_deck_size = -1

        self.turn_starts = Counter()
        self.actions_played = Counter()
        self.nopes_played = Counter()
        self.cards_spent_by_player = defaultdict(Counter)
        self.known_cards_by_player = defaultdict(Counter)

        self.defuse_estimate = {}
        self.defuses_used = Counter()
        self.defuse_thieves = Counter()
        self.last_defuse_thief = None
        self.last_defuse_player = None
        self.last_exploded_player = None

        self._player_last_peek = {}
        self._avoidance_signals = deque(maxlen=12)
        self._turn_pressure = {}
        self._last_resolved_action = None

        self._last_shuffle_event_id = 0
        self._bomb_reinsert_event_id = 0
        self._bomb_reinsert_turn = None
        self._bomb_reinsert_player = None
        self._draws_since_bomb_reinsert = 999
        self._turns_since_bomb_reinsert = 999

    # ------------------------------------------------------------ event ingest
    def observe_state(self, state: ObservableState) -> list[dict]:
        """Absorb new public events and current hand deltas.

        Returns the new events, mostly for debugging or one-off strategy checks.
        Calling this more than once for the same ObservableState is safe.
        """
        if self.my_id is None:
            self.my_id = state.my_id
        if self.my_id != state.my_id:
            self._reset_memory()
            self.my_id = state.my_id

        events = sorted(
            (e for e in getattr(state, "recent_events", [])
             if e.get("event_id", 0) > self._last_event_id),
            key=lambda e: e.get("event_id", 0),
        )

        for event in events:
            self._consume_event(event, state)
            self._last_event_id = max(self._last_event_id, event.get("event_id", 0))

        self._process_hand_delta(state, events)
        self.defuse_estimate[state.my_id] = self.count_hand(state, DEFUSE)
        self._last_hand = self.hand_counter(state)
        self._invalidate_top_if_deck_mismatch(state)
        return events

    def _consume_event(self, event: dict, state: ObservableState):
        event_type = event.get("type")
        player = event.get("player")

        if event_type == "turn_start" and player is not None:
            self.turn_starts[player] += 1
            self._turn_pressure[player] = event.get("turns_remaining", 1)
            if self._bomb_reinsert_event_id:
                self._turns_since_bomb_reinsert += 1
            return

        if event_type == "nope":
            if player is not None:
                self.nopes_played[player] += 1
                self.actions_played[player] += 1
                self.cards_spent_by_player[player][CardType.NOPE] += 1
                self._forget_known_card(player, CardType.NOPE)
            return

        if event_type == "action_noped":
            # The original action did not resolve, so do not charge its card.
            return

        if event_type in ("attack", "skip", "shuffle", "see_future", "favor", "cat_steal"):
            self._record_resolved_action(event, state)
            return

        if event_type == "draw":
            self._record_draw(event, state)
            return

        if event_type == "defuse":
            self._record_defuse(event, state)
            return

        if event_type == "explode":
            self._record_explosion(event, state)
            return

        if event_type == "game_over":
            return

    def _record_resolved_action(self, event: dict, state: ObservableState):
        player = event.get("player")
        if player is None:
            return
        self.actions_played[player] += 1
        self._last_resolved_action = event

        for card_type, count in self._card_cost_for_event(event).items():
            self.cards_spent_by_player[player][card_type] += count
            for _ in range(count):
                self._forget_known_card(player, card_type)

        if event.get("type") == "see_future":
            self._player_last_peek[player] = {
                "event_id": event.get("event_id", 0),
                "turn": event.get("turn", 0),
                "deck_size": state.deck_size,
            }
            return

        if event.get("type") == "shuffle":
            self._last_shuffle_event_id = event.get("event_id", 0)
            self._player_last_peek.clear()
            self._clear_top_knowledge()
            self._clear_bomb_reinsert()
            return

        if event.get("type") in ("skip", "attack", "shuffle"):
            self._maybe_record_avoidance_signal(event, state)

        if event.get("type") == "cat_steal":
            self._record_public_steal(event)
        elif event.get("type") == "favor":
            self._record_public_favor(event)

    def _record_draw(self, event: dict, state: ObservableState):
        player = event.get("player")
        if player is None:
            return

        if self._bomb_reinsert_event_id:
            self._draws_since_bomb_reinsert += 1

        top = self.known_top_card(state, consume=False)
        if top is None:
            self._drop_known_top_card_if_exact(state, player, None)
            return
        if top == EK:
            # A normal draw cannot be an EK; something changed that we missed.
            self._clear_top_knowledge()
            return

        self._remember_known_card(player, top)
        if top == DEFUSE:
            self.defuse_estimate[player] = self.defuse_estimate.get(player, 1.0) + 1.0
        self._drop_known_top_card_if_exact(state, player, top)

    def _record_defuse(self, event: dict, state: ObservableState):
        player = event.get("player")
        if player is None:
            return

        self.last_defuse_player = player
        self.defuses_used[player] += 1
        self.defuse_estimate[player] = max(0.0, self.defuse_estimate.get(player, 1.0) - 1.0)
        self.cards_spent_by_player[player][DEFUSE] += 1
        self._forget_known_card(player, DEFUSE)

        self._bomb_reinsert_event_id = event.get("event_id", 0)
        self._bomb_reinsert_turn = event.get("turn", 0)
        self._bomb_reinsert_player = player
        self._draws_since_bomb_reinsert = 0
        self._turns_since_bomb_reinsert = 0
        self._player_last_peek.clear()
        self._clear_top_knowledge()

    def _record_explosion(self, event: dict, state: ObservableState):
        player = event.get("player")
        if player is None:
            return
        self.last_exploded_player = player
        self.defuse_estimate[player] = 0.0
        self.known_cards_by_player.pop(player, None)

        top = self.known_top_card(state, consume=False)
        if top == EK:
            self._drop_known_top_card_if_exact(state, player, EK)
        else:
            self._clear_top_knowledge()

    def _record_public_steal(self, event: dict):
        thief = event.get("player")
        victim = event.get("from_player")
        named = self._card_from_name(event.get("named_card"))
        if named == DEFUSE and thief is not None and victim is not None:
            # Triple demands are public. Success is not guaranteed, so keep this
            # as an estimate unless hand deltas later prove it was us.
            self.defuse_estimate[victim] = max(0.0, self.defuse_estimate.get(victim, 1.0) - 0.75)
            self.defuse_estimate[thief] = self.defuse_estimate.get(thief, 1.0) + 0.75

    def _record_public_favor(self, event: dict):
        # Favor transfers a private card chosen by the target. We only attribute
        # exact card movement when our own hand delta proves it.
        return

    def _process_hand_delta(self, state: ObservableState, events: list[dict]):
        current = self.hand_counter(state)
        if not self._last_hand:
            return

        old_defuses = self._last_hand.get(DEFUSE, 0)
        new_defuses = current.get(DEFUSE, 0)
        delta = new_defuses - old_defuses
        if delta == 0:
            return

        if delta < 0 and not self._we_spent_defuse(events):
            thief = self._latest_transfer_counterparty(events, lost=True)
            if thief is not None:
                self.defuse_thieves[thief] += abs(delta)
                self.last_defuse_thief = thief
                self.defuse_estimate[thief] = self.defuse_estimate.get(thief, 1.0) + abs(delta)

        if delta > 0:
            source = self._latest_transfer_counterparty(events, lost=False)
            if source is not None:
                self.defuse_estimate[source] = max(
                    0.0, self.defuse_estimate.get(source, 1.0) - delta
                )

    def _maybe_record_avoidance_signal(self, event: dict, state: ObservableState):
        player = event.get("player")
        if player is None:
            return
        last_peek = self._player_last_peek.get(player)
        if not last_peek:
            return
        if self._last_shuffle_event_id > last_peek.get("event_id", 0):
            return

        event_type = event.get("type")
        pressure = self._turn_pressure.get(player, 1)
        confidence = 0.0
        reason = None
        if event_type == "skip":
            confidence = 0.72 if pressure <= 1 else 0.52
            reason = "player skipped after seeing the future"
        elif event_type == "attack":
            confidence = 0.62 if pressure <= 1 else 0.48
            reason = "player attacked after seeing the future"
        elif event_type == "shuffle":
            confidence = 0.45
            reason = "player shuffled after seeing the future"

        if reason:
            self._avoidance_signals.append({
                "event_id": event.get("event_id", 0),
                "turn": event.get("turn", 0),
                "player": player,
                "action": event_type,
                "confidence": confidence,
                "deck_size": state.deck_size,
                "reason": reason,
            })

    # --------------------------------------------------------------- top cards
    def known_top_cards(self, state: ObservableState | None = None) -> list[CardType] | None:
        if state is not None:
            self._invalidate_top_if_deck_mismatch(state)
        if self._known_top is None:
            return None
        return list(self._known_top)

    def known_top_card(self, state: ObservableState | None = None, consume: bool = False) -> CardType | None:
        cards = self.known_top_cards(state)
        if not cards:
            return None
        return cards[0]

    def do_we_know_a_bomb_is_on_top(self, state: ObservableState) -> bool:
        return self.known_top_card(state) == EK

    def do_we_know_top_is_safe(self, state: ObservableState) -> bool:
        top = self.known_top_card(state)
        return top is not None and top != EK

    def _drop_known_top_card_if_exact(
        self,
        state: ObservableState,
        player: int,
        expected: CardType | None,
    ):
        if self._known_top is None:
            return
        if expected is not None and self._known_top and self._known_top[0] != expected:
            self._clear_top_knowledge()
            return
        if self._known_top:
            self._known_top.pop(0)
            self._known_top_deck_size = max(0, self._known_top_deck_size - 1)
        if not self._known_top:
            self._known_top = []

    def _invalidate_top_if_deck_mismatch(self, state: ObservableState):
        if self._known_top is None:
            return
        if self._known_top_deck_size >= 0 and state.deck_size != self._known_top_deck_size:
            # If public draw/explode events were processed correctly, the sizes
            # match. A mismatch means hidden reinsertion/shuffle state beat us.
            self._clear_top_knowledge()

    def _clear_top_knowledge(self):
        self._known_top = None
        self._known_top_deck_size = -1

    # --------------------------------------------------------------- risk API
    def chance_of_explode(self, state: ObservableState) -> float:
        return self.baseline_explosion_chance(state)

    def baseline_explosion_chance(self, state: ObservableState) -> float:
        deck_size = max(0, state.deck_size)
        if deck_size == 0:
            return 0.0
        bombs = getattr(state, "deck_exploding_kittens_count", None)
        if bombs is None:
            bombs = max(0, len(state.alive_players) - 1)
        return max(0.0, min(1.0, bombs / deck_size))

    def estimated_top_bomb_chance(self, state: ObservableState) -> float:
        return self.top_bomb_risk_details(state)["estimated"]

    def is_top_card_risk_elevated(self, state: ObservableState, margin: float = 0.15) -> bool:
        details = self.top_bomb_risk_details(state)
        return details["estimated"] >= details["baseline"] + margin

    def do_we_expect_a_bomb_on_top(self, state: ObservableState, threshold: float = 0.50) -> bool:
        return self.estimated_top_bomb_chance(state) >= threshold

    def top_bomb_risk_details(self, state: ObservableState) -> dict:
        self.observe_state(state)
        baseline = self.baseline_explosion_chance(state)
        top = self.known_top_card(state)
        if top == EK:
            return {"baseline": baseline, "estimated": 1.0, "reasons": ["known top card is EK"]}
        if top is not None:
            return {"baseline": baseline, "estimated": 0.0, "reasons": [f"known top card is {top.name}"]}

        risk = baseline
        reasons = []

        signal = self._fresh_avoidance_signal(state)
        if signal:
            risk = max(risk, signal["confidence"])
            reasons.append(signal["reason"])

        if self._bomb_reinsert_event_id and self._draws_since_bomb_reinsert == 0:
            confidence = 0.48
            if self._bomb_reinsert_player == self.previous_alive_id(state, state.my_id):
                confidence = 0.68
                reasons.append("previous player defused and may have planted the EK on top")
            else:
                reasons.append("an EK was defused and reinserted without a public shuffle")
            risk = max(risk, confidence)
        elif self._bomb_reinsert_event_id and self._draws_since_bomb_reinsert <= 2:
            risk = max(risk, min(0.85, baseline * 1.25))
            reasons.append("recent unshuffled EK reinsertion still raises deck danger")

        last_skip = self._last_resolved_action
        if last_skip and last_skip.get("type") == "skip" and last_skip.get("player") != state.my_id:
            pressure = self._turn_pressure.get(last_skip.get("player"), 1)
            if pressure <= 1:
                risk = max(risk, min(0.55, baseline + 0.20))
                reasons.append("last player skipped a normal draw")

        return {
            "baseline": baseline,
            "estimated": max(0.0, min(1.0, risk)),
            "reasons": reasons,
        }

    def _fresh_avoidance_signal(self, state: ObservableState) -> dict | None:
        if not self._avoidance_signals:
            return None
        latest = self._avoidance_signals[-1]
        if self._last_shuffle_event_id > latest["event_id"]:
            return None
        if self._bomb_reinsert_event_id > latest["event_id"]:
            return None
        if latest.get("deck_size") != state.deck_size:
            return None
        return latest

    def bomb_reinserted_without_shuffle(self) -> bool:
        return bool(self._bomb_reinsert_event_id and self._bomb_reinsert_event_id > self._last_shuffle_event_id)

    def recent_bomb_could_target_us(self, state: ObservableState) -> bool:
        if not self.bomb_reinserted_without_shuffle():
            return False
        if self._draws_since_bomb_reinsert > 0:
            return False
        planter = self._bomb_reinsert_player
        return planter == self.previous_alive_id(state, state.my_id) or state.current_player == state.my_id

    # ---------------------------------------------------------- player memory
    def player_defuse_estimate(self, player_id: int) -> float:
        return max(0.0, self.defuse_estimate.get(player_id, 1.0))

    def players_by_defuse_estimate(self, state: ObservableState, include_self: bool = False) -> list[int]:
        players = [p for p in state.alive_players if include_self or p != state.my_id]
        return sorted(players, key=lambda p: self.player_defuse_estimate(p), reverse=True)

    def player_known_card_count(self, player_id: int, card_type: CardType) -> int:
        return self.known_cards_by_player[player_id].get(card_type, 0)

    def player_likely_has(self, player_id: int, card_type: CardType) -> bool:
        if self.player_known_card_count(player_id, card_type) > 0:
            return True
        if card_type == DEFUSE:
            return self.player_defuse_estimate(player_id) >= 1.0
        return False

    def who_stole_our_defuse(self) -> int | None:
        return self.last_defuse_thief

    def who_recently_defused(self) -> int | None:
        return self.last_defuse_player

    def who_recently_exploded(self) -> int | None:
        return self.last_exploded_player

    # ------------------------------------------------------------ action utils
    @staticmethod
    def hand_counter(state: ObservableState) -> Counter:
        return Counter(c.card_type for c in state.my_hand)

    @staticmethod
    def count_hand(state: ObservableState, card_type: CardType) -> int:
        return sum(1 for c in state.my_hand if c.card_type == card_type)

    @staticmethod
    def has_card(state: ObservableState, card_type: CardType) -> bool:
        return any(c.card_type == card_type for c in state.my_hand)

    @staticmethod
    def actions_by_type(valid_actions: list[Action]) -> dict[ActionType, list[Action]]:
        by_type = {}
        for action in valid_actions:
            by_type.setdefault(action.action_type, []).append(action)
        return by_type

    @staticmethod
    def first_action(valid_actions: list[Action], action_type: ActionType) -> Action | None:
        for action in valid_actions:
            if action.action_type == action_type:
                return action
        return None

    def best_target_action(
        self,
        actions: list[Action],
        state: ObservableState,
        prefer_defuse: bool = False,
    ) -> Action:
        def score(action: Action) -> tuple[float, int]:
            target = action.target_player
            if target is None:
                return (-1.0, -1)
            value = float(state.hand_sizes.get(target, 0))
            if prefer_defuse:
                value += 3.0 * self.player_defuse_estimate(target)
            return (value, -target)

        return max(actions, key=score)

    def demand_defuse(self, action: Action) -> Action:
        return replace(action, named_card=DEFUSE)

    def next_alive_id(self, state: ObservableState, after: int | None = None) -> int:
        if after is None:
            after = state.my_id
        order = sorted(state.alive_players)
        if not order:
            return state.my_id
        if after in order:
            return order[(order.index(after) + 1) % len(order)]
        for offset in range(1, max(order) + 2):
            candidate = (after + offset) % (max(order) + 1)
            if candidate in order:
                return candidate
        return order[0]

    def previous_alive_id(self, state: ObservableState, before: int | None = None) -> int:
        if before is None:
            before = state.my_id
        order = sorted(state.alive_players)
        if not order:
            return state.my_id
        if before in order:
            return order[(order.index(before) - 1) % len(order)]
        for offset in range(1, max(order) + 2):
            candidate = (before - offset) % (max(order) + 1)
            if candidate in order:
                return candidate
        return order[-1]

    def turns_until_player(self, state: ObservableState, player_id: int) -> int:
        order = sorted(state.alive_players)
        if player_id not in order or state.current_player not in order:
            return 0
        current_index = order.index(state.current_player)
        player_index = order.index(player_id)
        distance = (player_index - current_index) % len(order)
        return distance + max(0, state.turns_remaining - 1)

    # ------------------------------------------------------------- internals
    def _card_cost_for_event(self, event: dict) -> Counter:
        action_type = event.get("action_type")
        if action_type in _ACTION_CARD_COSTS:
            return Counter(_ACTION_CARD_COSTS[action_type])

        cat_type = self._card_from_name(event.get("cat_type"))
        if action_type == "PLAY_CAT_PAIR" and cat_type in CAT_CARDS:
            return Counter({cat_type: 2})
        if action_type == "PLAY_CAT_TRIPLE" and cat_type in CAT_CARDS:
            return Counter({cat_type: 3})
        return Counter()

    def _latest_transfer_counterparty(self, events: list[dict], lost: bool) -> int | None:
        for event in reversed(events):
            event_type = event.get("type")
            if event_type not in ("favor", "cat_steal"):
                continue
            actor = event.get("player")
            victim = event.get("from_player")
            if victim is None:
                victim = event.get("target_player")
            if lost and victim == self.my_id:
                return actor
            if not lost and actor == self.my_id:
                return victim
        return None

    def _we_spent_defuse(self, events: list[dict]) -> bool:
        return any(event.get("type") == "defuse" and event.get("player") == self.my_id for event in events)

    def _remember_known_card(self, player: int, card_type: CardType):
        self.known_cards_by_player[player][card_type] += 1

    def _forget_known_card(self, player: int, card_type: CardType):
        if self.known_cards_by_player[player][card_type] > 0:
            self.known_cards_by_player[player][card_type] -= 1

    @staticmethod
    def _card_from_name(name: str | None) -> CardType | None:
        if not name:
            return None
        try:
            return CardType[name]
        except KeyError:
            return None

    def _clear_bomb_reinsert(self):
        self._bomb_reinsert_event_id = 0
        self._bomb_reinsert_turn = None
        self._bomb_reinsert_player = None
        self._draws_since_bomb_reinsert = 999
        self._turns_since_bomb_reinsert = 999
