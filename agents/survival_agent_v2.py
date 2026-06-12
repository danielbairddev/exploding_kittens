from dataclasses import replace
from agents.survival_agent import SurvivalAgent
from game.state import ObservableState
from game.actions import Action, ActionType
from game.cards import CardType

EK = CardType.EXPLODING_KITTEN
DEF = CardType.DEFUSE
NOPE = CardType.NOPE


class SurvivalAgentV2(SurvivalAgent):
    """
    Sly2 — a steal-heavy evolution of Sly (SurvivalAgent).

    Same survival spine (never draw a known kitten, draw safe tops for free,
    treat a Defuse as insurance, weaponise EK placement), but tuned via
    head-to-head A/B benchmarking against Sly. What changed and why:

    * STEAL RELENTLESSLY. Card advantage + denial snowballs in this game, and
      it turned out to be the dominant lever:
        - Cat pairs: always play them (Sly only did ~55% of the time) — never
          declining a steal was worth several win-rate points; *not* stealing
          cost ~5%.
        - Favor: play it proactively every turn it's available. Even though the
          target picks what to give, the free card + denial was the single
          biggest improvement (~+7% head-to-head).
      Both are gated behind "no known kitten on top" — survive first, then loot.
    * CONSERVE SEE-THE-FUTURE. Only peek when it actually matters — when we hold
      no Defuse, in a 2-player endgame, or when the deck is short. With a Defuse
      as insurance, a blind draw is fine, so we'd rather spend the turn stealing.
    * PROTECT THE LAST DEFUSE. Nope a steal aimed at our final Defuse almost
      always.

    Ablation/benchmark summary (5-player, seat-rotated, vs Sly in shared games):
    Sly2 ~34-36% vs Sly ~26-28% across every opponent mix and the 6-bot arena
    pool. Aggressive ideas (attack-to-kill, endgame attacking) were tested and
    *hurt*, so they were dropped — the edge is economy, not offense.

    Inherits see_future/game_start/give_card/place_exploding_kitten and the
    helper methods from SurvivalAgent unchanged.
    """

    ARENA = {"name": "Sly2", "emoji": "\U0001F99D", "color": "#a78bfa",
             "blurb": "Sly, but steals everything.", "author": "Daniel Baird",
             "llm_assisted": True, "stats_version": 1}

    def _known_list(self, state: ObservableState):
        """Validated known top cards (list of CardType) or None if stale."""
        if self._top is not None and state.deck_size == self._seen_deck and self._top:
            return self._top
        return None

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

        # --- Phase 1: loot (only when no kitten is sitting on top) ----------
        if not top_ek:
            # Peek only when it matters — otherwise the Defuse is our insurance
            # and we'd rather spend the turn stealing.
            if top is None and has(ActionType.PLAY_SEE_THE_FUTURE) \
                    and (n_defuse == 0 or alive <= 2 or deck <= 8):
                return first(ActionType.PLAY_SEE_THE_FUTURE)
            # Cat triple: demand a Defuse from the biggest hand.
            if has(ActionType.PLAY_CAT_TRIPLE):
                act = self._best_target(by_type[ActionType.PLAY_CAT_TRIPLE], state)
                return replace(act, named_card=DEF)
            # Cat pair: always steal a random card from the biggest hand.
            if has(ActionType.PLAY_CAT_PAIR):
                return self._best_target(by_type[ActionType.PLAY_CAT_PAIR], state)
            # Favor: take a card from the biggest hand — pure card advantage.
            if has(ActionType.PLAY_FAVOR):
                return self._best_target(by_type[ActionType.PLAY_FAVOR], state)

        # --- Phase 2: terminal decision (same survival spine as Sly) --------
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

        # Defuse-less and blind: dodge the draw if we can.
        p_ek = (alive - 1) / deck
        if has(ActionType.PLAY_ATTACK):
            return first(ActionType.PLAY_ATTACK)
        if has(ActionType.PLAY_SKIP) and p_ek >= 0.10:
            return first(ActionType.PLAY_SKIP)
        return Action(ActionType.DRAW)

    def want_to_nope(self, state: ObservableState, action: Action, currently_noped: bool = False) -> bool:
        # Guard the last Defuse: nope a steal aimed at it almost always.
        if not currently_noped and state.my_id != state.current_player:
            at = action.action_type
            if at in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE) \
                    and action.target_player == state.my_id \
                    and sum(1 for c in state.my_hand if c.card_type == DEF) <= 1 \
                    and any(c.card_type == NOPE for c in state.my_hand) \
                    and any(c.card_type == DEF for c in state.my_hand):
                if self.rng.random() < 0.95:
                    return True
        return super().want_to_nope(state, action, currently_noped)
