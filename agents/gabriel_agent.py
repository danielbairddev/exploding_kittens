"""Gabriel — GRU-128 angel bot trained to die first.

Same architecture as Elephant (GRU(39→128) + Trunk(180→128→64) + 5 heads),
but trained with an inverted reward: glory comes from being the first to explode.
"""
import json, math, os
from agents.base import Agent
from agents.orangutan_features import encode as snap_encode, ACTIONS
from game.actions import Action, ActionType
from game.cards import CardType

try:
    import numpy as _np
    _HAS_NP = True
except ImportError:
    _np = None
    _HAS_NP = False

try:
    from training.rhino.event_encode import CARD_NAMES, N_EVENT
except ImportError:
    CARD_NAMES = ['DEFUSE','ATTACK','SKIP','FAVOR','SHUFFLE','SEE_THE_FUTURE','NOPE',
                  'TACO_CAT','HAIRY_POTATO_CAT','BEARD_CAT','RAINBOW_CAT','CATTERMELON',
                  'EXPLODING_KITTEN']
    N_EVENT = 39

_WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gabriel_weights.json')

_GRU_H     = 128
_N_TARGETS = 5
_N_CARDS   = 13
_N_BUCKETS = 5
_BUCKET_FRACS = [0.0, 0.25, 0.5, 0.75, 1.0]
_CARD_NAMES_LIST = CARD_NAMES


def _load():
    try:
        with open(_WEIGHTS_PATH) as f:
            w = json.load(f)
        required = ('Wz','Uz','bz','Wr','Ur','br','Wn','Un','bn',
                    'W1','b1','W2','b2','W3','b3',
                    'Wtgt','btgt','Wnope','bnope','Wgive','bgive','Wplace','bplace')
        if not all(k in w for k in required):
            return None
        if _HAS_NP:
            return {k: _np.array(v, dtype=_np.float32) for k, v in w.items()}
        return w
    except (OSError, ValueError):
        return None


def _np_sigmoid(x):
    return 1.0 / (1.0 + _np.exp(-_np.clip(x, -20.0, 20.0)))

def _np_gru_step(x, h, w):
    z = _np_sigmoid(w['Wz'] @ x + w['Uz'] @ h + w['bz'])
    r = _np_sigmoid(w['Wr'] @ x + w['Ur'] @ h + w['br'])
    n = _np.tanh(w['Wn'] @ x + w['Un'] @ (r * h) + w['bn'])
    return (1.0 - z) * h + z * n

def _np_trunk(h, snap, w):
    x = _np.concatenate([h, snap])
    a1 = _np.maximum(w['W1'] @ x + w['b1'], 0.0)
    return _np.maximum(w['W2'] @ a1 + w['b2'], 0.0)

def _np_policy(a2, w):       return w['W3'] @ a2 + w['b3']
def _np_target(a2, w):       return w['Wtgt'] @ a2 + w['btgt']
def _np_give(a2, w):         return w['Wgive'] @ a2 + w['bgive']
def _np_place(a2, w):
    v = w['Wplace'] @ a2 + w['bplace']; e = _np.exp(v - v.max())
    return e / e.sum()
def _np_nope_prob(a2, noped, w):
    ext = _np.append(a2, float(noped))
    return float(_np_sigmoid(w['Wnope'] @ ext + w['bnope'])[0])

def _np_masked_argmax(scores, mask):
    masked = _np.where(_np.array(mask) > 0, scores, -1e9)
    idx = int(_np.argmax(masked))
    return idx if mask[idx] else None


def _mv(W, v):
    return [sum(w * vi for w, vi in zip(row, v)) for row in W]

def _add(a, b):
    return [x + y for x, y in zip(a, b)]

def _sigmoid(v):
    return [1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, x)))) for x in v]

def _tanh_v(v):
    return [math.tanh(x) for x in v]

def _relu(v):
    return [max(0.0, x) for x in v]

def _softmax(v):
    m = max(v); e = [math.exp(x - m) for x in v]; s = sum(e)
    return [x / s for x in e]

def _masked_argmax(scores, mask):
    best_i, best_v = None, None
    for i, (s, m) in enumerate(zip(scores, mask)):
        if m and (best_v is None or s > best_v):
            best_i, best_v = i, s
    return best_i

def _gru_step(x, h, w):
    z = _sigmoid(_add(_add(_mv(w['Wz'], x), _mv(w['Uz'], h)), w['bz']))
    r = _sigmoid(_add(_add(_mv(w['Wr'], x), _mv(w['Ur'], h)), w['br']))
    rh = [ri * hi for ri, hi in zip(r, h)]
    n = _tanh_v(_add(_add(_mv(w['Wn'], x), _mv(w['Un'], rh)), w['bn']))
    return [(1.0 - zi) * hi + zi * ni for zi, hi, ni in zip(z, h, n)]

def _trunk(h, snap, w):
    x  = list(h) + list(snap)
    a1 = _relu(_add(_mv(w['W1'], x), w['b1']))
    return _relu(_add(_mv(w['W2'], a1), w['b2']))

def _policy(a2, w):          return _add(_mv(w['W3'], a2), w['b3'])
def _target_scores(a2, w):   return _add(_mv(w['Wtgt'], a2), w['btgt'])
def _give_scores(a2, w):     return _add(_mv(w['Wgive'], a2), w['bgive'])
def _place_probs(a2, w):     return _softmax(_add(_mv(w['Wplace'], a2), w['bplace']))

def _nope_prob(a2, currently_noped, w):
    ext = list(a2) + [float(currently_noped)]
    return _sigmoid([_add(_mv(w['Wnope'], ext), w['bnope'])[0]])[0]


class GabrielAgent(Agent):
    ARENA = {
        'name': 'Gabriel', 'emoji': '⚰️', 'color': '#d4af37',
        'blurb': 'The first angel sounded — and there came hail and fire mixed with blood.',
        'author': 'Daniel Baird', 'llm_assisted': True, 'stats_version': 1,
    }

    _WEIGHTS = _load()

    def __init__(self, name='Gabriel', seed=None):
        self.name = name
        self._h = [0.0] * _GRU_H
        self._last_eid = -1
        self._top = None; self._top_deck = -1

    def game_start(self, state):
        self._h = _np.zeros(_GRU_H, dtype=_np.float32) if _HAS_NP else [0.0] * _GRU_H
        self._last_eid = -1
        self._top = None; self._top_deck = -1

    def see_future(self, state, top3):
        self._top = [c.card_type for c in top3]
        self._top_deck = state.deck_size

    def _known_list(self, state):
        if (self._top is not None and
                state.deck_size == self._top_deck and len(self._top) >= 1):
            return self._top
        return None

    def _absorb(self, state):
        if self._WEIGHTS is None:
            return
        new = sorted([e for e in state.recent_events
                      if e.get('event_id', 0) > self._last_eid],
                     key=lambda e: e.get('event_id', 0))
        from training.rhino.event_encode import encode_event
        for ev in new:
            vec = encode_event(ev, state.my_id)
            if _HAS_NP:
                self._h = _np_gru_step(_np.array(vec, dtype=_np.float32), self._h, self._WEIGHTS)
            else:
                self._h = _gru_step(vec, self._h, self._WEIGHTS)
            self._last_eid = ev.get('event_id', self._last_eid)

    def _snap(self, state):
        return snap_encode(state, self._known_list(state))

    def _a2(self, state):
        if _HAS_NP:
            return _np_trunk(self._h, _np.array(self._snap(state), dtype=_np.float32), self._WEIGHTS)
        return _trunk(self._h, self._snap(state), self._WEIGHTS)

    def choose_action(self, state, valid_actions):
        if self._WEIGHTS is None:
            return Action(ActionType.DRAW)
        self._absorb(state)
        a2 = self._a2(state)
        by = {}
        for a in valid_actions:
            by.setdefault(a.action_type, []).append(a)
        mask = [1.0 if at in by else 0.0 for at in ACTIONS]
        if _HAS_NP:
            logits = _np_policy(a2, self._WEIGHTS)
            idx = _np_masked_argmax(logits, mask)
        else:
            logits = _policy(a2, self._WEIGHTS)
            idx = _masked_argmax(logits, mask)
        if idx is None:
            return Action(ActionType.DRAW)
        at = ACTIONS[idx]
        acts = by.get(at) or [Action(ActionType.DRAW)]

        if at in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
            if _HAS_NP:
                tgt_scores = _np_target(a2, self._WEIGHTS)
            else:
                tgt_scores = _target_scores(a2, self._WEIGHTS)
            tgt_by_rel = {}
            for a in acts:
                if a.target_player is not None:
                    rel = (a.target_player - state.my_id) % _N_TARGETS
                    tgt_by_rel[rel] = a
            tgt_mask = [1.0 if r in tgt_by_rel else 0.0 for r in range(_N_TARGETS)]
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
        prob = (_np_nope_prob(a2, currently_noped, self._WEIGHTS) if _HAS_NP
                else _nope_prob(a2, currently_noped, self._WEIGHTS))
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
        mask = [1.0 if name in hand_names else 0.0 for name in _CARD_NAMES_LIST]
        idx = (_np_masked_argmax(scores, mask) if _HAS_NP else _masked_argmax(scores, mask))
        if idx is None:
            return state.my_hand[0].card_type
        try:
            return CardType[_CARD_NAMES_LIST[idx]]
        except KeyError:
            return state.my_hand[0].card_type

    def place_exploding_kitten(self, state, deck_size):
        if self._WEIGHTS is None:
            return 0
        a2 = self._a2(state)
        if _HAS_NP:
            probs = _np_place(a2, self._WEIGHTS)
            bucket = int(_np.argmax(probs))
        else:
            probs = _place_probs(a2, self._WEIGHTS)
            bucket = probs.index(max(probs))
        return min(deck_size, round(_BUCKET_FRACS[bucket] * deck_size))
