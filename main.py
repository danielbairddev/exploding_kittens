#!/usr/bin/env python3
"""
Exploding Kittens simulation runner (in-process).

Usage:
  python main.py                         # 4 random agents, 1000 games
  python main.py --agent heuristic       # use heuristic agents
  python main.py --games 5000            # run 5000 games
  python main.py --players 3             # 3 players
  python main.py --verbose               # watch a single game
  python main.py --seed 42               # reproducible results

For distributed (agents as separate processes / other languages):
  python simulation/controller.py --games 100 --agents heuristic random heuristic random
"""
import argparse
import sys
import os
from ast import Dict
from typing import Any

from agents.ian1_agent import Ian1Agent
from dashboard_server import ARENA_BOTS

sys.path.insert(0, os.path.dirname(__file__))

from agents.random_agent import RandomAgent
from agents.heuristic_agent import HeuristicAgent
from agents.aggressive_agent import AggressiveAgent
from agents.chaos_agent import ChaosAgent
from simulation.runner import run_simulation, print_stats
from game.engine import GameEngine


def main():
    agent_name_mapping: dict[str, Any] = get_agent_name_mapping()

    parser = argparse.ArgumentParser(description="Exploding Kittens Simulation")
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--players", type=int, default=4, choices=[2, 3, 4, 5])
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--verbose", action="store_true", help="Watch a single game")
    parser.add_argument("--agent", choices=list(agent_name_mapping), default="random")
    parser.add_argument("--log-dir", default="logs", help="Directory for game logs")
    parser.add_argument("--log-games", type=int, default=0, metavar="N",
                        help="Log first N games in full detail (0 = no logging)")
    args = parser.parse_args()

    cls = agent_name_mapping[args.agent]
    agents = [cls(name=f"{args.agent.capitalize()}-{i}", seed=args.seed) for i in range(args.players)]

    if args.verbose:
        print(f"Watching 1 game with {args.players} players...\n")
        engine = GameEngine(agents, seed=args.seed, verbose=True)
        result = engine.play_game(args.players)
        print(f"\nResult: {result}")
    else:
        print(f"Running {args.games} games with {args.players} {args.agent} agents...")
        stats = run_simulation(agents, n_games=args.games, seed=args.seed,
                               log_dir=args.log_dir, log_games=args.log_games)
        print_stats(stats)

def get_agent_name_mapping() -> dict[str, Any]:
    agent_name_mapping: dict[str, Any] = {}
    for bot in ARENA_BOTS:
        agent_name_mapping[bot.ARENA["name"]] = bot
    return agent_name_mapping


if __name__ == "__main__":
    main()
