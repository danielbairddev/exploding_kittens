#!/usr/bin/env python3
"""Find the strongest Skull bots by head-to-head win rate.

Runs a tournament of random lineups drawn from the live Skull roster
(``SKULL_BOTS``), tallies per-bot win rate + average finishing place, and
reports the top bots. Mirrors how the arena actually seats games (4 distinct
bots per game, random seat order) so the ranking matches the dashboard.

Usage:
    python scripts/top_bots.py                 # 1000 games (default)
    python scripts/top_bots.py --games 5000    # more games, less noise
    python scripts/top_bots.py --games 200     # quick, noisier
    python scripts/top_bots.py --top 5         # show the top 5 instead of 3

Importable too:
    from scripts.top_bots import get_top_bots
    top3 = get_top_bots(n_games=1000)          # list of bot types, best first
"""
import argparse
import contextlib
import io
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.dashboard_server import SKULL_BOTS, SKULL_PLAYERS_PER_GAME
from skull.engine import SkullEngine

DEFAULT_GAMES = 1000
DEFAULT_TOP = 3


def _bot_name(cls) -> str:
    """Display name from the bot's ARENA metadata (falls back to the class name)."""
    arena = getattr(cls, "ARENA", {})
    return arena.get("name", getattr(cls, "__name__", repr(cls)))


def _draw_lineup(rng, roster, players_per_game):
    """A random lineup of distinct bots, randomly seated — same scheme the arena
    uses (distinct agents first; repeat only if the roster is smaller than the
    ring)."""
    lineup, bag = [], []
    while len(lineup) < players_per_game:
        if not bag:                       # refill once we run out of distinct bots
            bag = list(roster)
            rng.shuffle(bag)
        lineup.append(bag.pop())
    rng.shuffle(lineup)                    # randomize seat order
    return lineup


def run_tournament(n_games=DEFAULT_GAMES, roster=None,
                   players_per_game=SKULL_PLAYERS_PER_GAME, seed=None):
    """Play ``n_games`` Skull games and return a leaderboard (best first).

    Each row: {name, wins, games, win_rate, avg_place}. A bot is counted once
    per game it appears in and credited at most one win, matching the arena.
    """
    roster = roster if roster is not None else SKULL_BOTS
    cls_by_name = {_bot_name(b): b for b in roster}
    rng = random.Random(seed)
    wins = defaultdict(int)
    games = defaultdict(int)
    place_sum = defaultdict(int)
    place_games = defaultdict(int)

    # Some bots print on every move; swallow it so only the leaderboard shows.
    with contextlib.redirect_stdout(io.StringIO()):
        for _ in range(n_games):
            lineup = _draw_lineup(rng, roster, players_per_game)
            agents = [b(name=_bot_name(b)) for b in lineup]
            result = SkullEngine(agents).play_game(len(agents))

            winner = result["winner"]
            winner_name = _bot_name(lineup[winner]) if winner >= 0 else None
            for name in {_bot_name(b) for b in lineup}:
                games[name] += 1
            if winner_name is not None:
                wins[winner_name] += 1

            # Average finishing place (1 = best), when the engine reports order.
            for place, seat in enumerate(result.get("finish_order", [])):
                name = _bot_name(lineup[seat])
                place_sum[name] += place + 1
                place_games[name] += 1

    table = []
    for name, g in games.items():
        w = wins.get(name, 0)
        pg = place_games.get(name, 0)
        table.append({
            "cls": cls_by_name.get(name),
            "name": name,
            "wins": w,
            "games": g,
            "win_rate": w / g if g else 0.0,
            "avg_place": (place_sum[name] / pg) if pg else None,
        })
    table.sort(key=lambda r: r["win_rate"], reverse=True)
    return table


def get_top_bots(n_games=DEFAULT_GAMES, top=DEFAULT_TOP, **kwargs):
    """The ``top`` strongest bot types by win rate over ``n_games`` games,
    sorted best first."""
    return [row["cls"] for row in run_tournament(n_games=n_games, **kwargs)[:top]]


def main():
    ap = argparse.ArgumentParser(description="Rank Skull bots by win rate.")
    ap.add_argument("--games", type=int, default=DEFAULT_GAMES,
                    help=f"number of games to simulate (default {DEFAULT_GAMES})")
    ap.add_argument("--top", type=int, default=DEFAULT_TOP,
                    help=f"how many top bots to highlight (default {DEFAULT_TOP})")
    ap.add_argument("--players", type=int, default=SKULL_PLAYERS_PER_GAME,
                    help=f"players per game (default {SKULL_PLAYERS_PER_GAME})")
    ap.add_argument("--seed", type=int, default=None,
                    help="RNG seed for reproducible tournaments")
    args = ap.parse_args()

    print(f"Running {args.games} games over {len(SKULL_BOTS)} bots "
          f"({args.players} per game)...", flush=True)
    table = run_tournament(args.games, players_per_game=args.players, seed=args.seed)

    print(f"\n{'rank':>4}  {'bot':<16}  {'win %':>7}  {'avg place':>9}  {'games':>6}")
    print(f"{'-' * 4:>4}  {'-' * 16:<16}  {'-' * 7:>7}  {'-' * 9:>9}  {'-' * 6:>6}")
    for i, r in enumerate(table):
        place = f"{r['avg_place']:.2f}" if r["avg_place"] is not None else "—"
        print(f"{i + 1:>4}  {r['name']:<16}  {r['win_rate'] * 100:>6.1f}%  "
              f"{place:>9}  {r['games']:>6}")

    top = table[:args.top]
    print(f"\nTop {len(top)}: " + ", ".join(
        f"{r['name']} ({r['win_rate'] * 100:.1f}%)" for r in top))


if __name__ == "__main__":
    main()
