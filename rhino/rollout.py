"""Rollout workers for Rhino self-play.

The learner maintains a GRU hidden state across the game, processing each new
public event as it arrives.  The rollout stores the full event sequence + per-step
data so the training loop can replay it with BPTT.
"""
import numpy as np

from agents.coyote_agent import CoyoteAgent
from agents.survival_agent import SurvivalAgent
from agents.survival_agent_v2 import SurvivalAgentV2
from agents.aggressive_agent import AggressiveAgent
from agents.chaos_agent import ChaosAgent
from agents.heuristic_agent import HeuristicAgent
from agents.random_agent import RandomAgent
from agents.orangutan_features import encode as snap_encode, ACTIONS, N_ACTIONS
from rhino.event_encode import encode_event, N_EVENT
from rhino.net import GRU_H, POLICY_KEYS
from game.engine import GameEngine
from game.actions import Action, ActionType
from game.cards import CardType

DEF = CardType.DEFUSE
NEG = -1e9

FLEET = [CoyoteAgent, SurvivalAgentV2, SurvivalAgent, AggressiveAgent,
         ChaosAgent, HeuristicAgent, RandomAgent]


def _np_params(w):
    return {k: np.array(v) for k, v in w.items()}


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20.0, 20.0)))


def _gru_step(x, h, p):
    z = _sigmoid(p['Wz'] @ x + p['Uz'] @ h + p['bz'])
    r = _sigmoid(p['Wr'] @ x + p['Ur'] @ h + p['br'])
    n = np.tanh(p['Wn'] @ x + p['Un'] @ (r * h) + p['bn'])
    return (1.0 - z) * h + z * n


def _mlp_forward(h, snap, p):
    x = np.concatenate([h, snap])
    a1 = np.maximum(p['W1'] @ x + p['b1'], 0.0)
    a2 = np.maximum(p['W2'] @ a1 + p['b2'], 0.0)
    logits = p['W3'] @ a2 + p['b3']
    value = float((p['Wv'] @ a2 + p['bv'])[0]) if 'Wv' in p else 0.0
    return logits, value


def _masked_probs(logits, mask):
    z = np.where(mask > 0, logits, NEG)
    z -= z.max()
    e = np.exp(z) * mask
    return e / e.sum()


class _LearnerAgent(CoyoteAgent):
    """Stateful learner: maintains GRU hidden state and logs transitions."""
    PARAMS = None
    RNG = None
    GREEDY = False
    EVENT_LOG = None   # list[np.ndarray] — all event vecs this game (shared ref)
    STEP_LOG = None    # list[dict] — one per action chosen

    def game_start(self, state):
        super().game_start(state)
        self._h = np.zeros(GRU_H)
        self._last_eid = -1

    def _absorb_events(self, state):
        new = [e for e in state.recent_events
               if e.get('event_id', 0) > self._last_eid]
        for ev in sorted(new, key=lambda e: e.get('event_id', 0)):
            vec = encode_event(ev, state.my_id)
            if self.EVENT_LOG is not None:
                self.EVENT_LOG.append(vec)
            self._h = _gru_step(vec, self._h, self.PARAMS)
            self._last_eid = ev.get('event_id', self._last_eid)

    def choose_action(self, state, valid_actions):
        self._absorb_events(state)

        by = {}
        for a in valid_actions:
            by.setdefault(a.action_type, []).append(a)
        mask = np.array([1.0 if at in by else 0.0 for at in ACTIONS])
        snap = np.array(snap_encode(state, self._known_list(state)))

        logits, value = _mlp_forward(self._h, snap, self.PARAMS)
        probs = _masked_probs(logits, mask)
        idx = int(np.argmax(probs)) if self.GREEDY else int(self.RNG.choice(N_ACTIONS, p=probs))

        if self.STEP_LOG is not None:
            self.STEP_LOG.append({
                'event_count': len(self.EVENT_LOG) if self.EVENT_LOG is not None else 0,
                'snapshot': snap.tolist(),
                'mask': mask.tolist(),
                'action': idx,
                'old_logp': float(np.log(probs[idx] + 1e-12)),
                'old_value': value,
            })

        at = ACTIONS[idx]
        acts = by.get(at) or by.get(ActionType.DRAW) or [Action(ActionType.DRAW)]
        if at in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
            chosen = self._best_target(acts, state)
            if at == ActionType.PLAY_CAT_TRIPLE:
                from dataclasses import replace
                chosen = replace(chosen, named_card=DEF)
            return chosen
        return acts[0]


def play_one(policy_w, pool_w, rng, npr, self_prob=0.5):
    """Run one game. Returns (game_data dict, reward) or (None, 0)."""
    p = _np_params(policy_w)
    pool = [_np_params(w) for w in pool_w]

    event_log, step_log = [], []

    class Learner(_LearnerAgent):
        PARAMS = p; RNG = npr; GREEDY = False
        EVENT_LOG = event_log; STEP_LOG = step_log

    opponents = []
    for _ in range(4):
        if pool and rng.random() < self_prob:
            pp = rng.choice(pool)
            class Frozen(_LearnerAgent):
                PARAMS = pp; RNG = npr; GREEDY = rng.random() < 0.8
                EVENT_LOG = None; STEP_LOG = None
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

    return {'event_vecs': [v.tolist() for v in event_log], 'steps': step_log}, reward


def rollout_worker(args):
    """(policy_w, pool_w, n_games, seed, self_prob) -> list[(game_data, reward)]."""
    policy_w, pool_w, n_games, seed, self_prob = args
    import random as _random
    rng = _random.Random(seed)
    npr = np.random.default_rng(seed)
    out = []
    for _ in range(n_games):
        gd, rew = play_one(policy_w, pool_w, rng, npr, self_prob)
        if gd is not None:
            out.append((gd, rew))
    return out


def evaluate(policy_w, n=2000, seed=99):
    """Greedy win% and avg place vs fleet."""
    import random as _random
    p = _np_params(policy_w)
    rng = _random.Random(seed); npr = np.random.default_rng(seed)

    class Greedy(_LearnerAgent):
        PARAMS = p; RNG = npr; GREEDY = True; EVENT_LOG = None; STEP_LOG = None

    wins = 0; place_sum = 0; games = 0
    for _ in range(n):
        me = Greedy(name='Rhino')
        opps = [c(name=c.__name__) for c in rng.sample(FLEET, 4)]
        agents = [me] + opps
        order = list(range(5)); rng.shuffle(order); seat = order.index(0)
        r = GameEngine([agents[i] for i in order], collect_events=True).play_game(5)
        if r['winner'] < 0:
            continue
        deaths = [e['player'] for e in r['events'] if e['type'] == 'explode']
        if len(deaths) != 4:
            continue
        finish = [r['winner']] + list(reversed(deaths))
        place = finish.index(seat) + 1
        games += 1; place_sum += place
        if place == 1:
            wins += 1
    return (wins / games if games else 0.0), (place_sum / games if games else 0.0)
