"""Rollout workers for Gorilla self-play.

A rollout plays one game with the learner (current policy, sampling actions and
logging transitions) against 4 opponents drawn from the heuristic fleet and a
pool of past-self snapshots. Stateless given weights, so it parallelizes.
"""
import numpy as np

from agents.coyote_agent import CoyoteAgent
from agents.survival_agent import SurvivalAgent
from agents.survival_agent_v2 import SurvivalAgentV2
from agents.aggressive_agent import AggressiveAgent
from agents.heuristic_agent import HeuristicAgent
from agents.orangutan_features import encode, ACTIONS, N_ACTIONS
from game.engine import GameEngine
from game.actions import Action, ActionType
from game.cards import CardType

DEF = CardType.DEFUSE
NEG = -1e9
FLEET = [CoyoteAgent, SurvivalAgentV2, SurvivalAgent, AggressiveAgent, HeuristicAgent]


def _np_params(w):
    return {k: np.array(v) for k, v in w.items() if k != "arch"}


def _forward(p, x):
    a1 = np.maximum(p["W1"] @ x + p["b1"], 0)
    a2 = np.maximum(p["W2"] @ a1 + p["b2"], 0)
    logits = p["W3"] @ a2 + p["b3"]
    value = float((p["Wv"] @ a2 + p["bv"])[0]) if "Wv" in p else 0.0
    return logits, value


def _masked_probs(logits, mask):
    z = np.where(mask > 0, logits, NEG); z = z - z.max()
    e = np.exp(z) * mask
    return e / e.sum()


def _resolve(at, acts, agent, state):
    if at in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
        chosen = agent._best_target(acts, state)
        if at == ActionType.PLAY_CAT_TRIPLE:
            from dataclasses import replace
            chosen = replace(chosen, named_card=DEF)
        return chosen
    return acts[0]


class _NetAgentBase(CoyoteAgent):
    """Shared: choose action types with a numpy policy; other endpoints = Coyote."""
    PARAMS = None
    RNG = None
    GREEDY = True
    LOG = None

    def choose_action(self, state, valid_actions):
        by = {}
        for a in valid_actions:
            by.setdefault(a.action_type, []).append(a)
        mask = np.array([1.0 if at in by else 0.0 for at in ACTIONS])
        feats = np.array(encode(state, self._known_list(state)))
        logits, value = _forward(self.PARAMS, feats)
        probs = _masked_probs(logits, mask)
        if self.GREEDY:
            idx = int(np.argmax(probs))
        else:
            idx = int(self.RNG.choice(N_ACTIONS, p=probs))
        if self.LOG is not None:
            self.LOG.append((feats.tolist(), idx, float(np.log(probs[idx] + 1e-12)),
                             value, mask.tolist()))
        return _resolve(ACTIONS[idx], by[ACTIONS[idx]], self, state)


def play_one(policy_p, pool, rng, npr, self_prob=0.5):
    """policy_p: numpy params for the learner. pool: list of numpy param dicts
    (past selves). Returns (trajectory, reward)."""
    log = []

    class Learner(_NetAgentBase):
        PARAMS = policy_p; RNG = npr; GREEDY = False; LOG = log
        def game_start(self, state):
            super().game_start(state); self.LOG = log

    learner = Learner(name="Gorilla")

    opponents = []
    for _ in range(4):
        if pool and rng.random() < self_prob:
            params = rng.choice(pool)
            class Frozen(_NetAgentBase):
                PARAMS = params; RNG = npr; GREEDY = (rng.random() < 0.8); LOG = None
            opponents.append(Frozen(name="self"))
        else:
            opponents.append(rng.choice(FLEET)(name="fleet"))

    agents = [learner] + opponents
    order = list(range(5)); rng.shuffle(order)
    seat_of_learner = order.index(0)
    r = GameEngine([agents[i] for i in order], collect_events=True).play_game(5)
    if r["winner"] < 0:
        return log, 0.0
    deaths = [e["player"] for e in r["events"] if e["type"] == "explode"]
    if r["winner"] == seat_of_learner:
        reward = 1.0
    elif seat_of_learner in deaths:
        reward = -1.0
    else:
        reward = 0.0
    return log, reward


def rollout_worker(args):
    """(policy_w, pool_w, n_games, seed, self_prob) -> list of (traj, reward)."""
    policy_w, pool_w, n_games, seed, self_prob = args
    import random as _random
    policy_p = _np_params(policy_w)
    pool = [_np_params(w) for w in pool_w]
    rng = _random.Random(seed)
    npr = np.random.default_rng(seed)
    out = []
    for _ in range(n_games):
        out.append(play_one(policy_p, pool, rng, npr, self_prob))
    return out


def evaluate(policy_w, n=3000, seed=99):
    """Greedy win% and avg place of the learner vs the heuristic fleet."""
    import random as _random
    p = _np_params(policy_w)
    rng = _random.Random(seed); npr = np.random.default_rng(seed)
    wins = 0; place_sum = 0; games = 0

    class Greedy(_NetAgentBase):
        PARAMS = p; RNG = npr; GREEDY = True; LOG = None

    for _ in range(n):
        me = Greedy(name="Gorilla")
        opps = [c(name=c.__name__) for c in rng.sample(FLEET, 4)]
        agents = [me] + opps
        order = list(range(5)); rng.shuffle(order); seat = order.index(0)
        r = GameEngine([agents[i] for i in order], collect_events=True).play_game(5)
        if r["winner"] < 0:
            continue
        deaths = [e["player"] for e in r["events"] if e["type"] == "explode"]
        if len(deaths) != 4:
            continue
        finish = [r["winner"]] + list(reversed(deaths))
        place = finish.index(seat) + 1
        games += 1; place_sum += place
        if place == 1:
            wins += 1
    return (wins / games if games else 0), (place_sum / games if games else 0)
