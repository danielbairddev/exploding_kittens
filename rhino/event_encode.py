"""Encode a game event dict into a fixed-size feature vector.

Pure stdlib + numpy so it works in both the training pipeline and the deployed
agent (which imports this for inference).
"""
import numpy as np

EVENT_TYPES = [
    'turn_start', 'attack', 'skip', 'shuffle', 'see_future',
    'favor', 'cat_steal', 'nope', 'action_noped', 'draw',
    'defuse', 'explode', 'game_over',
]
_ET_IDX = {et: i for i, et in enumerate(EVENT_TYPES)}
N_EVENT_TYPES = len(EVENT_TYPES) + 1   # +1 for unknown

CARD_NAMES = [
    'DEFUSE', 'ATTACK', 'SKIP', 'FAVOR', 'SHUFFLE', 'SEE_THE_FUTURE',
    'NOPE', 'TACO_CAT', 'HAIRY_POTATO_CAT', 'BEARD_CAT',
    'RAINBOW_CAT', 'CATTERMELON', 'EXPLODING_KITTEN',
]
_CARD_IDX = {c: i for i, c in enumerate(CARD_NAMES)}
N_CARD_SLOTS = len(CARD_NAMES) + 1    # +1 for none

N_PLAYERS = 5
N_TARGET_SLOTS = N_PLAYERS + 1        # +1 for none/not-applicable

# Total: 14 + 5 + 6 + 14 = 39
N_EVENT = N_EVENT_TYPES + N_PLAYERS + N_TARGET_SLOTS + N_CARD_SLOTS


def encode_event(ev: dict, my_id: int) -> np.ndarray:
    """Encode one event dict to a float32 vector of length N_EVENT."""
    vec = np.zeros(N_EVENT, dtype=np.float32)
    off = 0

    # Event type (14-dim one-hot)
    vec[off + _ET_IDX.get(ev.get('type', ''), N_EVENT_TYPES - 1)] = 1.0
    off += N_EVENT_TYPES

    # Player (5-dim, relative: 0=self, 1=next seat, …)
    p = ev.get('player')
    if p is not None:
        vec[off + (p - my_id) % N_PLAYERS] = 1.0
    off += N_PLAYERS

    # Target player (6-dim: 5 relative + 1 "none")
    t = ev.get('target_player')
    if t is not None:
        vec[off + (t - my_id) % N_PLAYERS] = 1.0
    else:
        vec[off + N_PLAYERS] = 1.0
    off += N_TARGET_SLOTS

    # Named card (14-dim: 13 types + 1 "none")
    c = ev.get('named_card')
    if c is not None and c in _CARD_IDX:
        vec[off + _CARD_IDX[c]] = 1.0
    else:
        vec[off + N_CARD_SLOTS - 1] = 1.0

    return vec
