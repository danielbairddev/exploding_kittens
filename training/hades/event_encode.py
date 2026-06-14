"""Hades event encoding — 64-dim event vectors (HADES_PLAN.md §1.1).

Expanded from the 39-dim Rhino/GRU encoder. Pure stdlib (training wraps the
returned list with np.array; the deployed agent uses it directly).

Layout (64 dims):
    event_type      14   (13 known types + 1 unknown)
    actor_rel_seat   5   (0=self, 1=next seat, ... mod 5)
    target_rel_seat  6   (5 relative + 1 none)
    card_played     14   (13 card types + 1 none)
    card_given      14   (13 card types + 1 none; publicly hidden, usually none)
    turn_number_norm 1   (turn / 100)
    is_my_turn       1
    action_resolved  1   (0 for action_noped, else 1)
    cards_to_draw    1   (running attack-stack depth / 5)
    padding_mask     1   (1 = real event, 0 = padding)
    reserved         6

A small running `ctx` dict is threaded through `encode_event` so per-event
fields that depend on history (the live attack stack) can be tracked without
re-scanning the whole log each time.
"""
from game.cards import CardType

EVENT_TYPES = [
    'turn_start', 'attack', 'skip', 'shuffle', 'see_future',
    'favor', 'cat_steal', 'nope', 'action_noped', 'draw',
    'defuse', 'explode', 'game_over',
]
_ET_IDX = {et: i for i, et in enumerate(EVENT_TYPES)}
N_EVENT_TYPES = len(EVENT_TYPES) + 1   # +1 unknown  -> 14

CARD_NAMES = [
    'DEFUSE', 'ATTACK', 'SKIP', 'FAVOR', 'SHUFFLE', 'SEE_THE_FUTURE',
    'NOPE', 'TACO_CAT', 'HAIRY_POTATO_CAT', 'BEARD_CAT',
    'RAINBOW_CAT', 'CATTERMELON', 'EXPLODING_KITTEN',
]
_CARD_IDX = {c: i for i, c in enumerate(CARD_NAMES)}
N_CARD_SLOTS = len(CARD_NAMES) + 1     # +1 none -> 14

N_PLAYERS = 5
N_ACTOR_SLOTS  = N_PLAYERS              # 5
N_TARGET_SLOTS = N_PLAYERS + 1         # 6

N_RESERVED = 6
CONTEXT_WINDOW = 128                    # N=128 events

# Offsets
_O_TYPE   = 0
_O_ACTOR  = _O_TYPE   + N_EVENT_TYPES   # 14
_O_TARGET = _O_ACTOR  + N_ACTOR_SLOTS   # 19
_O_CPLAY  = _O_TARGET + N_TARGET_SLOTS  # 25
_O_CGIVE  = _O_CPLAY  + N_CARD_SLOTS    # 39
_O_TURN   = _O_CGIVE  + N_CARD_SLOTS    # 53
_O_MYTURN = _O_TURN   + 1               # 54
_O_RESOLV = _O_MYTURN + 1               # 55
_O_DRAW   = _O_RESOLV + 1               # 56
_O_PAD    = _O_DRAW   + 1               # 57
_O_RESV   = _O_PAD    + 1               # 58
N_EVENT   = _O_RESV + N_RESERVED        # 64

# Maps an action_type name to the card it consumes (for card_played).
_ACTION_CARD = {
    'PLAY_ATTACK': 'ATTACK', 'PLAY_SKIP': 'SKIP', 'PLAY_FAVOR': 'FAVOR',
    'PLAY_SHUFFLE': 'SHUFFLE', 'PLAY_SEE_THE_FUTURE': 'SEE_THE_FUTURE',
}
# Event types that imply a specific card without an action_type field.
_TYPE_CARD = {'defuse': 'DEFUSE', 'explode': 'EXPLODING_KITTEN', 'nope': 'NOPE'}


def new_context():
    """Fresh per-game running context for cards_to_draw tracking."""
    return {'attack_stack': 1}


def _card_played(ev):
    """Best-effort identity of the card played in this event (or None)."""
    t = ev.get('type', '')
    if t in _TYPE_CARD:
        return _TYPE_CARD[t]
    if t == 'cat_steal':
        ct = ev.get('cat_type')
        return ct if ct in _CARD_IDX else None
    at = ev.get('action_type')
    if at in _ACTION_CARD:
        return _ACTION_CARD[at]
    if at == 'PLAY_CAT_PAIR' or at == 'PLAY_CAT_TRIPLE':
        ct = ev.get('cat_type')
        return ct if ct in _CARD_IDX else None
    return None


def encode_event(ev: dict, my_id: int, ctx: dict | None = None) -> list:
    """Encode one public event dict into a float list of length N_EVENT.

    ctx: optional running context (from new_context()). Mutated in place to
    track the live attack stack for the cards_to_draw feature.
    """
    if ctx is None:
        ctx = new_context()
    vec = [0.0] * N_EVENT
    t = ev.get('type', '')

    # --- update running attack stack BEFORE encoding so cards_to_draw is current ---
    if t == 'attack':
        ctx['attack_stack'] = int(ev.get('turns_imposed', ctx.get('attack_stack', 1)) or 1)
    elif t == 'turn_start':
        ctx['attack_stack'] = int(ev.get('turns_remaining', 1) or 1)
    elif t == 'draw':
        ctx['attack_stack'] = max(1, ctx.get('attack_stack', 1) - 1)

    # event type (14)
    vec[_O_TYPE + _ET_IDX.get(t, N_EVENT_TYPES - 1)] = 1.0

    # actor relative seat (5)
    p = ev.get('player')
    if p is not None:
        vec[_O_ACTOR + (p - my_id) % N_PLAYERS] = 1.0

    # target relative seat (6: 5 rel + none)
    tgt = ev.get('target_player')
    if tgt is None:
        tgt = ev.get('target')
    if tgt is None and t in ('favor', 'cat_steal'):
        tgt = ev.get('from_player')
    if tgt is not None:
        vec[_O_TARGET + (tgt - my_id) % N_PLAYERS] = 1.0
    else:
        vec[_O_TARGET + N_PLAYERS] = 1.0

    # card played (14)
    cp = _card_played(ev)
    if cp in _CARD_IDX:
        vec[_O_CPLAY + _CARD_IDX[cp]] = 1.0
    else:
        vec[_O_CPLAY + N_CARD_SLOTS - 1] = 1.0

    # card given (14) — publicly hidden; named_card on a triple demand is the
    # closest public signal of an intended transfer.
    cg = ev.get('named_card')
    if cg in _CARD_IDX:
        vec[_O_CGIVE + _CARD_IDX[cg]] = 1.0
    else:
        vec[_O_CGIVE + N_CARD_SLOTS - 1] = 1.0

    # scalars
    vec[_O_TURN]   = min(ev.get('turn', 0) or 0, 200) / 100.0
    vec[_O_MYTURN] = 1.0 if p == my_id else 0.0
    vec[_O_RESOLV] = 0.0 if t == 'action_noped' else 1.0
    vec[_O_DRAW]   = min(ctx.get('attack_stack', 1), 5) / 5.0
    vec[_O_PAD]    = 1.0  # real event

    return vec


def padding_vector() -> list:
    """A zero/padding event (padding_mask = 0)."""
    return [0.0] * N_EVENT
