"""Rollout workers for Cassandra ian_folder.

Cassandra trains to NOT WIN (same goal as Orpheus), but with a richer architecture:
- Nope head receives full action context so it can selectively nope
- Place head receives deck parity so it can use parity strategy in 2-player endgame
- Policy head can learn to use SEE THE FUTURE for bomb intel before drawing
- Event stream tracks card_given in favor/steal events

Fleet: 70% pure loser games (Ian-heavy) + 30% mixed with best winners (Rhino/Elephant).
"""
import numpy as np

from agents.gabriel_agent import GabrielAgent
from agents.perdition2_agent import Perdition2Agent
from agents.ian1_agent import Ian1Agent
from agents.ian2_agent import Ian2Agent
from agents.ian3_agent import Ian3Agent
from agents.elephant_agent import ElephantAgent
from agents.rhino_agent import RhinoAgent
from agents.coyote_agent import CoyoteAgent

from agents.orangutan_features import ACTIONS, N_ACTIONS
from training.cassandra.event_encode import encode_event, N_EVENT, CARD_NAMES, _CARD_IDX, N_CARD_SLOTS
from training.cassandra.features import encode as snap_encode, N_SNAP
from training.cassandra.net import (CassandraNet, GRU_H, N_TARGETS, N_CARD_TYPES, N_BUCKETS,
                                     BUCKET_FRACS, NOPE_CTX_DIM, NOPE_HID, PLACE_CTX, H2)
from game.engine import GameEngine
from game.actions import Action, ActionType
from game.cards import CardType

DEF = CardType.DEFUSE
NEG = -1e9

LOSER_FLEET = [Ian1Agent, Ian1Agent, Ian1Agent,
               Ian2Agent, Ian2Agent, Ian2Agent,
               Ian3Agent, Ian3Agent,
               Perdition2Agent, Perdition2Agent,
               GabrielAgent]

WINNER_FLEET = [RhinoAgent, RhinoAgent, RhinoAgent,
                ElephantAgent, ElephantAgent,
                CoyoteAgent]

FLEET      = LOSER_FLEET   # used for evaluation
MIXED_PROB = 0.30          # fraction of games with 2 winner opponents

# Map action type to the card it implies (for nope context encoding)
_ACTION_CARD = {
    ActionType.PLAY_SKIP:           CardType.SKIP,
    ActionType.PLAY_ATTACK:         CardType.ATTACK,
    ActionType.PLAY_SHUFFLE:        CardType.SHUFFLE,
    ActionType.PLAY_SEE_THE_FUTURE: CardType.SEE_THE_FUTURE,
    ActionType.PLAY_FAVOR:          CardType.FAVOR,
    ActionType.PLAY_NOPE:           CardType.NOPE,
}


def _encode_nope_ctx(action, my_id, currently_noped):
    """Encode nope decision context into 24-dim vector."""
    at_oh = [0.0] * N_ACTIONS
    try:
        at_oh[ACTIONS.index(action.action_type)] = 1.0
    except (ValueError, AttributeError):
        pass

    card = (getattr(action, 'named_card', None) or
            getattr(action, 'cat_type', None) or
            _ACTION_CARD.get(getattr(action, 'action_type', None)))
    c_oh = [0.0] * N_CARD_SLOTS
    if card is not None and hasattr(card, 'name') and card.name in _CARD_IDX:
        c_oh[_CARD_IDX[card.name]] = 1.0
    else:
        c_oh[N_CARD_SLOTS - 1] = 1.0  # none slot

    target = getattr(action, 'target_player', None)
    targets_me = [1.0 if target == my_id else 0.0]
    noped_flag = [float(currently_noped)]

    return np.array(at_oh + c_oh + targets_me + noped_flag, dtype=np.float32)  # 24 dims


def _np(w):
    return {k: np.array(v, dtype=np.float32) for k, v in w.items()}


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20.0, 20.0)))


def _gru_step(x, h, p):
    z = _sigmoid(p['Wz'] @ x + p['Uz'] @ h + p['bz'])
    r = _sigmoid(p['Wr'] @ x + p['Ur'] @ h + p['br'])
    n = np.tanh(p['Wn'] @ x + p['Un'] @ (r * h) + p['bn'])
    return (1.0 - z) * h + z * n


def _trunk(h, snap, p):
    x  = np.concatenate([h, snap])
    a1 = np.maximum(p['W1'] @ x + p['b1'], 0.0)
    return np.maximum(p['W2'] @ a1 + p['b2'], 0.0)


def _policy(a2, p):
    return p['W3'] @ a2 + p['b3'], float((p['Wv'] @ a2 + p['bv'])[0]) if 'Wv' in p else 0.0


def _target_logits(a2, p):
    return p['Wtgt'] @ a2 + p['btgt']


def _nope_prob(a2, nope_ctx, p):
    ext = np.concatenate([a2, nope_ctx])
    h1  = np.maximum(p['Wnope1'] @ ext + p['bnope1'], 0.0)
    return float(_sigmoid(p['Wnope2'] @ h1 + p['bnope2'])[0])


def _give_logits(a2, p):
    return p['Wgive'] @ a2 + p['bgive']


def _place_logits(a2, deck_parity, p):
    ext = np.append(a2, float(deck_parity))
    return p['Wplace'] @ ext + p['bplace']


def _masked_probs(logits, mask):
    z = np.where(mask > 0, logits, NEG); z -= z.max()
    e = np.exp(z) * mask
    return e / (e.sum() + 1e-12)


def _softmax(v):
    e = np.exp(v - v.max()); return e / e.sum()


class _LearnerAgent:
    """Stateful learner — forward passes through Cassandra's architecture."""
    PARAMS = None; RNG = None; GREEDY = False
    EVENT_LOG = None; STEP_LOG = None
    NOPE_LOG = None; GIVE_LOG = None; PLACE_LOG = None

    def __init__(self, name='Cassandra'):
        self.name = name
        self._h = np.zeros(GRU_H, dtype=np.float32)
        self._last_eid = -1
        self._top = None; self._top_deck = -1
        self._opp_defuses_used = {}
        self._pending_give = None

    def game_start(self, state):
        self._h = np.zeros(GRU_H, dtype=np.float32)
        self._last_eid = -1
        self._top = None; self._top_deck = -1
        self._opp_defuses_used = {}
        self._pending_give = None

    def see_future(self, state, top3):
        self._top = [c.card_type for c in top3]

    def _known_list(self):
        return self._top if self._top else None

    def _absorb(self, state):
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
            # Track opponent defuse usage
            if t == 'defuse':
                p = ev.get('player')
                if p is not None and p != state.my_id:
                    self._opp_defuses_used[p] = self._opp_defuses_used.get(p, 0) + 1
            # Inject card_given when we were the one giving (favor/cat_steal from us)
            if (self._pending_give and
                    t in ('favor', 'cat_steal') and
                    ev.get('from_player') == state.my_id):
                ev = dict(ev, card_given=self._pending_give)
                self._pending_give = None
            vec = np.array(encode_event(ev, state.my_id), dtype=np.float32)
            if self.EVENT_LOG is not None:
                self.EVENT_LOG.append(vec)
            self._h = _gru_step(vec, self._h, self.PARAMS)
            self._last_eid = ev.get('event_id', self._last_eid)

    def _snap(self, state):
        return np.array(snap_encode(state, self._known_list(), self._opp_defuses_used,
                                    ek_count=state.deck_exploding_kittens_count),
                        dtype=np.float32)

    def _ec(self):
        return len(self.EVENT_LOG) if self.EVENT_LOG is not None else 0

    def choose_action(self, state, valid_actions):
        self._absorb(state)
        p = self.PARAMS
        snap = self._snap(state)
        a2   = _trunk(self._h, snap, p)
        logits, value = _policy(a2, p)

        by = {}
        for a in valid_actions:
            by.setdefault(a.action_type, []).append(a)
        mask = np.array([1.0 if at in by else 0.0 for at in ACTIONS])
        probs = _masked_probs(logits, mask)
        idx = int(np.argmax(probs)) if self.GREEDY else int(self.RNG.choice(N_ACTIONS, p=probs))
        at  = ACTIONS[idx]

        acts = by.get(at) or [Action(ActionType.DRAW)]
        chosen = acts[0]
        has_target = False; tgt_mask = None; tgt_action = None; tgt_logp = None

        if at in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
            has_target = True
            tgt_mask_arr = np.zeros(N_TARGETS)
            act_by_rel = {}
            for a in acts:
                if a.target_player is not None:
                    rel = (a.target_player - state.my_id) % N_TARGETS
                    tgt_mask_arr[rel] = 1.0
                    act_by_rel[rel] = a
            tgt_logits = _target_logits(a2, p)
            tgt_probs  = _masked_probs(tgt_logits, tgt_mask_arr)
            if self.GREEDY:
                tgt_rel = int(np.argmax(tgt_probs))
            else:
                valid_rels = [i for i in range(N_TARGETS) if tgt_mask_arr[i] > 0]
                tgt_rel = int(self.RNG.choice(valid_rels,
                              p=tgt_probs[valid_rels] / tgt_probs[valid_rels].sum()))
            chosen = act_by_rel.get(tgt_rel, acts[0])
            tgt_mask = tgt_mask_arr.tolist()
            tgt_action = tgt_rel
            tgt_logp   = float(np.log(tgt_probs[tgt_rel] + 1e-12))
            if at == ActionType.PLAY_CAT_TRIPLE:
                from dataclasses import replace
                chosen = replace(chosen, named_card=DEF)

        if self.STEP_LOG is not None:
            self.STEP_LOG.append({
                'event_count':  self._ec(),
                'snapshot':     snap.tolist(),
                'mask':         mask.tolist(),
                'action':       idx,
                'old_logp':     float(np.log(probs[idx] + 1e-12)),
                'old_value':    value,
                'has_target':   has_target,
                'target_mask':  tgt_mask,
                'target_action': tgt_action,
                'target_logp':  tgt_logp,
            })

        return chosen

    def want_to_nope(self, state, action, currently_noped=False):
        self._absorb(state)
        snap = self._snap(state)
        a2   = _trunk(self._h, snap, self.PARAMS)
        nope_ctx = _encode_nope_ctx(action, state.my_id, currently_noped)
        prob  = _nope_prob(a2, nope_ctx, self.PARAMS)
        decision = bool(self.RNG.random() < prob) if not self.GREEDY else (prob > 0.5)
        logp  = float(np.log(prob + 1e-12) if decision else np.log(1.0 - prob + 1e-12))
        _, value = _policy(a2, self.PARAMS)
        if self.NOPE_LOG is not None:
            self.NOPE_LOG.append({
                'event_count':    self._ec(),
                'snapshot':       snap.tolist(),
                'nope_ctx':       nope_ctx.tolist(),  # NEW: action context
                'decision':       int(decision),
                'old_logp':       logp,
                'old_value':      value,
            })
        return decision

    def give_card(self, state, requester_id):
        self._absorb(state)
        snap = self._snap(state)
        a2   = _trunk(self._h, snap, self.PARAMS)
        logits    = _give_logits(a2, self.PARAMS)
        hand_names = {c.card_type.name for c in state.my_hand}
        card_mask  = np.array([1.0 if n in hand_names else 0.0 for n in CARD_NAMES])
        probs = _masked_probs(logits, card_mask)
        if self.GREEDY:
            chosen_idx = int(np.argmax(probs))
        else:
            valid = np.where(card_mask > 0)[0]
            chosen_idx = int(self.RNG.choice(valid, p=probs[valid] / probs[valid].sum()))
        _, value = _policy(a2, self.PARAMS)
        if self.GIVE_LOG is not None:
            self.GIVE_LOG.append({
                'event_count': self._ec(),
                'snapshot':    snap.tolist(),
                'card_mask':   card_mask.tolist(),
                'decision':    chosen_idx,
                'old_logp':    float(np.log(probs[chosen_idx] + 1e-12)),
                'old_value':   value,
            })
        try:
            ct = CardType[CARD_NAMES[chosen_idx]]
        except (KeyError, IndexError):
            ct = state.my_hand[0].card_type
        self._pending_give = ct.name
        return ct

    def place_exploding_kitten(self, state, deck_size):
        self._absorb(state)
        snap = self._snap(state)
        a2   = _trunk(self._h, snap, self.PARAMS)
        parity   = deck_size % 2
        logits   = _place_logits(a2, parity, self.PARAMS)
        probs    = _softmax(logits)
        if self.GREEDY:
            bucket = int(np.argmax(probs))
        else:
            bucket = int(self.RNG.choice(N_BUCKETS, p=probs))
        _, value = _policy(a2, self.PARAMS)
        if self.PLACE_LOG is not None:
            self.PLACE_LOG.append({
                'event_count': self._ec(),
                'snapshot':    snap.tolist(),
                'deck_size':   deck_size,
                'deck_parity': parity,   # NEW
                'decision':    bucket,
                'old_logp':    float(np.log(probs[bucket] + 1e-12)),
                'old_value':   value,
            })
        return min(deck_size, round(BUCKET_FRACS[bucket] * deck_size))


def play_one(policy_w, pool_w, rng, npr, self_prob=0.3):
    p    = _np(policy_w)
    pool = [_np(w) for w in pool_w]
    ev_log, step_log, nope_log, give_log, place_log = [], [], [], [], []

    class Learner(_LearnerAgent):
        PARAMS = p; RNG = npr; GREEDY = False
        EVENT_LOG = ev_log; STEP_LOG = step_log
        NOPE_LOG = nope_log; GIVE_LOG = give_log; PLACE_LOG = place_log

    opponents = []
    mixed_game = rng.random() < MIXED_PROB
    for i in range(4):
        if pool and rng.random() < self_prob:
            pp = rng.choice(pool)
            class Frozen(_LearnerAgent):
                PARAMS = pp; RNG = npr; GREEDY = rng.random() < 0.8
                EVENT_LOG = None; STEP_LOG = None
                NOPE_LOG  = None; GIVE_LOG = None; PLACE_LOG = None
            opponents.append(Frozen(name='self'))
        else:
            src = WINNER_FLEET if (mixed_game and i >= 2) else LOSER_FLEET
            opp = rng.choice(src)(name='fleet')
            opp._play_mode = True
            opponents.append(opp)

    agents = [Learner(name='Cassandra')] + opponents
    order  = list(range(5)); rng.shuffle(order)
    seat   = order.index(0)
    r = GameEngine([agents[i] for i in order], collect_events=True).play_game(5)

    if r['winner'] < 0 or not step_log:
        return None, 0.0

    reward = 0.0 if r['winner'] == seat else 1.0
    return {
        'event_vecs':  [v.tolist() for v in ev_log],
        'steps':       step_log,
        'nope_steps':  nope_log,
        'give_steps':  give_log,
        'place_steps': place_log,
    }, reward


def rollout_worker(args):
    policy_w, pool_w, n_games, seed, self_prob = args
    import random as _random
    rng = _random.Random(seed); npr = np.random.default_rng(seed)
    out = []
    for _ in range(n_games):
        gd, rew = play_one(policy_w, pool_w, rng, npr, self_prob)
        if gd is not None:
            out.append((gd, rew))
    return out


def _evaluate_chunk(args):
    policy_w, n, seed = args
    import random as _random
    p   = _np(policy_w); rng = _random.Random(seed); npr = np.random.default_rng(seed)

    class Greedy(_LearnerAgent):
        PARAMS = p; RNG = npr; GREEDY = True
        EVENT_LOG = None; STEP_LOG = None
        NOPE_LOG  = None; GIVE_LOG = None; PLACE_LOG = None

    losses = 0; games = 0
    for _ in range(n):
        me = Greedy(name='Cassandra')
        opps = [rng.choice(FLEET)(name='fleet') for _ in range(4)]
        for opp in opps:
            opp._play_mode = True
        agents = [me] + opps
        order = list(range(5)); rng.shuffle(order); seat = order.index(0)
        r = GameEngine([agents[i] for i in order], collect_events=True).play_game(5)
        if r['winner'] < 0: continue
        games += 1
        if r['winner'] != seat:
            losses += 1
    return losses, games


def evaluate(policy_w, n=2000, seed=99, ex=None):
    if ex is None:
        losses, games = _evaluate_chunk((policy_w, n, seed))
    else:
        import math
        workers = ex._max_workers
        chunk = math.ceil(n / workers)
        futs = [ex.submit(_evaluate_chunk, (policy_w, chunk, seed + i))
                for i in range(workers)]
        losses = games = 0
        for f in futs:
            l, g = f.result(); losses += l; games += g
    return losses / games if games else 0.0
