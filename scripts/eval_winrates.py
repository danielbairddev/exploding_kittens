#!/usr/bin/env python3
"""Find arena noise levels for Orangutan, Rhino, Elephant.

Evaluates each bot at a range of noise values against the full non-ML fleet,
then prints a table so you can pick values that preserve relative order but
compress strength toward the heuristic bots.

Usage:
    python3 scripts/eval_winrates.py
    python3 scripts/eval_winrates.py --games 1000  # faster, noisier
    python3 scripts/eval_winrates.py --games 4000  # slower, more accurate
"""
import argparse, sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agents.orangutan_agent as _oa
import agents.rhino_agent     as _ra
import agents.elephant_agent  as _ea

from agents.coyote_agent      import CoyoteAgent
from agents.survival_agent    import SurvivalAgent
from agents.survival_agent_v2 import SurvivalAgentV2
from agents.aggressive_agent  import AggressiveAgent
from agents.heuristic_agent   import HeuristicAgent
from agents.chaos_agent       import ChaosAgent
from agents.random_agent      import RandomAgent
from game.engine import GameEngine

FLEET = [CoyoteAgent, SurvivalAgentV2, SurvivalAgent, AggressiveAgent,
         HeuristicAgent, ChaosAgent, RandomAgent]

NOISE_LEVELS = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]


def eval_agent(agent_cls, noise_mod, n_games, seed):
    """Win rate of agent_cls (with noise_mod applied) vs random FLEET draws."""
    rng = random.Random(seed)
    wins = games = 0
    for _ in range(n_games):
        me = agent_cls(name='target')
        opps = [c(name=c.__name__) for c in rng.sample(FLEET, 4)]
        agents = [me] + opps
        order = list(range(5)); rng.shuffle(order); seat = order.index(0)
        r = GameEngine([agents[i] for i in order]).play_game(5)
        if r['winner'] < 0: continue
        games += 1
        if r['winner'] == seat: wins += 1
    return wins / games if games else 0.0


def sweep(name, mod, agent_cls, n_games, seed):
    print(f"\n{'─'*52}")
    print(f"  {name}   ({n_games} games per level)")
    print(f"  {'noise':>6}  {'win %':>7}")
    print(f"  {'──────':>6}  {'───────':>7}")
    for noise in NOISE_LEVELS:
        mod._ARENA_NOISE = noise
        wr = eval_agent(agent_cls, mod, n_games, seed)
        print(f"  {noise:>6.0%}  {wr*100:>6.1f}%")
    mod._ARENA_NOISE = 0.0  # reset


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--games', type=int, default=2000)
    ap.add_argument('--seed',  type=int, default=42)
    args = ap.parse_args()

    print(f"Sweeping noise levels ({args.games} games each) ...")

    sweep("Orangutan", _oa, _oa.OrangutanAgent, args.games, args.seed)
    sweep("Rhino",     _ra, _ra.RhinoAgent,     args.games, args.seed)
    sweep("Elephant",  _ea, _ea.ElephantAgent,  args.games, args.seed)

    print(f"\n{'─'*52}")
    print("Pick noise values that keep Elephant > Rhino > Orangutan")
    print("and compress all three toward the heuristic bot win rates (~20-25%).")
    print("Then set _ARENA_NOISE in each agent file accordingly.")


if __name__ == '__main__':
    main()
