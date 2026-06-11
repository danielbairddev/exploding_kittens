#!/usr/bin/env python3
"""
Exploding Kittens simulation runner.

Usage:
  python main.py                    # 4 random agents, 1000 games
  python main.py --games 5000       # run 5000 games
  python main.py --players 3        # 3 players
  python main.py --verbose          # watch a single game
  python main.py --seed 42          # reproducible results
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from agents.random_agent import RandomAgent
from simulation.runner import run_simulation, print_stats
from game.engine import GameEngine


def main():
    parser = argparse.ArgumentParser(description="Exploding Kittens Simulation")
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--players", type=int, default=4, choices=[2, 3, 4, 5])
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--verbose", action="store_true", help="Watch a single game")
    args = parser.parse_args()

    agents = [RandomAgent(name=f"Random-{i}", seed=args.seed) for i in range(args.players)]

    if args.verbose:
        print(f"Watching 1 game with {args.players} players...\n")
        engine = GameEngine(agents, seed=args.seed, verbose=True)
        result = engine.play_game(args.players)
        print(f"\nResult: {result}")
    else:
        print(f"Running {args.games} games with {args.players} random agents...")
        stats = run_simulation(agents, n_games=args.games, seed=args.seed)
        print_stats(stats)


if __name__ == "__main__":
    main()
