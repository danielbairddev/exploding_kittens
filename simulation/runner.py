import json
import os
from collections import defaultdict
from datetime import datetime
from game.engine import GameEngine


def run_simulation(agents: list, n_games: int = 1000, seed: int | None = None,
                   log_dir: str | None = None, log_games: int = 0) -> dict:
    """
    Run n_games games with the given agents and return aggregated stats.

    log_dir:   directory to write game logs (created if needed)
    log_games: how many games to log in full detail (0 = summary only)
    """
    n_players = len(agents)
    wins = defaultdict(int)
    total_turns = 0

    agent_names = [getattr(a, "name", f"Agent{i}") for i, a in enumerate(agents)]
    agent_types = [type(a).__name__ for a in agents]

    log_file = None
    if log_dir and log_games > 0:
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(log_dir, f"sim_{ts}.jsonl")
        log_file = open(log_path, "w")
        meta = {
            "type": "simulation",
            "n_games": n_games,
            "log_games": log_games,
            "seed": seed,
            "players": [{"id": i, "name": n, "agent_type": t}
                        for i, (n, t) in enumerate(zip(agent_names, agent_types))],
        }
        log_file.write(json.dumps(meta) + "\n")
        print(f"  Logging first {log_games} games to {log_path}")

    try:
        for i in range(n_games):
            game_seed = (seed + i) if seed is not None else None
            collect = log_file is not None and i < log_games
            engine = GameEngine(agents, seed=game_seed, verbose=False, collect_events=collect)
            result = engine.play_game(n_players)

            wins[result["winner"]] += 1
            total_turns += result["turns"]

            if collect:
                record = {
                    "type": "game",
                    "game_id": i,
                    "seed": game_seed,
                    "winner": result["winner"],
                    "winner_name": agent_names[result["winner"]],
                    "turns": result["turns"],
                    "elimination_order": result["elimination_order"],
                    "events": result["events"],
                }
                log_file.write(json.dumps(record) + "\n")
    finally:
        if log_file:
            log_file.close()

    stats = {
        "n_games": n_games,
        "n_players": n_players,
        "avg_turns": round(total_turns / n_games, 1),
        "players": [],
    }

    for i, name in enumerate(agent_names):
        win_rate = wins[i] / n_games
        stats["players"].append({
            "id": i,
            "name": name,
            "wins": wins[i],
            "win_rate": round(win_rate, 4),
        })

    stats["players"].sort(key=lambda p: p["wins"], reverse=True)
    return stats


def print_stats(stats: dict):
    print(f"\n{'='*50}")
    print(f"  Simulation: {stats['n_games']} games, {stats['n_players']} players")
    print(f"  Avg turns per game: {stats['avg_turns']}")
    print(f"{'='*50}")
    print(f"  {'Player':<20} {'Wins':>8} {'Win Rate':>10}")
    print(f"  {'-'*40}")
    for p in stats["players"]:
        print(f"  {p['name']:<20} {p['wins']:>8} {p['win_rate']:>9.1%}")
    print(f"{'='*50}\n")
