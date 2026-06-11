#!/usr/bin/env python3
"""
Distributed simulation controller.

Spawns one agent process per player (each runs an HTTP server),
waits for them to be ready, then runs games via RemoteAgent proxies.

Usage:
  python simulation/controller.py --games 100 --players 4
  python simulation/controller.py --games 50 --agents heuristic random heuristic random

Each agent process is a separate OS process — agents can be any language
as long as they implement the HTTP/JSON protocol in agents/agent_server.py.
"""
import os
import sys
import time
import argparse
import subprocess
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.remote_agent import RemoteAgent
from simulation.runner import run_simulation, print_stats

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AGENT_SERVER = os.path.join(_PROJECT_ROOT, "agents", "agent_server.py")
_BASE_PORT = 5100


def _wait_for_ready(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def run_distributed(agent_specs: list[dict], n_games: int = 100, seed: int | None = None) -> dict:
    """
    agent_specs: [{"type": "random"|"heuristic", "name": str, "port": int (optional)}]
    """
    for i, spec in enumerate(agent_specs):
        spec.setdefault("port", _BASE_PORT + i)

    processes = []
    try:
        for spec in agent_specs:
            cmd = [
                sys.executable, _AGENT_SERVER,
                "--agent", spec["type"],
                "--port", str(spec["port"]),
                "--name", spec["name"],
            ]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            processes.append(proc)
            print(f"  Started {spec['name']} ({spec['type']}) on :{spec['port']}  pid={proc.pid}")

        print("  Waiting for agents...")
        for spec in agent_specs:
            if not _wait_for_ready(spec["port"]):
                raise RuntimeError(f"Agent on port {spec['port']} failed to start within 15s")
        print(f"  All {len(agent_specs)} agents ready.\n")

        agents = [
            RemoteAgent(url=f"http://127.0.0.1:{s['port']}", name=s["name"])
            for s in agent_specs
        ]

        stats = run_simulation(agents, n_games=n_games, seed=seed)
        return stats

    finally:
        for proc in processes:
            proc.terminate()
        for proc in processes:
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Distributed Exploding Kittens simulation")
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--players", type=int, default=4, choices=[2, 3, 4, 5])
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--agents", nargs="*",
        metavar="TYPE",
        help="Agent types per player (random|heuristic). Defaults to all heuristic.",
    )
    args = parser.parse_args()

    agent_types = args.agents or ["heuristic"] * args.players
    if len(agent_types) != args.players:
        parser.error(f"--agents must have exactly {args.players} entries")

    specs = [
        {"type": t, "name": f"{t.capitalize()}-{i}"}
        for i, t in enumerate(agent_types)
    ]

    print(f"Running {args.games} distributed games with {args.players} agents...\n")
    stats = run_distributed(specs, n_games=args.games, seed=args.seed)
    print_stats(stats)
