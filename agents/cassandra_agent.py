"""Cassandra — GRU-192 bot trained to lose with full decision context.

Architecture improvements over Orpheus/Gabriel:
  - Nope head sees the card being played and whether it targets Cassandra
    (fixes always-nope problem)
  - Place head sees deck parity for correct 2-player bomb placement
  - Policy head can learn to use SEE THE FUTURE for bomb intel
  - Event stream encodes card_given in favor/steal events
  - Per-opponent defuse tracking in snapshot

Goal: not be the last survivor. Trained against Ian/Perdition loser fleet
      + mixed Rhino/Elephant winner fleet.

Disabled in arena until training matures — see dashboard_server.py (ARENA_BOTS).
"""
import json, math, os
from agents.base import Agent
from game.actions import Action, ActionType
from game.cards import CardType

try:
    import numpy as _np
    _HAS_NP = True
except ImportError:
    _np = None
    _HAS_NP = False

try:
    from training.cassandra.event_encode import encode_event, CARD_NAMES, N_CARD_SLOTS, _CARD_IDX
    from training.cassandra.features import encode as snap_encode, BUCKET_FRACS
    from training.cassandra.net import (GRU_H, N_TARGETS, N_CARD_TYPES, N_BUCKETS,
                                         NOPE_CTX_DIM, N_ACTIONS as _N_ACTIONS)
    from agents.orangutan_features import ACTIONS
    _HAS_TRAINING = True
except ImportError:
    CARD_NAMES = ['DEFUSE','ATTACK','SKIP','FAVOR','SHUFFLE','SEE_THE_FUTURE','NOPE',
                  'TACO_CAT','HAIRY_POTATO_CAT','BEARD_CAT','RAINBOW_CAT','CATTERMELON',
                  'EXPLODING_KITTEN']
    N_CARD_SLOTS = 14
    BUCKET_FRACS = [0.0, 0.25, 0.5, 0.75, 1.0]
    GRU_H = 192; N_TARGETS = 5; N_CARD_TYPES = 13; N_BUCKETS = 5; NOPE_CTX_DIM = 24
    _HAS_TRAINING = False
    ACTIONS = []

_WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cassandra_weights.json')

_CARD_IDX_LOCAL = {n: i for i, n in enumerate(CARD_NAMES)}

# Map action type to implied card (for nope context)
_ACTION_CARD = {}
if _HAS_TRAINING:
    _ACTION_CARD = {
        ActionType.PLAY_SKIP:           CardType.SKIP,
        ActionType.PLAY_ATTACK:         CardType.ATTACK,
        ActionType.PLAY_SHUFFLE:        CardType.SHUFFLE,
        ActionType.PLAY_SEE_THE_FUTURE: CardType.SEE_THE_FUTURE,
        ActionType.PLAY_FAVOR:          CardType.FAVOR,
        ActionType.PLAY_NOPE:           CardType.NOPE,
    }


def _load():
    try:
        with open(_WEIGHTS_PATH) as f:
            w = json.load(f)
        required = ('Wz','Uz','bz','Wr','Ur','br','Wn','Un','bn',
                    'W1','b1','W2','b2','W3','b3',
                    'Wtgt','btgt','Wnope1','bnope1','Wnope2','bnope2',
                    'Wgive','bgive','Wplace','bplace')
        if not all(k in w for k in required):
            return None
        if _HAS_NP:
            return {k: _np.array(v, dtype=_np.float32) for k, v in w.items()}
        return w
    except (OSError, ValueError):
        return None


# ---- NumPy fast path ----

def _np_sigmoid(x):
    return 1.0 / (1.0 + _np.exp(-_np.clip(x, -20.0, 20.0)))

def _np_gru_step(x, h, w):
    z = _np_sigmoid(w['Wz'] @ x + w['Uz'] @ h + w['bz'])
    r = _np_sigmoid(w['Wr'] @ x + w['Ur'] @ h + w['br'])
    n = _np.tanh(w['Wn'] @ x + w['Un'] @ (r * h) + w['bn'])
    return (1.0 - z) * h + z * n

def _np_trunk(h, snap, w):
    x  = _np.concatenate([h, snap])
    a1 = _np.maximum(w['W1'] @ x + w['b1'], 0.0)
    return _np.maximum(w['W2'] @ a1 + w['b2'], 0.0)

def _np_policy(a2, w):
    return w['W3'] @ a2 + w['b3']

def _np_target(a2, w):
    return w['Wtgt'] @ a2 + w['btgt']

def _np_give(a2, w):
    return w['Wgive'] @ a2 + w['bgive']

def _np_place(a2, parity, w):
    ext = _np.append(a2, float(parity))
    v   = w['Wplace'] @ ext + w['bplace']
    e   = _np.exp(v - v.max()); return e / e.sum()

def _np_nope_prob(a2, nope_ctx, w):
    ext = _np.concatenate([a2, nope_ctx])
    h1  = _np.maximum(w['Wnope1'] @ ext + w['bnope1'], 0.0)
    return float(_np_sigmoid(w['Wnope2'] @ h1 + w['bnope2'])[0])

def _np_masked_argmax(scores, mask):
    masked = _np.where(_np.array(mask) > 0, scores, -1e9)
    idx = int(_np.argmax(masked))
    return idx if mask[idx] else None


# ---- Pure-Python fallback ----

def _mv(W, v):    return [sum(w * vi for w, vi in zip(row, v)) for row in W]
def _add(a, b):   return [x + y for x, y in zip(a, b)]
def _sigmoid_v(v): return [1.0/(1.0+math.exp(-max(-20.0,min(20.0,x)))) for x in v]
def _tanh_v(v):   return [math.tanh(x) for x in v]
def _relu(v):     return [max(0.0, x) for x in v]
def _softmax(v):
    m = max(v); e = [math.exp(x-m) for x in v]; s = sum(e); return [x/s for x in e]

def _masked_argmax(scores, mask):
    best_i, best_v = None, None
    for i, (s, m) in enumerate(zip(scores, mask)):
        if m and (best_v is None or s > best_v):
            best_i, best_v = i, s
    return best_i

def _gru_step(x, h, w):
    z  = _sigmoid_v(_add(_add(_mv(w['Wz'], x), _mv(w['Uz'], h)), w['bz']))
    r  = _sigmoid_v(_add(_add(_mv(w['Wr'], x), _mv(w['Ur'], h)), w['br']))
    rh = [ri*hi for ri,hi in zip(r, h)]
    n  = _tanh_v(_add(_add(_mv(w['Wn'], x), _mv(w['Un'], rh)), w['bn']))
    return [(1.0-zi)*hi+zi*ni for zi,hi,ni in zip(z,h,n)]

def _trunk(h, snap, w):
    x  = list(h) + list(snap)
    a1 = _relu(_add(_mv(w['W1'], x), w['b1']))
    return _relu(_add(_mv(w['W2'], a1), w['b2']))

def _policy(a2, w):        return _add(_mv(w['W3'], a2), w['b3'])
def _target_scores(a2, w): return _add(_mv(w['Wtgt'], a2), w['btgt'])
def _give_scores(a2, w):   return _add(_mv(w['Wgive'], a2), w['bgive'])
def _place_probs(a2, parity, w):
    ext = list(a2) + [float(parity)]
    return _softmax(_add(_mv(w['Wplace'], ext), w['bplace']))

def _nope_prob(a2, nope_ctx, w):
    ext = list(a2) + list(nope_ctx)
    h1  = _relu(_add(_mv(w['Wnope1'], ext), w['bnope1']))
    return _sigmoid_v([_add(_mv(w['Wnope2'], h1), w['bnope2'])[0]])[0]


def _make_nope_ctx(action, my_id, currently_noped):
    """Build 24-dim nope context for inference."""
    at_oh = [0.0] * 8
    if _HAS_TRAINING and ACTIONS:
        try: at_oh[ACTIONS.index(action.action_type)] = 1.0
        except (ValueError, AttributeError): pass

    card = (getattr(action, 'named_card', None) or
            getattr(action, 'cat_type', None) or
            _ACTION_CARD.get(getattr(action, 'action_type', None)))
    c_oh = [0.0] * N_CARD_SLOTS
    if card is not None and hasattr(card, 'name') and card.name in _CARD_IDX_LOCAL:
        c_oh[_CARD_IDX_LOCAL[card.name]] = 1.0
    else:
        c_oh[N_CARD_SLOTS - 1] = 1.0

    targets_me = [1.0 if getattr(action, 'target_player', None) == my_id else 0.0]
    return at_oh + c_oh + targets_me + [float(currently_noped)]  # 8+14+1+1=24


class CassandraAgent(Agent):
    ARENA = {
        'name': 'Cassandra', 'emoji': '🔮', 'color': '#6b21a8',
        'blurb': 'Saw the fall of Troy but was cursed never to be believed.',
        'stats_version': 1,
    }

    _WEIGHTS = _load()

    def __init__(self, name='Cassandra', seed=None):
        self.name = name
        self._h = [0.0] * GRU_H
        self._last_eid = -1
        self._top = None; self._top_deck = -1
        self._opp_defuses_used = {}
        self._pending_give = None

    def game_start(self, state):
        self._h = _np.zeros(GRU_H, dtype=_np.float32) if _HAS_NP else [0.0] * GRU_H
        self._last_eid = -1
        self._top = None; self._top_deck = -1
        self._opp_defuses_used = {}
        self._pending_give = None

    def see_future(self, state, top3):
        self._top = [c.card_type for c in top3]

    def _known_list(self):
        return self._top if self._top else None

    def _absorb(self, state):
        if self._WEIGHTS is None:
            return
        new = sorted([e for e in state.recent_events
                      if e.get('event_id', 0) > self._last_eid],
                     key=lambda e: e.get('event_id', 0))
        for ev in new:
            t = ev.get('type')
            # Maintain STF window: shift on any draw, invalidate on shuffle/defuse
            if t == 'draw' and self._top:
                self._top = self._top[1:] or None
            elif t in ('shuffle', 'defuse'):
                self._top = None
            if t == 'defuse':
                p = ev.get('player')
                if p is not None and p != state.my_id:
                    self._opp_defuses_used[p] = self._opp_defuses_used.get(p, 0) + 1
            if (self._pending_give and
                    t in ('favor', 'cat_steal') and
                    ev.get('from_player') == state.my_id):
                ev = dict(ev, card_given=self._pending_give)
                self._pending_give = None
            vec = encode_event(ev, state.my_id) if _HAS_TRAINING else [0.0] * 56
            if _HAS_NP:
                self._h = _np_gru_step(_np.array(vec, dtype=_np.float32), self._h, self._WEIGHTS)
            else:
                self._h = _gru_step(vec, self._h, self._WEIGHTS)
            self._last_eid = ev.get('event_id', self._last_eid)

    def _snap(self, state):
        if _HAS_TRAINING:
            return snap_encode(state, self._known_list(), self._opp_defuses_used,
                               ek_count=state.deck_exploding_kittens_count)
        return [0.0] * 97

    def _a2(self, state):
        snap = self._snap(state)
        if _HAS_NP:
            return _np_trunk(self._h, _np.array(snap, dtype=_np.float32), self._WEIGHTS)
        return _trunk(self._h, snap, self._WEIGHTS)

    def choose_action(self, state, valid_actions):
        if self._WEIGHTS is None:
            return Action(ActionType.DRAW)
        self._absorb(state)
        a2 = self._a2(state)
        by = {}
        for a in valid_actions:
            by.setdefault(a.action_type, []).append(a)
        mask = [1.0 if at in by else 0.0 for at in ACTIONS] if ACTIONS else []
        if _HAS_NP and ACTIONS:
            logits = _np_policy(a2, self._WEIGHTS)
            idx = _np_masked_argmax(logits, mask)
        elif ACTIONS:
            logits = _policy(a2, self._WEIGHTS)
            idx = _masked_argmax(logits, mask)
        else:
            return Action(ActionType.DRAW)
        if idx is None:
            return Action(ActionType.DRAW)
        at   = ACTIONS[idx]
        acts = by.get(at) or [Action(ActionType.DRAW)]

        if at in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
            if _HAS_NP:
                tgt_scores = _np_target(a2, self._WEIGHTS)
            else:
                tgt_scores = _target_scores(a2, self._WEIGHTS)
            tgt_by_rel = {}
            for a in acts:
                if a.target_player is not None:
                    tgt_by_rel[(a.target_player - state.my_id) % N_TARGETS] = a
            tgt_mask = [1.0 if r in tgt_by_rel else 0.0 for r in range(N_TARGETS)]
            best_rel = (_np_masked_argmax(tgt_scores, tgt_mask) if _HAS_NP
                        else _masked_argmax(tgt_scores, tgt_mask))
            chosen = tgt_by_rel.get(best_rel, acts[0])
            if at == ActionType.PLAY_CAT_TRIPLE:
                from dataclasses import replace
                chosen = replace(chosen, named_card=CardType.DEFUSE)
            return chosen

        return acts[0]

    def want_to_nope(self, state, action, currently_noped=False):
        if self._WEIGHTS is None:
            return False
        self._absorb(state)
        a2 = self._a2(state)
        ctx = _make_nope_ctx(action, state.my_id, currently_noped)
        if _HAS_NP:
            prob = _np_nope_prob(a2, _np.array(ctx, dtype=_np.float32), self._WEIGHTS)
        else:
            prob = _nope_prob(a2, ctx, self._WEIGHTS)
        return prob > 0.5

    def give_card(self, state, requester_id):
        if self._WEIGHTS is None or not state.my_hand:
            return state.my_hand[0].card_type if state.my_hand else CardType.DEFUSE
        self._absorb(state)
        a2 = self._a2(state)
        if _HAS_NP:
            scores = _np_give(a2, self._WEIGHTS)
        else:
            scores = _give_scores(a2, self._WEIGHTS)
        hand_names = {c.card_type.name for c in state.my_hand}
        mask = [1.0 if n in hand_names else 0.0 for n in CARD_NAMES]
        idx = (_np_masked_argmax(scores, mask) if _HAS_NP else _masked_argmax(scores, mask))
        if idx is None:
            return state.my_hand[0].card_type
        try:
            ct = CardType[CARD_NAMES[idx]]
        except KeyError:
            ct = state.my_hand[0].card_type
        self._pending_give = ct.name
        return ct

    def place_exploding_kitten(self, state, deck_size):
        if self._WEIGHTS is None:
            return 0
        self._absorb(state)
        a2     = self._a2(state)
        parity = deck_size % 2
        if _HAS_NP:
            probs  = _np_place(a2, parity, self._WEIGHTS)
            bucket = int(_np.argmax(probs))
        else:
            probs  = _place_probs(a2, parity, self._WEIGHTS)
            bucket = probs.index(max(probs))
        return min(deck_size, round(BUCKET_FRACS[bucket] * deck_size))
