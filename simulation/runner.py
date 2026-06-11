from collections import defaultdict
from game.engine import GameEngine


def run_simulation(agents: list, n_games: int = 1000, seed: int | None = None) -> dict:
    """
    Run n_games games with the given agents and return aggregated stats.
    Agents are assigned player IDs 0..n-1 in the order provided.
    """
    n_players = len(agents)
    wins = defaultdict(int)
    total_turns = 0
    elimination_counts = defaultdict(int)  # position -> count (0=first out, n-2=last out)

    for i in range(n_games):
        game_seed = (seed + i) if seed is not None else None
        engine = GameEngine(agents, seed=game_seed, verbose=False)
        result = engine.play_game(n_players)

        wins[result["winner"]] += 1
        total_turns += result["turns"]
        for pos, pid in enumerate(result["elimination_order"]):
            elimination_counts[(pid, pos)] += 1

    agent_names = [getattr(a, "name", f"Agent{i}") for i, a in enumerate(agents)]

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
