from math import comb
from collections import Counter
from dataclasses import replace
from agents.survival_agent_v2 import SurvivalAgentV2
from game.state import ObservableState
from game.actions import Action, ActionType
from game.cards import CardType

EK = CardType.EXPLODING_KITTEN
DEF = CardType.DEFUSE
NOPE = CardType.NOPE

# Fixed card totals in a game (independent of player count, for <= 6 players):
# the action/cat deck is constant and there are always 6 Defuses in the box.
# (Exploding Kittens aren't needed here — we only count what opponents might hold.)
_TOTAL = {
    CardType.ATTACK: 4, CardType.SKIP: 4, CardType.FAVOR: 4, CardType.SHUFFLE: 4,
    CardType.SEE_THE_FUTURE: 5, CardType.NOPE: 5,
    CardType.TACO_CAT: 4, CardType.HAIRY_POTATO_CAT: 4, CardType.BEARD_CAT: 4,
    CardType.RAINBOW_CAT: 4, CardType.CATTERMELON: 4, DEF: 6,
}

# Give-away priority: cards that are dead weight to everyone first, then cats
# (so we don't hand a steal-bot its next pair), keeping survival cards; never Defuse.
_GIVE_NONCAT_FIRST = [
    CardType.SHUFFLE, CardType.FAVOR, CardType.SEE_THE_FUTURE,
    CardType.TACO_CAT, CardType.HAIRY_POTATO_CAT, CardType.BEARD_CAT,
    CardType.RAINBOW_CAT, CardType.CATTERMELON,
    CardType.NOPE, CardType.SKIP, CardType.ATTACK,
]


class CoyoteAgent(SurvivalAgentV2):
    """
    Coyote — a card-counting evolution of Sly2 that hunts the leader.

    Same steal-heavy survival core as Sly2, but it *counts cards* off the
    observable discard pile to reason about what opponents probably hold, and
    adds a few benchmarked refinements. Every idea here was A/B-tested
    head-to-head vs Sly2; the ones that lost (stealing from small hands,
    snipe-attacking, denying the leader's steals) were dropped.

    Card counting: for any card type, ``unseen = total - my_hand - discard``,
    spread across the draw pile + opponents' hands. Treating a player's hand as
    a random subset of that pool gives a hypergeometric estimate of what they
    hold. Used for:

    * HOLD THE ATTACK. When we'd otherwise dump our draw via Attack, first check
      whether the next player likely holds an Attack — if so they'd just bounce
      it back (stacked), so we hold it and Skip/draw instead. (Your idea — it
      benchmarked as a small, real win.)
    * NOPE WARS WE CAN WIN. Only counter-Nope our own play when the opponents
      almost certainly have no Nope left to re-cancel it, so the counter sticks.

    Plus two economy tweaks that beat Sly2:
    * DON'T FEED THE CATS. When forced to give a card, hand over dead weight
      (shuffle/favor/see) before cats, so we don't complete an opponent's pair.
    * PROTECT DEFUSES. Nope a steal aimed at us while we're down to <= 2 Defuses.

    Net: ~+1 point on Sly2 head-to-head and clear #1 in the full arena pool.
    """

    ARENA = {"name": "Coyote", "emoji": "\U0001F43A", "color": "#d6a35c",
             "blurb": "Counts cards, hunts the leader.", "author": "Daniel Baird",
             "llm_assisted": True, "stats_version": 18}

    # ---- card counting -------------------------------------------------
    def _unseen(self, state: ObservableState):
        """(unseen counts by type, total unseen pool, opponents' total cards)."""
        seen = Counter(c.card_type for c in state.my_hand)
        seen.update(c.card_type for c in state.discard_pile)
        unseen = {ct: max(0, tot - seen.get(ct, 0)) for ct, tot in _TOTAL.items()}
        opp_total = sum(h for pid, h in state.hand_sizes.items() if pid != state.my_id)
        pool = state.deck_size + opp_total
        return unseen, pool, opp_total

    @staticmethod
    def _p_holds(k: int, n: int, pool: int) -> float:
        """P(a random n-card hand drawn from `pool` contains >=1 of k marked cards)."""
        if k <= 0 or n <= 0 or pool <= 0:
            return 0.0
        if k >= pool or n >= pool or pool - k < n:
            return 1.0
        return 1.0 - comb(pool - k, n) / comb(pool, n)

    def _p_next_holds(self, state: ObservableState, card_type: CardType) -> float:
        unseen, pool, _ = self._unseen(state)
        nxt = self._next_alive_id(state, state.my_id)
        return self._p_holds(unseen.get(card_type, 0), state.hand_sizes.get(nxt, 0), pool)

    # ---- turn logic ----------------------------------------------------
    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        by_type: dict = {}
        for a in valid_actions:
            by_type.setdefault(a.action_type, []).append(a)

        def has(t):
            return t in by_type

        def first(t):
            return by_type[t][0]

        hand = [c.card_type for c in state.my_hand]
        n_defuse = hand.count(DEF)
        alive = len(state.alive_players)
        deck = max(1, state.deck_size)
        under_attack = state.turns_remaining > 1
        topl = self._known_list(state)
        top = topl[0] if topl else None
        top_ek = top == EK
        top_safe = top is not None and top != EK

        # Phase 1: loot (identical to Sly2) — only when no kitten on top.
        if not top_ek:
            if top is None and has(ActionType.PLAY_SEE_THE_FUTURE) \
                    and (n_defuse == 0 or alive <= 2 or deck <= 8):
                return first(ActionType.PLAY_SEE_THE_FUTURE)
            if has(ActionType.PLAY_CAT_TRIPLE):
                act = self._best_target(by_type[ActionType.PLAY_CAT_TRIPLE], state)
                return replace(act, named_card=DEF)
            if has(ActionType.PLAY_CAT_PAIR):
                return self._best_target(by_type[ActionType.PLAY_CAT_PAIR], state)
            if has(ActionType.PLAY_FAVOR):
                return self._best_target(by_type[ActionType.PLAY_FAVOR], state)

        # Phase 2: terminal decision.
        if top_ek:
            if has(ActionType.PLAY_ATTACK):
                return first(ActionType.PLAY_ATTACK)
            if has(ActionType.PLAY_SKIP):
                return first(ActionType.PLAY_SKIP)
            if has(ActionType.PLAY_SHUFFLE):
                return first(ActionType.PLAY_SHUFFLE)
            return Action(ActionType.DRAW)

        if under_attack:
            if has(ActionType.PLAY_ATTACK):
                return first(ActionType.PLAY_ATTACK)
            if top_safe:
                return Action(ActionType.DRAW)
            if has(ActionType.PLAY_SKIP):
                return first(ActionType.PLAY_SKIP)
            if n_defuse > 0:
                return Action(ActionType.DRAW)
            if has(ActionType.PLAY_SHUFFLE):
                return first(ActionType.PLAY_SHUFFLE)
            return Action(ActionType.DRAW)

        if top_safe:
            return Action(ActionType.DRAW)

        if n_defuse > 0:
            return Action(ActionType.DRAW)

        # Defuse-less and blind: dodge the draw. Hold the Attack if the next
        # player likely holds one too (they'd just bounce it back, stacked).
        p_ek = (alive - 1) / deck
        if has(ActionType.PLAY_ATTACK) and self._p_next_holds(state, CardType.ATTACK) < 0.45:
            return first(ActionType.PLAY_ATTACK)
        if has(ActionType.PLAY_SKIP) and p_ek >= 0.10:
            return first(ActionType.PLAY_SKIP)
        if has(ActionType.PLAY_ATTACK):       # last resort over a blind draw
            return first(ActionType.PLAY_ATTACK)
        return Action(ActionType.DRAW)

    # ---- nope policy ---------------------------------------------------
    def want_to_nope(self, state: ObservableState, action: Action, currently_noped: bool = False) -> bool:
        at = action.action_type

        # Counter-Nope our own play only if opponents almost certainly can't
        # re-cancel it — i.e. there's no Nope left in their hands.
        if state.my_id == state.current_player and currently_noped \
                and any(c.card_type == NOPE for c in state.my_hand) \
                and at in (ActionType.PLAY_ATTACK, ActionType.PLAY_SKIP, ActionType.PLAY_FAVOR,
                           ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
            unseen, pool, opp_total = self._unseen(state)
            if self._p_holds(unseen.get(NOPE, 0), opp_total, pool) < 0.30:
                return True

        # Protect our Defuses (up to two) from theft aimed at us.
        if not currently_noped and state.my_id != state.current_player:
            if at in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE) \
                    and action.target_player == state.my_id \
                    and sum(1 for c in state.my_hand if c.card_type == DEF) <= 2 \
                    and any(c.card_type == NOPE for c in state.my_hand) \
                    and any(c.card_type == DEF for c in state.my_hand):
                if self.rng.random() < 0.95:
                    return True

        return super().want_to_nope(state, action, currently_noped)

    # ---- don't feed the cats -------------------------------------------
    def give_card(self, state: ObservableState, requester_id: int) -> CardType:
        held = {c.card_type for c in state.my_hand}
        for ct in _GIVE_NONCAT_FIRST:
            if ct in held:
                return ct
        safe = [c for c in state.my_hand if c.card_type != DEF]
        pool = safe if safe else state.my_hand
        return self.rng.choice(pool).card_type
