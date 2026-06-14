"""Hades snapshot features — 134-dim state vector (HADES_PLAN.md §1.2).

Pure stdlib so the deployed agent has no third-party dependency.

Layout (134 dims):
    core counts        42   hand_counts(14) | discard_counts(14) | unseen_frac(14)
    scalars            10
    opponent matrix    40   4 opponents x 10
    exact deck state   42   14 card slots x top-3 positions (from See-the-Future)

The opponent matrix needs running per-player statistics, so callers maintain an
`OpponentTracker` across the game and pass it to `encode`.
"""
from game.cards import CardType

# 13 real card types (incl. EK) + 1 trailing pad slot = 14 per count block.
CARD_NAMES = [
    'DEFUSE', 'ATTACK', 'SKIP', 'FAVOR', 'SHUFFLE', 'SEE_THE_FUTURE',
    'NOPE', 'TACO_CAT', 'HAIRY_POTATO_CAT', 'BEARD_CAT',
    'RAINBOW_CAT', 'CATTERMELON', 'EXPLODING_KITTEN',
]
_NAME_TO_CT = {n: getattr(CardType, n) for n in CARD_NAMES}
_CARD_IDX = {n: i for i, n in enumerate(CARD_NAMES)}
N_CARD = 14   # 13 + pad

# Total copies of each type (Defuse 6 in box; EK = n_players-1 = 4 in a 5p game).
_TOTALS = {
    'DEFUSE': 6, 'ATTACK': 4, 'SKIP': 4, 'FAVOR': 4, 'SHUFFLE': 4,
    'SEE_THE_FUTURE': 5, 'NOPE': 5, 'TACO_CAT': 4, 'HAIRY_POTATO_CAT': 4,
    'BEARD_CAT': 4, 'RAINBOW_CAT': 4, 'CATTERMELON': 4, 'EXPLODING_KITTEN': 4,
}

N_PLAYERS = 5
N_OPP = 4
OPP_FEATS = 10
N_CORE = 3 * N_CARD          # 42
N_SCALARS = 10
N_OPP_MATRIX = N_OPP * OPP_FEATS  # 40
N_DECK = 3 * N_CARD          # 42
N_FEATURES = N_CORE + N_SCALARS + N_OPP_MATRIX + N_DECK  # 134

START_DECK = 47.0  # approx full draw pile size at game start (5p)


def _turn_order(state):
    """Live opponents in turn order starting after me (wrapping)."""
    order = sorted(state.alive_players)
    if state.my_id in order:
        i = order.index(state.my_id)
        return order[i + 1:] + order[:i]
    return order


class OpponentTracker:
    """Per-game running statistics about each opponent, fed from recent_events.

    All probabilistic fields are coarse heuristics (the network learns to weight
    them); they are documented inline. prob_has_defuse starts at a uniform prior
    and decays when a player is seen to spend a Defuse.
    """

    def __init__(self, my_id):
        self.my_id = my_id
        self._last_eid = -1
        self.attacked_me = {}        # pid -> count of attacks targeting me
        self.defuses_to_me = {}      # pid -> Defuses this pid gave me (via favor/steal we can't see; favor from me)
        self.stolen_from_me = {}     # pid -> cards stolen from me
        self.defuses_used = {}       # pid -> observed defuse events
        self.plays = {}              # pid -> count of card plays
        self.turns = {}              # pid -> count of turn_starts
        self.nopes = {}              # pid -> count of nope plays
        self.nope_chances = {}       # pid -> nope-able actions seen while alive
        self.targeted = {}           # pid -> times this pid was targeted by anyone
        self.prob_defuse = {}        # pid -> heuristic P(holds a defuse)

    def _get(self, d, pid):
        return d.get(pid, 0)

    def update(self, state):
        """Consume any new public events since the last call."""
        new = sorted([e for e in state.recent_events
                      if e.get('event_id', 0) > self._last_eid],
                     key=lambda e: e.get('event_id', 0))
        for ev in new:
            self._last_eid = ev.get('event_id', self._last_eid)
            t = ev.get('type', '')
            p = ev.get('player')
            if p is None:
                continue
            if p != self.my_id:
                self.prob_defuse.setdefault(p, 0.55)
            if t == 'turn_start':
                self.turns[p] = self.turns.get(p, 0) + 1
            elif t == 'attack':
                tgt = ev.get('target')
                self.plays[p] = self.plays.get(p, 0) + 1
                if tgt == self.my_id:
                    self.attacked_me[p] = self.attacked_me.get(p, 0) + 1
                if tgt is not None and tgt != self.my_id:
                    self.targeted[tgt] = self.targeted.get(tgt, 0) + 1
            elif t in ('skip', 'shuffle', 'see_future', 'favor', 'cat_steal'):
                self.plays[p] = self.plays.get(p, 0) + 1
                tgt = ev.get('target_player')
                if tgt is None:
                    tgt = ev.get('from_player')
                if tgt is not None and tgt != self.my_id:
                    self.targeted[tgt] = self.targeted.get(tgt, 0) + 1
                if t == 'cat_steal' and ev.get('from_player') == self.my_id:
                    self.stolen_from_me[p] = self.stolen_from_me.get(p, 0) + 1
            elif t == 'nope':
                self.nopes[p] = self.nopes.get(p, 0) + 1
                self.plays[p] = self.plays.get(p, 0) + 1
            elif t == 'defuse':
                # This player just spent a Defuse on an EK.
                self.defuses_used[p] = self.defuses_used.get(p, 0) + 1
                self.prob_defuse[p] = max(0.05, self.prob_defuse.get(p, 0.55) - 0.4)
            elif t == 'draw':
                # Survived a draw — tiny erosion of "must be holding a defuse" prior.
                self.prob_defuse[p] = max(0.05, self.prob_defuse.get(p, 0.55) * 0.98)
            # Count nope opportunities for everyone alive (rough denominator).
            if t in ('attack', 'skip', 'shuffle', 'see_future', 'favor',
                     'cat_steal', 'nope'):
                for q in state.alive_players:
                    if q != p and q != self.my_id:
                        self.nope_chances[q] = self.nope_chances.get(q, 0) + 1

    def row(self, pid):
        """10-dim feature row for opponent pid (already known alive)."""
        turns = max(1, self.turns.get(pid, 0))
        chances = max(1, self.nope_chances.get(pid, 0))
        return [
            0.0,  # hand_size filled by caller (needs state.hand_sizes)
            min(self.defuses_used.get(pid, 0), 3) / 3.0,
            self.prob_defuse.get(pid, 0.55),
            1.0,  # is_alive (caller only calls for alive opp)
            min(self.attacked_me.get(pid, 0), 5) / 5.0,
            min(self.defuses_to_me.get(pid, 0), 3) / 3.0,
            min(self.stolen_from_me.get(pid, 0), 5) / 5.0,
            min(self.plays.get(pid, 0) / turns, 4.0) / 4.0,        # play_rate
            min(self.nopes.get(pid, 0) / chances, 1.0),            # nope_rate
            min(self.targeted.get(pid, 0), 8) / 8.0,               # is_targeted_often
        ]


def encode(state, tracker, known_top=None):
    """ObservableState (+ OpponentTracker + optional STF top-3) -> list[float]."""
    hand = [c.card_type for c in state.my_hand]
    hand_ct = {n: 0 for n in CARD_NAMES}
    for c in hand:
        if c.name in hand_ct:
            hand_ct[c.name] += 1
    disc_ct = {n: 0 for n in CARD_NAMES}
    for c in state.discard_pile:
        if c.card_type.name in disc_ct:
            disc_ct[c.card_type.name] += 1

    f = []
    # --- core counts (42) ---
    f += [hand_ct[n] / 4.0 for n in CARD_NAMES] + [0.0]                       # 14 hand
    f += [disc_ct[n] / 6.0 for n in CARD_NAMES] + [0.0]                       # 14 discard
    f += [max(0, _TOTALS[n] - hand_ct[n] - disc_ct[n]) / _TOTALS[n]
          for n in CARD_NAMES] + [0.0]                                        # 14 unseen

    # --- scalars (10) ---
    deck = max(1, state.deck_size)
    alive = max(1, len(state.alive_players))
    known_eks = getattr(state, 'deck_exploding_kittens_count', alive - 1)
    f.append(state.deck_size / START_DECK)                                    # deck_size_norm
    f.append(min(state.turns_remaining, 5) / 5.0)                            # cards_to_draw
    f.append(alive / 5.0)                                                     # n_alive
    f.append(len(hand) / 12.0)                                                # my_hand_size
    f.append(hand_ct['DEFUSE'] / 2.0)                                         # my_defuses
    f.append(min(known_eks / deck, 1.0))                                     # ek_draw_prob
    f.append(min(known_eks, 4) / 4.0)                                        # known_eks_in_deck
    f.append(min(_turns_to_my_turn(state), 8) / 8.0)                         # turns_to_my_turn
    f.append(max(0, _TOTALS['NOPE'] - hand_ct['NOPE'] - disc_ct['NOPE'])
             / _TOTALS['NOPE'])                                              # nopes_in_wild
    f.append(max(0, _TOTALS['DEFUSE'] - hand_ct['DEFUSE'] - disc_ct['DEFUSE'])
             / _TOTALS['DEFUSE'])                                            # defuses_in_wild

    # --- opponent matrix (40) ---
    ring = _turn_order(state)[:N_OPP]
    for i in range(N_OPP):
        if i < len(ring):
            pid = ring[i]
            row = tracker.row(pid)
            row[0] = min(state.hand_sizes.get(pid, 0), 12) / 12.0
            f += row
        else:
            f += [0.0] * OPP_FEATS

    # --- exact deck state (42) ---
    for pos in range(3):
        slot = [0.0] * N_CARD
        if known_top and pos < len(known_top):
            name = known_top[pos].name if hasattr(known_top[pos], 'name') else known_top[pos]
            if name in _CARD_IDX:
                slot[_CARD_IDX[name]] = 1.0
        f += slot

    return f


def _turns_to_my_turn(state):
    """Approx number of opponent turns before the bot next acts."""
    order = sorted(state.alive_players)
    if state.my_id not in order or state.current_player not in order:
        return 0
    n = len(order)
    ci = order.index(state.current_player)
    mi = order.index(state.my_id)
    dist = (mi - ci) % n
    # account for the attack stack on the current player
    return dist + max(0, state.turns_remaining - 1)
