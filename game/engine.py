import random
from .cards import Card, CardType, CAT_CARDS, build_deck
from .state import GameState, PlayerState, ObservableState
from .actions import Action, ActionType


class GameEngine:
    def __init__(self, agents: list, seed: int | None = None, verbose: bool = False,
                 collect_events: bool = False, reveal_top: bool = False):
        self.agents = agents
        self.verbose = verbose
        self.collect_events = collect_events
        self.reveal_top = reveal_top   # god-mode: always expose the real top 3 (oracle test)
        self.rng = random.Random(seed)
        self._events: list[dict] = []
        self._public_events: list[dict] = []
        self._next_public_event_id: int = 1
        self._turn: int = 0

    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    def _event(self, type: str, **kwargs):
        if self.collect_events:
            self._events.append({"turn": self._turn, "type": type, **kwargs})

    def _public_event(self, type: str, **kwargs):
        event = {
            "event_id": self._next_public_event_id,
            "turn": self._turn,
            "type": type,
            **kwargs,
        }
        self._next_public_event_id += 1
        self._public_events.append(event)

    @staticmethod
    def _public_action(action: Action) -> dict:
        return {
            "action_type": action.action_type.name,
            "target_player": action.target_player,
            "cat_type": action.cat_type.name if action.cat_type else None,
            "named_card": action.named_card.name if action.named_card else None,
        }

    def _observable(self, state: GameState, for_player: int) -> ObservableState:
        me = state.players[for_player]
        obs = ObservableState(
            my_id=for_player,
            my_hand=list(me.hand),
            hand_sizes={p.player_id: len(p.hand) for p in state.players if p.alive},
            alive_players=[p.player_id for p in state.alive_players],
            deck_size=state.deck_size,
            discard_pile=list(state.discard_pile),
            turns_remaining=state.turns_remaining,
            current_player=state.current_player,
            recent_events=list(self._public_events),
        )
        if self.reveal_top:
            obs.known_top3 = [Card(c.card_type) for c in state.draw_pile[:3]]
        return obs

    def _setup(self, n_players: int) -> GameState:
        deck = build_deck(n_players)
        self.rng.shuffle(deck)

        players = []
        for i in range(n_players):
            hand = [deck.pop() for _ in range(7)]
            hand.append(Card(CardType.DEFUSE))
            players.append(PlayerState(player_id=i, hand=hand))

        # Add remaining defuses (6 total in box; n_players already dealt to hands)
        for _ in range(max(0, 6 - n_players)):
            deck.append(Card(CardType.DEFUSE))
        for _ in range(n_players - 1):
            deck.append(Card(CardType.EXPLODING_KITTEN))
        self.rng.shuffle(deck)

        return GameState(
            players=players,
            draw_pile=deck,
            discard_pile=[],
            current_player=0,
            turns_remaining=1,
        )

    def _valid_actions(self, state: GameState) -> list[Action]:
        player = state.players[state.current_player]
        actions = [Action(ActionType.DRAW)]

        for card in player.hand:
            ct = card.card_type
            if ct == CardType.ATTACK:
                actions.append(Action(ActionType.PLAY_ATTACK))
            elif ct == CardType.SKIP:
                actions.append(Action(ActionType.PLAY_SKIP))
            elif ct == CardType.SHUFFLE:
                actions.append(Action(ActionType.PLAY_SHUFFLE))
            elif ct == CardType.SEE_THE_FUTURE:
                actions.append(Action(ActionType.PLAY_SEE_THE_FUTURE))
            elif ct == CardType.FAVOR:
                for other in state.alive_players:
                    if other.player_id != state.current_player and other.hand:
                        actions.append(Action(ActionType.PLAY_FAVOR, target_player=other.player_id))
            elif ct in CAT_CARDS:
                count = sum(1 for c in player.hand if c.card_type == ct)
                if count >= 2:
                    for other in state.alive_players:
                        if other.player_id != state.current_player and other.hand:
                            actions.append(Action(ActionType.PLAY_CAT_PAIR, target_player=other.player_id, cat_type=ct))
                if count >= 3:
                    for other in state.alive_players:
                        if other.player_id != state.current_player and other.hand:
                            # named_card=None here; agents fill it in when they choose this action
                            actions.append(Action(ActionType.PLAY_CAT_TRIPLE, target_player=other.player_id, cat_type=ct))

        # Deduplicate
        seen = set()
        unique = []
        for a in actions:
            key = (a.action_type, a.target_player, a.cat_type)
            if key not in seen:
                seen.add(key)
                unique.append(a)
        return unique



    def _check_nope(self, state: GameState, action: Action, acting_player: int) -> bool:
        """
        Nope resolution loop. Any player (including the actor) can play a Nope.
        Keeps asking in seat order until a full round passes with no Nopes played.
        Each Nope flips whether the action is currently cancelled.
        """
        noped = False
        while True:
            any_played = False
            for player in state.alive_players:
                if not player.has(CardType.NOPE):
                    continue
                obs = self._observable(state, player.player_id)
                if self.agents[player.player_id].want_to_nope(obs, action, noped):
                    player.remove(CardType.NOPE)
                    state.discard_pile.append(Card(CardType.NOPE))
                    noped = not noped
                    any_played = True
                    self._log(
                        f"  Player {player.player_id} plays NOPE "
                        f"(action {'cancelled' if noped else 'restored'})"
                    )
                    self._event("nope", player=player.player_id,
                                action_type=action.action_type.name,
                                result="cancelled" if noped else "restored")
                    self._public_event(
                        "nope",
                        player=player.player_id,
                        action_player=acting_player,
                        result="cancelled" if noped else "restored",
                        **self._public_action(action),
                    )
            if not any_played:
                break
        return noped

    def _apply_action(self, state: GameState, action: Action) -> bool:
        """Apply action. Returns True if the turn ends (player must draw)."""
        pid = state.current_player
        player = state.players[pid]

        if action.action_type == ActionType.DRAW:
            return True

        if action.action_type == ActionType.PLAY_ATTACK:
            if self._check_nope(state, action, pid):
                self._event("action_noped", player=pid, action_type="PLAY_ATTACK")
                self._public_event("action_noped", player=pid, **self._public_action(action))
                return False
            player.remove(CardType.ATTACK)
            state.discard_pile.append(Card(CardType.ATTACK))
            next_pid = self._next_alive(state, pid)
            state.current_player = next_pid
            state.turns_remaining = state.turns_remaining + 1 if state.turns_remaining > 1 else 2
            self._log(f"  Player {pid} ATTACKs — player {next_pid} takes {state.turns_remaining} turns")
            self._event("attack", player=pid, target=next_pid, turns_imposed=state.turns_remaining)
            self._public_event(
                "attack",
                player=pid,
                target=next_pid,
                turns_imposed=state.turns_remaining,
                **self._public_action(action),
            )
            return False

        if action.action_type == ActionType.PLAY_SKIP:
            if self._check_nope(state, action, pid):
                self._event("action_noped", player=pid, action_type="PLAY_SKIP")
                self._public_event("action_noped", player=pid, **self._public_action(action))
                return False
            player.remove(CardType.SKIP)
            state.discard_pile.append(Card(CardType.SKIP))
            state.turns_remaining -= 1
            if state.turns_remaining <= 0:
                state.turns_remaining = 1
                state.current_player = self._next_alive(state, pid)
            self._log(f"  Player {pid} SKIPs")
            self._event("skip", player=pid)
            self._public_event("skip", player=pid, **self._public_action(action))
            return False

        if action.action_type == ActionType.PLAY_SHUFFLE:
            if self._check_nope(state, action, pid):
                self._event("action_noped", player=pid, action_type="PLAY_SHUFFLE")
                self._public_event("action_noped", player=pid, **self._public_action(action))
                return False
            player.remove(CardType.SHUFFLE)
            state.discard_pile.append(Card(CardType.SHUFFLE))
            self.rng.shuffle(state.draw_pile)
            self._log(f"  Player {pid} SHUFFLEs the deck")
            self._event("shuffle", player=pid)
            self._public_event("shuffle", player=pid, **self._public_action(action))
            return False

        if action.action_type == ActionType.PLAY_SEE_THE_FUTURE:
            if self._check_nope(state, action, pid):
                self._event("action_noped", player=pid, action_type="PLAY_SEE_THE_FUTURE")
                self._public_event("action_noped", player=pid, **self._public_action(action))
                return False
            player.remove(CardType.SEE_THE_FUTURE)
            state.discard_pile.append(Card(CardType.SEE_THE_FUTURE))
            top3 = state.draw_pile[:3]
            obs = self._observable(state, pid)
            obs.known_top3 = top3
            self.agents[pid].see_future(obs, top3)
            self._log(f"  Player {pid} SEEs THE FUTURE: {top3}")
            self._event("see_future", player=pid, top3=[c.card_type.name for c in top3])
            self._public_event("see_future", player=pid, **self._public_action(action))
            return False

        if action.action_type == ActionType.PLAY_FAVOR:
            if self._check_nope(state, action, pid):
                self._event("action_noped", player=pid, action_type="PLAY_FAVOR", target=action.target_player)
                self._public_event("action_noped", player=pid, **self._public_action(action))
                return False
            player.remove(CardType.FAVOR)
            state.discard_pile.append(Card(CardType.FAVOR))
            target = state.players[action.target_player]
            if not target.hand:
                return False
            obs = self._observable(state, action.target_player)
            given = self.agents[action.target_player].give_card(obs, pid)
            if given not in [c.card_type for c in target.hand]:
                given = target.hand[0].card_type
            card = target.remove(given)
            player.hand.append(card)
            self._log(f"  Player {pid} FAVORs player {action.target_player} — gets {card}")
            self._event("favor", player=pid, from_player=action.target_player, card=card.card_type.name)
            self._public_event(
                "favor",
                player=pid,
                from_player=action.target_player,
                **self._public_action(action),
            )
            return False

        if action.action_type == ActionType.PLAY_CAT_PAIR:
            if self._check_nope(state, action, pid):
                self._event("action_noped", player=pid, action_type="PLAY_CAT_PAIR", target=action.target_player)
                self._public_event("action_noped", player=pid, **self._public_action(action))
                return False
            player.remove(action.cat_type)
            player.remove(action.cat_type)
            state.discard_pile.extend([Card(action.cat_type), Card(action.cat_type)])
            target = state.players[action.target_player]
            if target.hand:
                stolen = self.rng.choice(target.hand)
                target.hand.remove(stolen)
                player.hand.append(stolen)
                self._log(f"  Player {pid} CAT-PAIRs player {action.target_player} — steals {stolen}")
                self._event("cat_steal", player=pid, from_player=action.target_player,
                            cat_type=action.cat_type.name, card=stolen.card_type.name, method="pair")
                self._public_event(
                    "cat_steal",
                    player=pid,
                    from_player=action.target_player,
                    method="pair",
                    **self._public_action(action),
                )
            return False

        if action.action_type == ActionType.PLAY_CAT_TRIPLE:
            if self._check_nope(state, action, pid):
                self._event("action_noped", player=pid, action_type="PLAY_CAT_TRIPLE", target=action.target_player)
                self._public_event("action_noped", player=pid, **self._public_action(action))
                return False
            player.remove(action.cat_type)
            player.remove(action.cat_type)
            player.remove(action.cat_type)
            state.discard_pile.extend([Card(action.cat_type)] * 3)
            target = state.players[action.target_player]
            if target.hand:
                wanted = action.named_card
                if wanted and any(c.card_type == wanted for c in target.hand):
                    card = target.remove(wanted)
                else:
                    card = self.rng.choice(target.hand)
                    target.hand.remove(card)
                player.hand.append(card)
                self._log(f"  Player {pid} CAT-TRIPLEs player {action.target_player} — steals {card}")
                self._event("cat_steal", player=pid, from_player=action.target_player,
                            cat_type=action.cat_type.name, card=card.card_type.name, method="triple",
                            demanded=wanted.name if wanted else None)
                self._public_event(
                    "cat_steal",
                    player=pid,
                    from_player=action.target_player,
                    method="triple",
                    **self._public_action(action),
                )
            return False

        return False

    def _next_alive(self, state: GameState, current: int) -> int:
        n = len(state.players)
        nxt = (current + 1) % n
        while not state.players[nxt].alive:
            nxt = (nxt + 1) % n
        return nxt

    def _draw_card(self, state: GameState) -> bool:
        """Draw a card. Returns True if player explodes without defuse."""
        pid = state.current_player
        player = state.players[pid]

        if not state.draw_pile:
            # Empty deck — no exploding kitten possible, just skip
            return False

        card = state.draw_pile.pop(0)
        self._log(f"  Player {pid} draws {card}")

        if card.card_type != CardType.EXPLODING_KITTEN:
            player.hand.append(card)
            self._event("draw", player=pid, card=card.card_type.name)
            self._public_event("draw", player=pid)
            return False

        # Exploding kitten!
        if player.has(CardType.DEFUSE):
            player.remove(CardType.DEFUSE)
            state.discard_pile.append(Card(CardType.DEFUSE))
            obs = self._observable(state, pid)
            pos = self.agents[pid].place_exploding_kitten(obs, len(state.draw_pile))
            pos = max(0, min(pos, len(state.draw_pile)))
            state.draw_pile.insert(pos, Card(CardType.EXPLODING_KITTEN))
            self._log(f"  Player {pid} DEFUSEs — inserts EK at position {pos}")
            self._event("defuse", player=pid, ek_position=pos, deck_size=len(state.draw_pile))
            self._public_event("defuse", player=pid)
            return False
        else:
            player.alive = False
            self._log(f"  Player {pid} EXPLODES 💥")
            self._event("explode", player=pid)
            self._public_event("explode", player=pid)
            return True

    def play_game(self, n_players: int) -> dict:
        self._events = []
        self._public_events = []
        self._next_public_event_id = 1
        state = self._setup(n_players)

        # Notify agents of their starting hands
        for i, agent in enumerate(self.agents[:n_players]):
            agent.game_start(self._observable(state, i))

        state.turn_number = 0
        return self._run(state)

    def play_out(self, state: GameState) -> dict:
        """Continue an already-in-progress game to completion (Monte-Carlo coach
        rollouts). Agents are (re)initialised at this state; current_player must
        already be set on `state`."""
        self._events = []
        for i, agent in enumerate(self.agents):
            if i < len(state.players):
                agent.game_start(self._observable(state, i))
        return self._run(state)

    def _run(self, state: GameState) -> dict:
        self._state = state          # expose live state (interactive play / coach)
        max_turns = 500  # safety limit

        while len(state.alive_players) > 1 and state.turn_number < max_turns:
            state.turn_number += 1
            self._turn = state.turn_number
            pid = state.current_player
            player = state.players[pid]

            if not player.alive:
                state.current_player = self._next_alive(state, pid)
                continue

            self._log(f"\nTurn {state.turn_number} — Player {pid} (hand: {len(player.hand)} cards, deck: {state.deck_size})")
            self._event("turn_start", player=pid, hand_size=len(player.hand),
                        deck_size=state.deck_size,
                        alive=[p.player_id for p in state.alive_players],
                        hand_sizes={p.player_id: len(p.hand) for p in state.players if p.alive})
            self._public_event(
                "turn_start",
                player=pid,
                hand_size=len(player.hand),
                deck_size=state.deck_size,
                alive=[p.player_id for p in state.alive_players],
                hand_sizes={p.player_id: len(p.hand) for p in state.players if p.alive},
                turns_remaining=state.turns_remaining,
            )

            # Play phase: agent chooses actions until they DRAW
            while True:
                obs = self._observable(state, pid)
                valid = self._valid_actions(state)
                action = self.agents[pid].choose_action(obs, valid)

                # Validate action type is in valid set
                valid_types = {(a.action_type, a.target_player, a.cat_type) for a in valid}
                key = (action.action_type, action.target_player, action.cat_type)
                if key not in valid_types and action.action_type not in {a.action_type for a in valid}:
                    action = Action(ActionType.DRAW)

                self._log(f"  Player {pid} chooses {action}")
                self._apply_action(state, action)

                if action.action_type == ActionType.DRAW:
                    self._draw_card(state)
                    # Advance turn
                    state.turns_remaining -= 1
                    if state.turns_remaining <= 0:
                        state.turns_remaining = 1
                        state.current_player = self._next_alive(state, pid)
                    break

                # If action advanced the player (ATTACK/SKIP), break out
                if state.current_player != pid:
                    break

        winner = state.alive_players[0].player_id if state.alive_players else -1
        self._log(f"\nGame over — Player {winner} wins in {state.turn_number} turns")
        self._event("game_over", winner=winner)
        self._public_event("game_over", winner=winner)

        result = {
            "winner": winner,
            "turns": state.turn_number,
            "survivors": [p.player_id for p in state.alive_players],
            "elimination_order": [p.player_id for p in state.players if not p.alive],
        }
        if self.collect_events:
            result["events"] = list(self._events)
        return result
