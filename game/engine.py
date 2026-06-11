import random
from .cards import Card, CardType, CAT_CARDS, build_deck
from .state import GameState, PlayerState, ObservableState
from .actions import Action, ActionType


class GameEngine:
    def __init__(self, agents: list, seed: int | None = None, verbose: bool = False):
        self.agents = agents
        self.verbose = verbose
        self.rng = random.Random(seed)

    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    def _observable(self, state: GameState, for_player: int) -> ObservableState:
        me = state.players[for_player]
        return ObservableState(
            my_id=for_player,
            my_hand=list(me.hand),
            hand_sizes={p.player_id: len(p.hand) for p in state.players if p.alive},
            alive_players=[p.player_id for p in state.alive_players],
            deck_size=state.deck_size,
            discard_pile=list(state.discard_pile),
            turns_remaining=state.turns_remaining,
            current_player=state.current_player,
        )

    def _setup(self, n_players: int) -> GameState:
        deck = build_deck(n_players)
        self.rng.shuffle(deck)

        players = []
        for i in range(n_players):
            hand = [deck.pop() for _ in range(7)]
            hand.append(Card(CardType.DEFUSE))
            players.append(PlayerState(player_id=i, hand=hand))

        # Add exploding kittens and remaining defuses
        deck.append(Card(CardType.DEFUSE))  # 1 spare defuse
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
                # Check if we have a pair
                if sum(1 for c in player.hand if c.card_type == ct) >= 2:
                    for other in state.alive_players:
                        if other.player_id != state.current_player and other.hand:
                            actions.append(Action(ActionType.PLAY_CAT_PAIR, target_player=other.player_id, cat_type=ct))

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
        """Ask other players if they want to Nope. Returns True if action is noped."""
        noped = False
        for player in state.alive_players:
            if player.player_id == acting_player:
                continue
            if not player.has(CardType.NOPE):
                continue
            obs = self._observable(state, player.player_id)
            if self.agents[player.player_id].want_to_nope(obs, action):
                player.remove(CardType.NOPE)
                state.discard_pile.append(Card(CardType.NOPE))
                noped = not noped  # Nopes can be counter-Noped
                self._log(f"  Player {player.player_id} plays NOPE (action {'cancelled' if noped else 'restored'})")
        return noped

    def _apply_action(self, state: GameState, action: Action) -> bool:
        """Apply action. Returns True if the turn ends (player must draw)."""
        pid = state.current_player
        player = state.players[pid]

        if action.action_type == ActionType.DRAW:
            return True

        if action.action_type == ActionType.PLAY_ATTACK:
            if self._check_nope(state, action, pid):
                return False
            player.remove(CardType.ATTACK)
            state.discard_pile.append(Card(CardType.ATTACK))
            # Next player takes 2 turns (stacks if already under attack)
            next_pid = self._next_alive(state, pid)
            state.current_player = next_pid
            state.turns_remaining = state.turns_remaining + 1 if state.turns_remaining > 1 else 2
            self._log(f"  Player {pid} ATTACKs — player {next_pid} takes {state.turns_remaining} turns")
            return False  # turn already advanced

        if action.action_type == ActionType.PLAY_SKIP:
            if self._check_nope(state, action, pid):
                return False
            player.remove(CardType.SKIP)
            state.discard_pile.append(Card(CardType.SKIP))
            state.turns_remaining -= 1
            if state.turns_remaining <= 0:
                state.turns_remaining = 1
                state.current_player = self._next_alive(state, pid)
            self._log(f"  Player {pid} SKIPs")
            return False

        if action.action_type == ActionType.PLAY_SHUFFLE:
            if self._check_nope(state, action, pid):
                return False
            player.remove(CardType.SHUFFLE)
            state.discard_pile.append(Card(CardType.SHUFFLE))
            self.rng.shuffle(state.draw_pile)
            self._log(f"  Player {pid} SHUFFLEs the deck")
            return False

        if action.action_type == ActionType.PLAY_SEE_THE_FUTURE:
            if self._check_nope(state, action, pid):
                return False
            player.remove(CardType.SEE_THE_FUTURE)
            state.discard_pile.append(Card(CardType.SEE_THE_FUTURE))
            top3 = state.draw_pile[:3]
            obs = self._observable(state, pid)
            obs.known_top3 = top3
            self.agents[pid].see_future(obs, top3)
            self._log(f"  Player {pid} SEEs THE FUTURE: {top3}")
            return False

        if action.action_type == ActionType.PLAY_FAVOR:
            if self._check_nope(state, action, pid):
                return False
            player.remove(CardType.FAVOR)
            state.discard_pile.append(Card(CardType.FAVOR))
            target = state.players[action.target_player]
            obs = self._observable(state, action.target_player)
            given = self.agents[action.target_player].give_card(obs, pid)
            # Validate — must be a card they actually hold
            if given not in [c.card_type for c in target.hand]:
                given = target.hand[0].card_type
            card = target.remove(given)
            player.hand.append(card)
            self._log(f"  Player {pid} FAVORs player {action.target_player} — gets {card}")
            return False

        if action.action_type == ActionType.PLAY_CAT_PAIR:
            if self._check_nope(state, action, pid):
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
            return False
        else:
            player.alive = False
            self._log(f"  Player {pid} EXPLODES 💥")
            return True

    def play_game(self, n_players: int) -> dict:
        state = self._setup(n_players)

        # Notify agents of their starting hands
        for i, agent in enumerate(self.agents[:n_players]):
            agent.game_start(self._observable(state, i))

        state.turn_number = 0
        max_turns = 500  # safety limit

        while len(state.alive_players) > 1 and state.turn_number < max_turns:
            state.turn_number += 1
            pid = state.current_player
            player = state.players[pid]

            if not player.alive:
                state.current_player = self._next_alive(state, pid)
                continue

            self._log(f"\nTurn {state.turn_number} — Player {pid} (hand: {len(player.hand)} cards, deck: {state.deck_size})")

            # Play phase: agent chooses actions until they DRAW
            while True:
                obs = self._observable(state, pid)
                valid = self._valid_actions(state)
                action = self.agents[pid].choose_action(obs, valid)

                # Validate
                if action.action_type not in [a.action_type for a in valid]:
                    action = Action(ActionType.DRAW)

                self._log(f"  Player {pid} chooses {action}")
                end_turn = self._apply_action(state, action)

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

        return {
            "winner": winner,
            "turns": state.turn_number,
            "survivors": [p.player_id for p in state.alive_players],
            "elimination_order": [p.player_id for p in state.players if not p.alive],
        }
