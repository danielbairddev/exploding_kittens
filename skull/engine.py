import random

from .discs import Disc, DiscType, build_starting_hand
from .state import GameState, PlayerState, ObservableState, Phase
from .actions import Action, ActionType

POINTS_TO_WIN = 2          # two successful challenges wins the game
MAX_ROUNDS = 300           # safety valve against a pathological game never ending
MAX_CHAT_PER_TURN = 1      # chat messages a bot may post per decision point
MAX_CHAT_LEN = 200         # chat messages are truncated to this many characters


class SkullEngine:
    """Plays full games of Skull. Same constructor / play_game contract as the
    Exploding Kittens ``GameEngine`` so the arena machinery can drive it.

    A game is a sequence of rounds. Each round:
      1. PLACING  — every player lays at least one disc, then may keep placing.
      2. BIDDING  — once opened, players raise or pass; last one standing is
                    the challenger and owes that many safe flips.
      3. REVEAL   — the challenger flips their own discs first, then opponents'
                    top discs. All roses up to the bid = a point. A skull = the
                    challenger loses a disc (and is eliminated at zero discs).
    First to two points, or last player with discs, wins.
    """

    def __init__(self, agents: list, seed: int | None = None, verbose: bool = False,
                 collect_events: bool = False):
        self.agents = agents
        self.verbose = verbose
        self.collect_events = collect_events
        self.rng = random.Random(seed)
        self._events: list[dict] = []
        self._public_events: list[dict] = []
        self._next_public_event_id = 1
        self._round = 0
        self._elim_order: list[int] = []

    # ------------------------------------------------------------------ logging
    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    def _event(self, type: str, **kwargs):
        if self.collect_events:
            self._events.append({"turn": self._round, "type": type, **kwargs})

    def _public_event(self, type: str, **kwargs):
        self._public_events.append({
            "event_id": self._next_public_event_id,
            "turn": self._round,
            "type": type,
            **kwargs,
        })
        self._next_public_event_id += 1

    # -------------------------------------------------------------- observation
    def _observable(self, state: GameState, for_player: int) -> ObservableState:
        me = state.players[for_player]
        return ObservableState(
            my_id=for_player,
            phase=state.phase,
            my_hand=[d.disc_type for d in me.hand],
            my_stack=[d.disc_type for d in me.stack],
            stack_sizes={p.player_id: len(p.stack) for p in state.alive_players},
            disc_counts={p.player_id: p.disc_count for p in state.alive_players},
            points={p.player_id: p.points for p in state.alive_players},
            alive_players=[p.player_id for p in state.alive_players],
            current_bid=state.current_bid,
            highest_bidder=state.highest_bidder,
            total_on_table=state.discs_on_table,
            current_player=state.current_player,
            recent_events=list(self._public_events),
        )

    # -------------------------------------------------------------------- setup
    def _setup(self, n_players: int) -> GameState:
        players = [PlayerState(player_id=i, hand=build_starting_hand())
                   for i in range(n_players)]
        first = self.rng.randrange(n_players)   # Skull picks a random opening player
        return GameState(players=players, current_player=first, starting_player=first)

    def _next_alive(self, state: GameState, current: int) -> int:
        n = len(state.players)
        nxt = (current + 1) % n
        while not state.players[nxt].alive:
            nxt = (nxt + 1) % n
        return nxt

    def _next_active_bidder(self, state: GameState, current: int) -> int:
        """Next alive player who hasn't passed this bidding round."""
        n = len(state.players)
        nxt = (current + 1) % n
        for _ in range(n):
            p = state.players[nxt]
            if p.alive and not p.passed:
                return nxt
            nxt = (nxt + 1) % n
        return current

    # ----------------------------------------------------------- agent dispatch
    def _choose(self, state: GameState, pid: int, valid: list[Action]) -> Action:
        keys = {a.key() for a in valid}
        chats = 0
        while True:
            # Recompute the view each pass so a bot sees its own chat appear in
            # recent_events before it picks its real move.
            obs = self._observable(state, pid)
            action = self.agents[pid].choose_action(obs, valid)
            if action is not None and action.action_type == ActionType.SAY:
                if chats < MAX_CHAT_PER_TURN and action.message:
                    self._say(pid, action.message)
                    chats += 1
                    continue
                return valid[0]   # out of chat budget (or empty) -> just play
            if action is None or action.key() not in keys:
                return valid[0]   # default to the first legal action
            return action

    def _endgame_chat(self, state: GameState, winner: int) -> None:
        """Let every agent post one parting message once the game is decided."""
        for pid in range(len(state.players)):
            action = self.agents[pid].game_over(
                self._observable(state, pid), won=(pid == winner))
            if (action is not None
                    and action.action_type == ActionType.SAY
                    and action.message):
                self._say(pid, action.message)

    def _say(self, pid: int, message: str) -> None:
        text = str(message)[:MAX_CHAT_LEN]
        self._log(f"  P{pid} says: {text}")
        self._event("chat", player=pid, message=text)
        self._public_event("chat", player=pid, message=text)

    # ------------------------------------------------------------- valid moves
    def _placing_actions(self, player: PlayerState, can_bid: bool,
                         total: int) -> list[Action]:
        actions = []
        if any(d.disc_type == DiscType.ROSE for d in player.hand):
            actions.append(Action(ActionType.PLACE, disc_type=DiscType.ROSE))
        if any(d.disc_type == DiscType.SKULL for d in player.hand):
            actions.append(Action(ActionType.PLACE, disc_type=DiscType.SKULL))
        if can_bid:
            actions += [Action(ActionType.BID, amount=k) for k in range(1, total + 1)]
        if not actions:   # no discs left to place and bidding not open yet -> must bid
            actions = [Action(ActionType.BID, amount=k) for k in range(1, max(total, 1) + 1)]
        return actions

    # --------------------------------------------------------------- one round
    def _play_round(self, state: GameState) -> None:
        for p in state.players:
            p.hand.extend(p.stack)      # everything starts the round back in hand
            p.stack = []
            p.passed = False
        state.phase = Phase.PLACING
        state.current_bid = 0
        state.highest_bidder = None
        if not state.players[state.starting_player].alive:
            state.starting_player = self._next_alive(state, state.starting_player)
        state.current_player = state.starting_player

        n_alive = len(state.alive_players)
        self._event("round_start", starting_player=state.starting_player,
                    alive=[p.player_id for p in state.alive_players])
        self._public_event("round_start", starting_player=state.starting_player,
                           alive=[p.player_id for p in state.alive_players])

        # --- PLACING -------------------------------------------------------
        placements = 0
        while state.phase == Phase.PLACING:
            pid = state.current_player
            player = state.players[pid]
            # Bidding may open only after every alive player has placed once.
            can_bid = placements >= n_alive
            total = state.discs_on_table
            valid = self._placing_actions(player, can_bid, total)
            action = self._choose(state, pid, valid)

            if action.action_type == ActionType.PLACE:
                disc = player.take_from_hand(action.disc_type)
                player.stack.append(disc)
                placements += 1
                self._log(f"  P{pid} places a disc (stack={len(player.stack)})")
                self._event("place", player=pid)
                self._public_event("place", player=pid, stack=len(player.stack))
                state.current_player = self._next_alive(state, pid)
            else:   # BID — opens the auction
                self._open_bid(state, pid, action.amount)

        # --- BIDDING -------------------------------------------------------
        while state.phase == Phase.BIDDING:
            active = [p for p in state.alive_players if not p.passed]
            if len(active) <= 1:
                state.phase = Phase.REVEAL
                break
            pid = state.current_player
            player = state.players[pid]
            total = state.discs_on_table
            valid = [Action(ActionType.PASS)]
            valid += [Action(ActionType.BID, amount=k)
                      for k in range(state.current_bid + 1, total + 1)]
            action = self._choose(state, pid, valid)

            if action.action_type == ActionType.BID and action.amount > state.current_bid:
                state.current_bid = action.amount
                state.highest_bidder = pid
                self._log(f"  P{pid} bids {action.amount}")
                self._event("bid", player=pid, amount=action.amount)
                self._public_event("bid", player=pid, amount=action.amount)
            else:
                player.passed = True
                self._log(f"  P{pid} passes")
                self._event("pass", player=pid)
                self._public_event("pass", player=pid)
            state.current_player = self._next_active_bidder(state, pid)

        # --- REVEAL --------------------------------------------------------
        self._resolve_reveal(state)

    def _open_bid(self, state: GameState, pid: int, amount: int) -> None:
        total = state.discs_on_table
        amount = max(1, min(amount, total))
        state.current_bid = amount
        state.highest_bidder = pid
        state.phase = Phase.BIDDING
        state.current_player = self._next_active_bidder(state, pid)
        self._log(f"  P{pid} opens bidding at {amount}")
        self._event("bid", player=pid, amount=amount, opening=True)
        self._public_event("bid", player=pid, amount=amount, opening=True)

    # ------------------------------------------------------------- the reveal
    def _resolve_reveal(self, state: GameState) -> None:
        challenger = state.highest_bidder
        bid = state.current_bid
        cp = state.players[challenger]
        self._log(f"  P{challenger} must flip {bid} discs")
        self._event("challenge", player=challenger, bid=bid)
        self._public_event("challenge", player=challenger, bid=bid)

        flipped = 0
        hit_skull = False
        own_skull = False                            # was the skull the challenger's own?
        flipped_discs: list[tuple[int, Disc]] = []   # (owner_id, disc) to return later

        while flipped < bid:
            if cp.stack:                              # flip all of your own first
                source, disc = cp, cp.stack.pop()
            else:
                targets = [p.player_id for p in state.alive_players
                           if p.player_id != challenger and p.stack]
                if not targets:
                    break
                valid = [Action(ActionType.FLIP, target_player=t) for t in targets]
                action = self._choose(state, challenger, valid)
                tid = action.target_player
                source, disc = state.players[tid], state.players[tid].stack.pop()
            flipped_discs.append((source.player_id, disc))
            flipped += 1
            is_skull = disc.disc_type == DiscType.SKULL
            self._log(f"    flips {disc.disc_type.name} from P{source.player_id}")
            self._event("reveal", player=challenger, owner=source.player_id,
                        disc=disc.disc_type.name)
            self._public_event("reveal", player=challenger, owner=source.player_id,
                              disc=disc.disc_type.name)
            if is_skull:
                hit_skull = True
                own_skull = source.player_id == challenger
                break

        # return every flipped disc to its owner before resolving the outcome
        for owner_id, disc in flipped_discs:
            state.players[owner_id].hand.append(disc)
        for p in state.players:                       # un-placed discs come home too
            p.hand.extend(p.stack)
            p.stack = []

        if not hit_skull and flipped >= bid:
            cp.points += 1
            self._log(f"  P{challenger} SUCCEEDS — {cp.points} point(s)")
            self._event("success", player=challenger, points=cp.points)
            self._public_event("success", player=challenger, points=cp.points)
            state.starting_player = challenger
        else:
            self._fail(state, challenger, own_skull=own_skull)

    def _choose_discard(self, state: GameState, challenger: int) -> Disc:
        """Flipping your own skull lets you choose which disc to give up.
        Offer one DISCARD per distinct disc type still in hand and return the
        matching Disc to remove (defaulting to a random one if the pick is bad)."""
        cp = state.players[challenger]
        in_hand = {d.disc_type for d in cp.hand}
        valid = [Action(ActionType.DISCARD, disc_type=t)
                 for t in (DiscType.ROSE, DiscType.SKULL) if t in in_hand]
        prev_phase = state.phase
        state.phase = Phase.DISCARD
        try:
            action = self._choose(state, challenger, valid)
        finally:
            state.phase = prev_phase
        for disc in cp.hand:
            if disc.disc_type == action.disc_type:
                return disc
        return self.rng.choice(cp.hand)

    def _fail(self, state: GameState, challenger: int, own_skull: bool = False) -> None:
        cp = state.players[challenger]
        if own_skull:
            lost = self._choose_discard(state, challenger)   # your skull — you pick the loss
        else:
            lost = self.rng.choice(cp.hand)           # opponent's skull — lost at random
        cp.hand.remove(lost)
        self._log(f"  P{challenger} FAILS — loses a disc ({cp.disc_count} left)")
        self._event("fail", player=challenger, lost=lost.disc_type.name,
                    discs_left=cp.disc_count)
        self._public_event("fail", player=challenger, discs_left=cp.disc_count)
        if cp.disc_count == 0:
            cp.alive = False
            self._elim_order.append(challenger)
            self._log(f"  P{challenger} is ELIMINATED")
            self._event("explode", player=challenger)     # arena death-order event
            self._public_event("eliminated", player=challenger)
            state.starting_player = self._next_alive(state, challenger)
        else:
            # Standard Skull: the player who failed starts the next round.
            state.starting_player = challenger

    # --------------------------------------------------------------- top level
    def play_game(self, n_players: int) -> dict:
        self._events = []
        self._public_events = []
        self._next_public_event_id = 1
        self._elim_order = []
        state = self._setup(n_players)

        for i, agent in enumerate(self.agents[:n_players]):
            agent.game_start(self._observable(state, i))

        return self._run(state)

    def _run(self, state: GameState) -> dict:
        winner = -1
        while state.round_number < MAX_ROUNDS:
            state.round_number += 1
            self._round = state.round_number

            if len(state.alive_players) <= 1:
                break
            self._play_round(state)

            # win by points
            for p in state.alive_players:
                if p.points >= POINTS_TO_WIN:
                    winner = p.player_id
                    break
            if winner >= 0:
                break
            # win by being the last player with discs
            if len(state.alive_players) == 1:
                winner = state.alive_players[0].player_id
                break

        if winner < 0 and state.alive_players:        # MAX_ROUNDS hit: rank by points
            winner = max(state.alive_players,
                         key=lambda p: (p.points, p.disc_count)).player_id

        self._log(f"\nGame over — P{winner} wins after {state.round_number} rounds")
        self._event("game_over", winner=winner)
        self._public_event("game_over", winner=winner)
        self._endgame_chat(state, winner)

        survivors = [p.player_id for p in state.alive_players]
        # Full finishing order, best -> worst, for rating every seat each game:
        # survivors ranked by points then discs held, then the eliminated in
        # reverse death order (last out finished higher than first out).
        alive_sorted = sorted(state.alive_players,
                              key=lambda p: (p.points, p.disc_count), reverse=True)
        finish_order = [p.player_id for p in alive_sorted] + list(reversed(self._elim_order))
        result = {
            "winner": winner,
            "turns": state.round_number,
            "survivors": survivors,
            "elimination_order": list(self._elim_order),
            "finish_order": finish_order,
            "points": {p.player_id: p.points for p in state.players},
        }
        if self.collect_events:
            result["events"] = list(self._events)
        return result
