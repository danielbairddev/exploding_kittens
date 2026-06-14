"""Event encoding for Cassandra — 56 dims.

Layout: event_type(14) + player_rel(5) + target_rel(6) + card_played(14) + card_given(14) + turn_scalars(3) = 56

card_given: populated when Cassandra is the giver in favor/cat_steal (injected
  by rollout._absorb / cassandra_agent._absorb via 'card_given' key on the event).
  Fires the "none" slot for all other events and for steals Cassandra didn't initiate.

turn_scalars: populated only on turn_start events, else 0.0
  [deck_size/30, n_alive/5, turns_remaining/5]
"""

EVENT_TYPES = [
    'turn_start', 'attack', 'skip', 'shuffle', 'see_future',
    'favor', 'cat_steal', 'nope', 'action_noped', 'draw',
    'defuse', 'explode', 'game_over',
]
_ET_IDX = {et: i for i, et in enumerate(EVENT_TYPES)}
N_EVENT_TYPES = len(EVENT_TYPES) + 1  # +1 unknown = 14

CARD_NAMES = [
    'DEFUSE', 'ATTACK', 'SKIP', 'FAVOR', 'SHUFFLE', 'SEE_THE_FUTURE',
    'NOPE', 'TACO_CAT', 'HAIRY_POTATO_CAT', 'BEARD_CAT',
    'RAINBOW_CAT', 'CATTERMELON', 'EXPLODING_KITTEN',
]
_CARD_IDX = {c: i for i, c in enumerate(CARD_NAMES)}
N_CARD_SLOTS = len(CARD_NAMES) + 1  # +1 none = 14

N_PLAYERS = 5
N_TARGET_SLOTS = N_PLAYERS + 1  # +1 none = 6
N_TURN_SCALARS = 3               # deck_size, n_alive, turns_remaining

# 14 + 5 + 6 + 14 + 14 + 3 = 56
N_EVENT = N_EVENT_TYPES + N_PLAYERS + N_TARGET_SLOTS + N_CARD_SLOTS + N_CARD_SLOTS + N_TURN_SCALARS


def encode_event(ev: dict, my_id: int) -> list:
    vec = [0.0] * N_EVENT
    off = 0

    # Event type (14-dim)
    vec[off + _ET_IDX.get(ev.get('type', ''), N_EVENT_TYPES - 1)] = 1.0
    off += N_EVENT_TYPES

    # Actor relative to me (5-dim)
    p = ev.get('player')
    if p is not None:
        vec[off + (p - my_id) % N_PLAYERS] = 1.0
    off += N_PLAYERS

    # Target relative to me (6-dim: 5 seats + none)
    t = ev.get('target_player')
    if t is not None:
        vec[off + (t - my_id) % N_PLAYERS] = 1.0
    else:
        vec[off + N_PLAYERS] = 1.0
    off += N_TARGET_SLOTS

    # Card played / named (14-dim)
    c = ev.get('named_card') or ev.get('cat_type')
    if c is not None and c in _CARD_IDX:
        vec[off + _CARD_IDX[c]] = 1.0
    else:
        vec[off + N_CARD_SLOTS - 1] = 1.0
    off += N_CARD_SLOTS

    # Card given/transferred (14-dim) — injected by caller when Cassandra is the giver
    cg = ev.get('card_given')
    if cg is not None and cg in _CARD_IDX:
        vec[off + _CARD_IDX[cg]] = 1.0
    else:
        vec[off + N_CARD_SLOTS - 1] = 1.0
    off += N_CARD_SLOTS

    # Turn scalars (3-dim) — only populated for turn_start events
    if ev.get('type') == 'turn_start':
        vec[off]     = ev.get('deck_size', 0) / 30.0
        vec[off + 1] = len(ev.get('alive', [])) / 5.0
        vec[off + 2] = min(ev.get('turns_remaining', 1), 5) / 5.0

    return vec
