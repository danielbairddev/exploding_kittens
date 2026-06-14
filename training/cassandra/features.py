"""Snapshot feature encoding for Cassandra — 97 dims vs Orpheus/Gabriel's 52.

Key upgrades:
  - known_top_3: 3 × 14-dim full one-hots instead of 3 binary flags (42 vs 3 dims)
  - deck_parity: deck_size % 2, critical for 2-player bomb placement strategy
  - opp_defuses_used: per-opponent count of observed defuse events (4 dims)
  - turns_in_ring: how many opponents draw before Orpheus's next draw (1 dim)

Layout:
  hand_counts(12) + discard_counts(12) + unseen_counts(12) +
  scalars(9) + opp_hand_sizes(4) + opp_defuses_used(4) +
  opp_aggregates(2) + known_top_3(42) = 97
"""
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

# All 13 card types for known_top one-hots (EK included)
ALL_CARD_TYPES = _COUNT_TYPES + [CardType.EXPLODING_KITTEN]
_CARD_OH_IDX = {ct: i for i, ct in enumerate(ALL_CARD_TYPES)}
N_CARD_OH = len(ALL_CARD_TYPES) + 1  # 14: 13 types + 1 "unknown" slot

EK  = CardType.EXPLODING_KITTEN
DEF = CardType.DEFUSE

N_SNAP = 97


def _turn_order(state):
    order = sorted(state.alive_players)
    if state.my_id in order:
        i = order.index(state.my_id)
        return order[i + 1:] + order[:i]
    return order


def encode(state, known_top=None, opp_defuses_used=None, ek_count=None):
    """
    state: ObservableState
    known_top: list[CardType] of up to 3 top-deck cards (from SEE THE FUTURE)
    opp_defuses_used: dict[player_id -> int] of observed defuse events per player
    """
    hand = [c.card_type for c in state.my_hand]
    hand_ct = {t: 0 for t in _COUNT_TYPES}
    for t in hand:
        if t in hand_ct:
            hand_ct[t] += 1

    disc_ct = {t: 0 for t in _COUNT_TYPES}
    for c in state.discard_pile:
        if c.card_type in disc_ct:
            disc_ct[c.card_type] += 1

    f = []

    # Hand counts (12)
    f += [hand_ct[t] / 4.0 for t in _COUNT_TYPES]

    # Discard counts (12)
    f += [disc_ct[t] / 6.0 for t in _COUNT_TYPES]

    # Unseen fraction per type (12)
    f += [max(0, _TOTALS[t] - hand_ct[t] - disc_ct[t]) / _TOTALS[t]
          for t in _COUNT_TYPES]

    # Scalars (9)
    deck = state.deck_size
    alive = len(state.alive_players)
    ring = _turn_order(state)
    f.append(deck / 30.0)                                       # deck size
    f.append(min(state.turns_remaining, 5) / 5.0)              # attack stack
    f.append(1.0 if state.turns_remaining > 1 else 0.0)        # under attack
    f.append(alive / 5.0)                                       # players alive
    f.append(len(hand) / 12.0)                                  # my hand size
    f.append(hand_ct[DEF] / 2.0)                               # my defuse count
    ek = ek_count if ek_count is not None else state.deck_exploding_kittens_count
    f.append(ek / max(deck, 1))                                  # exact EK draw prob
    f.append(float(deck % 2))                                   # deck parity (NEW)
    f.append(len(ring) / 4.0)                                   # opponents before my draw (NEW)

    # Opponent hand sizes in turn order (4)
    opp = [h for pid, h in state.hand_sizes.items() if pid != state.my_id]
    sizes = [state.hand_sizes.get(pid, 0) / 12.0 for pid in ring[:4]]
    f += sizes + [0.0] * (4 - len(sizes))

    # Opponent defuse events observed in turn order (4) (NEW)
    du = opp_defuses_used or {}
    dused = [du.get(pid, 0) / 3.0 for pid in ring[:4]]
    f += dused + [0.0] * (4 - len(dused))

    # Opponent aggregates (2)
    f.append((max(opp) if opp else 0) / 12.0)
    f.append((sum(opp) / len(opp) if opp else 0) / 12.0)

    # Known top-3 full one-hots (42 = 3 × 14) — slot 13 = "unknown" (NEW)
    for i in range(3):
        slot = [0.0] * N_CARD_OH
        if known_top and i < len(known_top):
            ct  = known_top[i]
            idx = _CARD_OH_IDX.get(ct)
            slot[idx if idx is not None else N_CARD_OH - 1] = 1.0
        else:
            slot[N_CARD_OH - 1] = 1.0  # unknown slot
        f += slot

    assert len(f) == N_SNAP, f"feature length {len(f)} != {N_SNAP}"
    return f
