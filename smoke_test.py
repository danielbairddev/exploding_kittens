#!/usr/bin/env python3
"""Pre-deploy smoke test: import the dashboard stack and play one quick game.

Used by auto_deploy.sh before each pull from origin/main.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    # Import validates the full agent roster + engine wiring.
    import web.dashboard_server  # noqa: F401

    from agents.random_agent import RandomAgent
    from game.engine import GameEngine

    agents = [RandomAgent(name=f"Smoke-{i}", seed=0) for i in range(5)]
    result = GameEngine(agents, seed=0).play_game(5)
    if result.get("winner") is None:
        print("smoke: no winner", file=sys.stderr)
        sys.exit(1)
    print(f"smoke ok: winner={result['winner']} turns={result['turns']}")


if __name__ == "__main__":
    main()
