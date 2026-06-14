#!/usr/bin/env python3
"""Skull simulation runner (in-process) — the quick functionality test.

Usage:
  python -m skull.run                      # 4 random bots, 2000 games
  python -m skull.run --players 5          # 5-handed table
  python -m skull.run --games 10000        # more games
  python -m skull.run --verbose            # watch a single game move by move
  python -m skull.run --seed 42            # reproducible
  python -m skull.run --agent "Ian's Bomber"

With a single bot type filling every seat, win rates should land near 1/players
— a handy sanity check that no seat gets a structural advantage.
"""
import argparse
import os
import sys

from web.dashboard_server import SKULL_BOTS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skull.engine import SkullEngine
from skull.agents.random_agent import RandomSkullAgent

def main():
    parser = argparse.ArgumentParser(description="Skull simulation")
    parser.add_argument("--games", type=int, default=2000)
    parser.add_argument("--players", type=int, default=4, choices=[3, 4, 5, 6])
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--verbose", action="store_true", help="Watch one game")
    parser.add_argument("--agent", type=str, default=None)
    args = parser.parse_args()

    agent_class = None
    agent_name = args.agent
    for bot in SKULL_BOTS:
        if agent_name == bot.ARENA.get("name"):
            agent_class = bot
    if agent_class is None:
        Exception(f"{agent_name} is not a valid agent name. If you have added this agent, add it to "
                  f"dashboard_server.py SKULL_BOTS to test it here")

    agents = [agent_class(name=f"{agent_name}-{i}", seed=args.seed) for i in range(args.players)]

    if args.verbose:
        print(f"Watching one {args.players}-player game...\n")
        engine = SkullEngine(agents, seed=args.seed, verbose=True)
        result = engine.play_game(args.players)
        print(f"\nResult: {result}")
        return

    print(f"Running {args.games} games, {args.players} random bots...")
    wins = [0] * args.players
    no_winner = 0
    total_rounds = 0
    for g in range(args.games):
        seed = None if args.seed is None else args.seed + g
        engine = SkullEngine(agents, seed=seed)
        result = engine.play_game(args.players)
        total_rounds += result["turns"]
        if result["winner"] >= 0:
            wins[result["winner"]] += 1
        else:
            no_winner += 1

    print(f"\nGames: {args.games}   avg rounds/game: {total_rounds / args.games:.1f}"
          f"   no-winner: {no_winner}")
    print("Wins by seat (expect ~{:.1%} each):".format(1 / args.players))
    for seat, w in enumerate(wins):
        bar = "#" * round(40 * w / args.games)
        print(f"  seat {seat}: {w:5d}  {w / args.games:6.1%}  {bar}")


if __name__ == "__main__":
    main()
