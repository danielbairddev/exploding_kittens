"""Rollout workers for Rhino self-play.

All decisions — action type, target, want_to_nope, give_card, place_kitten —
are made by the learned policy and logged for PPO training.
"""
import numpy as np

from agents.coyote_agent import CoyoteAgent
from agents.survival_agent import SurvivalAgent
from agents.survival_agent_v2 import SurvivalAgentV2
from agents.aggressive_agent import AggressiveAgent
from agents.heuristic_agent import HeuristicAgent
from agents.ian1_agent import Ian1Agent
from agents.ian2_agent import Ian2Agent
from agents.orangutan_features import encode as snap_encode, ACTIONS, N_ACTIONS
from rhino.event_encode import encode_event, N_EVENT, CARD_NAMES, _CARD_IDX
from rhino.net import (GRU_H, N_TARGETS, N_CARD_TYPES, N_BUCKETS, BUCKET_FRACS,
                       POLICY_KEYS)
from game.engine import GameEngine
from game.actions import Action, ActionType
from game.cards import CardType

DEF = CardType.DEFUSE
NEG = -1e9

# Competitive, diverse fleet — no Perdition (tries to lose, corrupts signal),
# no Random/Chaos (pure noise).
FLEET = [CoyoteAgent, SurvivalAgentV2, SurvivalAgent, AggressiveAgent,
         HeuristicAgent, Ian1Agent, Ian2Agent]


def _np(w):
    return {k: np.array(v) for k, v in w.items()}


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20.0, 20.0)))


# ---- Numpy inference helpers (stateless, used in workers) ----

def _gru_step(x, h, p):
    z = _sigmoid(p['Wz'] @ x + p['Uz'] @ h + p['bz'])
    r = _sigmoid(p['Wr'] @ x + p['Ur'] @ h + p['br'])
    n = np.tanh(p['Wn'] @ x + p['Un'] @ (r * h) + p['bn'])
    return (1.0 - z) * h + z * n


def _trunk(h, snap, p):
    x  = np.concatenate([h, snap])
    a1 = np.maximum(p['W1'] @ x + p['b1'], 0.0)
    a2 = np.maximum(p['W2'] @ a1 + p['b2'], 0.0)
    return a2


def _policy(a2, p):
    logits = p['W3'] @ a2 + p['b3']
    value  = float((p['Wv'] @ a2 + p['bv'])[0]) if 'Wv' in p else 0.0
    return logits, value


def _target_logits(a2, p):
    return p['Wtgt'] @ a2 + p['btgt']


def _nope_prob(a2, currently_noped, p):
    ext = np.append(a2, float(currently_noped))
    return float(_sigmoid(p['Wnope'] @ ext + p['bnope'])[0])


def _give_logits(a2, p):
    return p['Wgive'] @ a2 + p['bgive']


def _place_logits(a2, p):
    return p['Wplace'] @ a2 + p['bplace']


def _masked_probs(logits, mask):
    z = np.where(mask > 0, logits, NEG); z -= z.max()
    e = np.exp(z) * mask
    return e / (e.sum() + 1e-12)


def _softmax(logits):
    z = logits - logits.max()
    e = np.exp(z)
    return e / e.sum()


class _LearnerAgent(CoyoteAgent):
    """Fully-ML agent: all decisions go through the learned policy."""
    PARAMS = None; RNG = None; GREEDY = False
    EVENT_LOG = None; STEP_LOG = None
    NOPE_LOG = None; GIVE_LOG = None; PLACE_LOG = None

    def game_start(self, state):
        super().game_start(state)
        self._h = np.zeros(GRU_H)
        self._last_eid = -1

    def _absorb(self, state):
        new = sorted([e for e in state.recent_events
                      if e.get('event_id', 0) > self._last_eid],
                     key=lambda e: e.get('event_id', 0))
        for ev in new:
            vec = encode_event(ev, state.my_id)
            if self.EVENT_LOG is not None:
                self.EVENT_LOG.append(vec)
            self._h = _gru_step(vec, self._h, self.PARAMS)
            self._last_eid = ev.get('event_id', self._last_eid)

    def _ec(self):
        return len(self.EVENT_LOG) if self.EVENT_LOG is not None else 0

    def choose_action(self, state, valid_actions):
        self._absorb(state)
        p = self.PARAMS
        snap = np.array(snap_encode(state, self._known_list(state)))
        a2 = _trunk(self._h, snap, p)
        logits, value = _policy(a2, p)

        by = {}
        for a in valid_actions:
            by.setdefault(a.action_type, []).append(a)
        mask = np.array([1.0 if at in by else 0.0 for at in ACTIONS])
        probs = _masked_probs(logits, mask)
        idx = int(np.argmax(probs)) if self.GREEDY else int(self.RNG.choice(N_ACTIONS, p=probs))
        at = ACTIONS[idx]

        # Target selection
        acts = by.get(at) or [Action(ActionType.DRAW)]
        chosen = acts[0]
        has_target = False; tgt_mask = None; tgt_action = None; tgt_logp = None

        if at in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
            has_target = True
            # Build relative-position mask over valid targets
            tgt_mask_arr = np.zeros(N_TARGETS)
            act_by_rel = {}
            for a in acts:
                if a.target_player is not None:
                    rel = (a.target_player - state.my_id) % N_TARGETS
                    tgt_mask_arr[rel] = 1.0
                    act_by_rel[rel] = a
            tgt_logits = _target_logits(a2, p)
            tgt_probs = _masked_probs(tgt_logits, tgt_mask_arr)
            if self.GREEDY:
                tgt_rel = int(np.argmax(tgt_probs))
            else:
                valid_rels = [i for i in range(N_TARGETS) if tgt_mask_arr[i] > 0]
                tgt_rel = int(self.RNG.choice(valid_rels,
                              p=tgt_probs[valid_rels] / tgt_probs[valid_rels].sum()))
            chosen = act_by_rel.get(tgt_rel, acts[0])
            tgt_mask = tgt_mask_arr.tolist()
            tgt_action = tgt_rel
            tgt_logp = float(np.log(tgt_probs[tgt_rel] + 1e-12))

            if at == ActionType.PLAY_CAT_TRIPLE:
                from dataclasses import replace
                chosen = replace(chosen, named_card=DEF)

        if self.STEP_LOG is not None:
            self.STEP_LOG.append({
                'event_count': self._ec(),
                'snapshot': snap.tolist(),
                'mask': mask.tolist(),
                'action': idx,
                'old_logp': float(np.log(probs[idx] + 1e-12)),
                'old_value': value,
                'has_target': has_target,
                'target_mask': tgt_mask,
                'target_action': tgt_action,
                'target_logp': tgt_logp,
            })

        return chosen

    def want_to_nope(self, state, action, currently_noped=False):
        if self.PARAMS is None:
            return False
        self._absorb(state)
        snap = np.array(snap_encode(state, self._known_list(state)))
        a2 = _trunk(self._h, snap, self.PARAMS)
        prob = _nope_prob(a2, currently_noped, self.PARAMS)
        decision = bool(self.RNG.random() < prob) if not self.GREEDY else (prob > 0.5)
        logp = float(np.log(prob + 1e-12) if decision else np.log(1.0 - prob + 1e-12))
        _, value = _policy(a2, self.PARAMS)
        if self.NOPE_LOG is not None:
            self.NOPE_LOG.append({
                'event_count': self._ec(),
                'snapshot': snap.tolist(),
                'currently_noped': int(currently_noped),
                'decision': int(decision),
                'old_logp': logp,
                'old_value': value,
            })
        return decision

    def give_card(self, state, requester_id):
        if self.PARAMS is None:
            return state.my_hand[0].card_type
        self._absorb(state)
        snap = np.array(snap_encode(state, self._known_list(state)))
        a2 = _trunk(self._h, snap, self.PARAMS)
        logits = _give_logits(a2, self.PARAMS)
        # mask to card types present in hand
        hand_names = {c.card_type.name for c in state.my_hand}
        card_mask = np.array([1.0 if name in hand_names else 0.0
                              for name in CARD_NAMES])
        probs = _masked_probs(logits, card_mask)
        if self.GREEDY:
            chosen_idx = int(np.argmax(probs))
        else:
            valid = np.where(card_mask > 0)[0]
            chosen_idx = int(self.RNG.choice(valid,
                             p=probs[valid] / probs[valid].sum()))
        _, value = _policy(a2, self.PARAMS)
        if self.GIVE_LOG is not None:
            self.GIVE_LOG.append({
                'event_count': self._ec(),
                'snapshot': snap.tolist(),
                'card_mask': card_mask.tolist(),
                'decision': chosen_idx,
                'old_logp': float(np.log(probs[chosen_idx] + 1e-12)),
                'old_value': value,
            })
        try:
            return CardType[CARD_NAMES[chosen_idx]]
        except (KeyError, IndexError):
            return state.my_hand[0].card_type

    def place_exploding_kitten(self, state, deck_size):
        if self.PARAMS is None:
            return 0
        snap = np.array(snap_encode(state, self._known_list(state)))
        a2 = _trunk(self._h, snap, self.PARAMS)
        logits = _place_logits(a2, self.PARAMS)
        probs = _softmax(logits)
        if self.GREEDY:
            bucket = int(np.argmax(probs))
        else:
            bucket = int(self.RNG.choice(N_BUCKETS, p=probs))
        _, value = _policy(a2, self.PARAMS)
        if self.PLACE_LOG is not None:
            self.PLACE_LOG.append({
                'event_count': self._ec(),
                'snapshot': snap.tolist(),
                'deck_size': deck_size,
                'decision': bucket,
                'old_logp': float(np.log(probs[bucket] + 1e-12)),
                'old_value': value,
            })
        return min(deck_size, round(BUCKET_FRACS[bucket] * deck_size))


def play_one(policy_w, pool_w, rng, npr, self_prob=0.5):
    p = _np(policy_w)
    pool = [_np(w) for w in pool_w]
    ev_log, step_log, nope_log, give_log, place_log = [], [], [], [], []

    class Learner(_LearnerAgent):
        PARAMS = p; RNG = npr; GREEDY = False
        EVENT_LOG = ev_log; STEP_LOG = step_log
        NOPE_LOG = nope_log; GIVE_LOG = give_log; PLACE_LOG = place_log

    opponents = []
    for _ in range(4):
        if pool and rng.random() < self_prob:
            pp = rng.choice(pool)
            class Frozen(_LearnerAgent):
                PARAMS = pp; RNG = npr; GREEDY = rng.random() < 0.8
                EVENT_LOG = None; STEP_LOG = None
                NOPE_LOG  = None; GIVE_LOG = None; PLACE_LOG = None
            opponents.append(Frozen(name='self'))
        else:
            opponents.append(rng.choice(FLEET)(name='fleet'))

    agents = [Learner(name='Rhino')] + opponents
    order = list(range(5)); rng.shuffle(order)
    seat = order.index(0)
    r = GameEngine([agents[i] for i in order], collect_events=True).play_game(5)

    if r['winner'] < 0 or not step_log:
        return None, 0.0

    deaths = [e['player'] for e in r['events'] if e['type'] == 'explode']
    reward = 1.0 if r['winner'] == seat else (-1.0 if seat in deaths else 0.0)
    return {
        'event_vecs': [v.tolist() for v in ev_log],
        'steps': step_log,
        'nope_steps': nope_log,
        'give_steps': give_log,
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


def evaluate(policy_w, n=2000, seed=99):
    import random as _random
    p = _np(policy_w); rng = _random.Random(seed); npr = np.random.default_rng(seed)

    class Greedy(_LearnerAgent):
        PARAMS = p; RNG = npr; GREEDY = True
        EVENT_LOG = None; STEP_LOG = None
        NOPE_LOG  = None; GIVE_LOG = None; PLACE_LOG = None

    wins = 0; place_sum = 0; games = 0
    for _ in range(n):
        me = Greedy(name='Rhino')
        opps = [c(name=c.__name__) for c in rng.sample(FLEET, 4)]
        agents = [me] + opps
        order = list(range(5)); rng.shuffle(order); seat = order.index(0)
        r = GameEngine([agents[i] for i in order], collect_events=True).play_game(5)
        if r['winner'] < 0: continue
        deaths = [e['player'] for e in r['events'] if e['type'] == 'explode']
        if len(deaths) != 4: continue
        finish = [r['winner']] + list(reversed(deaths))
        place = finish.index(seat) + 1
        games += 1; place_sum += place
        if place == 1: wins += 1
    return (wins / games if games else 0.0), (place_sum / games if games else 0.0)
