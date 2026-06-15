"""Rollout workers for Zeus training — the win-maximising twin of Hades.

Same Transformer/feature stack as Hades (reused directly from training.hades), but
the objective is flipped: reward is +1 for winning (sole survivor), -1 otherwise.
No dense shaping, no anti-logic — Zeus only cares about winning.

Opponents are the standard competitive fleet (strong winners + heuristics). The
loser/anti-agent bots (Gabriel, Orpheus, Perdition2, Hades) are intentionally
excluded: training against bots that throw the game would teach Zeus to exploit
suicidal opponents instead of genuinely playing to win.
"""
import numpy as np

from agents.coyote_agent import CoyoteAgent
from agents.survival_agent import SurvivalAgent
from agents.survival_agent_v2 import SurvivalAgentV2
from agents.aggressive_agent import AggressiveAgent
from agents.heuristic_agent import HeuristicAgent
from agents.orangutan_agent import OrangutanAgent
from agents.random_agent import RandomAgent
from agents.chaos_agent import ChaosAgent
from agents.rhino_agent import RhinoAgent
from agents.elephant_agent import ElephantAgent
from agents.ian1_agent import Ian1Agent
from agents.ian2_agent import Ian2Agent
from agents.ian3_agent import Ian3Agent
from agents.perdition2_agent import Perdition2Agent
from agents.gabriel_agent import GabrielAgent
from agents.orpheus_agent import OrpheusAgent
from agents.cassandra_agent import CassandraAgent
from agents.hades_agent import HadesAgent

from training.hades.rollout import _HadesLearner, _make_net
from game.engine import GameEngine

# Competitive opponents, heavily weighted toward the strongest winners — the
# headroom past ~41% is in beating Coyote/Rhino/Elephant/Sly2 more often, so
# Zeus faces them 3x while keeping weaker bots in the mix for generalisation.
FLEET = [CoyoteAgent, CoyoteAgent, CoyoteAgent,
         RhinoAgent, RhinoAgent, RhinoAgent,
         ElephantAgent, ElephantAgent, ElephantAgent,
         SurvivalAgentV2, SurvivalAgentV2, SurvivalAgentV2,
         SurvivalAgent, OrangutanAgent,
         AggressiveAgent, HeuristicAgent, RandomAgent, ChaosAgent,
         Ian1Agent, Ian2Agent]
# Eval fleet mirrors the LIVE arena roster (web/dashboard_server.py ARENA_BOTS)
# so Zeus's win rate is directly comparable to the leaderboard — strong winners,
# heuristics, AND the loser/anti-agent bots it would actually meet in the arena.
# (Keep in sync if the arena roster changes.)
EVAL_FLEET = [HeuristicAgent, AggressiveAgent, ChaosAgent, SurvivalAgent,
              RandomAgent, SurvivalAgentV2, CoyoteAgent, OrangutanAgent,
              Ian1Agent, Ian2Agent, Ian3Agent, Perdition2Agent,
              RhinoAgent, ElephantAgent, GabrielAgent, OrpheusAgent,
              CassandraAgent, HadesAgent]


def play_one(policy_w, pool_w, rng, npr, self_prob=0.3):
    learner_net = _make_net(policy_w)
    ev_log, step_log, nope_log, give_log, place_log = [], [], [], [], []

    class Learner(_HadesLearner):
        NET = learner_net; RNG = npr; GREEDY = False
        EV_LOG = ev_log; STEP_LOG = step_log; NOPE_LOG = nope_log
        GIVE_LOG = give_log; PLACE_LOG = place_log; AUX = None  # no dense shaping

    opponents = []
    for _ in range(4):
        if pool_w and rng.random() < self_prob:
            pnet = _make_net(rng.choice(pool_w))
            class Frozen(_HadesLearner):
                NET = pnet; RNG = npr; GREEDY = (rng.random() < 0.8)
                EV_LOG = None; STEP_LOG = None; NOPE_LOG = None
                GIVE_LOG = None; PLACE_LOG = None; AUX = None
            opponents.append(Frozen(name='self'))
        else:
            opp = rng.choice(FLEET)(name='fleet')
            opp._play_mode = True  # disable arena handicap during training
            opponents.append(opp)

    agents = [Learner(name='Zeus')] + opponents
    order = list(range(5)); rng.shuffle(order)
    seat = order.index(0)
    r = GameEngine([agents[i] for i in order], collect_events=True).play_game(5)

    if r['winner'] < 0 or not step_log:
        return None, 0.0

    won = (seat == r['winner'])          # sole survivor == win
    reward = 1.0 if won else -1.0        # only winning matters; placement ignored

    return {
        'event_vecs': ev_log,
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


def _evaluate_chunk(args):
    policy_w, n, seed = args
    import random as _random
    net = _make_net(policy_w)
    rng = _random.Random(seed); npr = np.random.default_rng(seed)

    class Greedy(_HadesLearner):
        NET = net; RNG = npr; GREEDY = True
        EV_LOG = None; STEP_LOG = None; NOPE_LOG = None
        GIVE_LOG = None; PLACE_LOG = None; AUX = None

    wins = 0; games = 0
    for _ in range(n):
        me = Greedy(name='Zeus')
        # 4 distinct opponents, mirroring how the arena seats 5 distinct bots
        opp_cls = (rng.sample(EVAL_FLEET, 4) if len(EVAL_FLEET) >= 4
                   else [rng.choice(EVAL_FLEET) for _ in range(4)])
        opps = [c(name='fleet') for c in opp_cls]
        for opp in opps:
            opp._play_mode = True
        agents = [me] + opps
        order = list(range(5)); rng.shuffle(order); seat = order.index(0)
        r = GameEngine([agents[i] for i in order], collect_events=True).play_game(5)
        if r['winner'] < 0:
            continue
        games += 1
        if seat == r['winner']:
            wins += 1
    return wins, games


def evaluate(policy_w, n=2000, seed=99, ex=None):
    """Returns win rate vs EVAL_FLEET. Higher is better (random baseline = 20%)."""
    if ex is None:
        wins, games = _evaluate_chunk((policy_w, n, seed))
    else:
        import math
        workers = ex._max_workers
        chunk = math.ceil(n / workers)
        futs = [ex.submit(_evaluate_chunk, (policy_w, chunk, seed + i))
                for i in range(workers)]
        wins = games = 0
        for f in futs:
            w, g = f.result()
            wins += w; games += g
    return wins / games if games else 0.0
