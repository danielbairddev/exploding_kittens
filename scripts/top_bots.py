#!/usr/bin/env python3
"""Find the strongest Skull bots — using the real arena's own code.

This drives the same `Arena` the live dashboard uses: the same matchmaking
(`rated_lineup` — top bots by average place + a rotating challenger), the same
per-bot accounting (`record_game`), and the same leaderboard (`stats_payload`).
Running here vs. on the server differs only in how many games have accumulated,
so the rankings can't contradict each other by construction.

Usage:
    python scripts/top_bots.py                 # 1000 games (default)
    python scripts/top_bots.py --games 20000   # more games, closer to the live board
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.dashboard_server import (
    Arena, SKULL_ROSTER, SKULL_BOTS, SKULL_PLAYERS_PER_GAME,
    _GuardedAgent, BotCrash,
)
from skull.engine import SkullEngine

DEFAULT_GAMES = 1000
DEFAULT_TOP = 3

# A snapshot path that never exists, so the scratch Arena starts empty and is
# never persisted (we never call save_snapshot) — the live stats are untouched.
_SCRATCH_SNAPSHOT = "top_bots_scratch_DO_NOT_PERSIST.json"


def run_tournament(n_games=DEFAULT_GAMES, players_per_game=SKULL_PLAYERS_PER_GAME,
                   seed=None):
    """Play ``n_games`` Skull games through a fresh arena and return its
    leaderboard (list of stats rows), sorted by win rate then ELO — exactly how
    the live dashboard ranks the board.

    A bot that crashes mid-game is benched for the rest of the run, mirroring the
    arena's quarantine. Returns the same row dicts as ``Arena.stats_payload``.
    """
    rng = random.Random(seed)
    failures = 0

    # Construction + simulation are stdout-silenced: the Arena logs on load and
    # some bots print on every move; only the leaderboard should reach the user.
    with contextlib.redirect_stdout(io.StringIO()):
        arena = Arena(_SCRATCH_SNAPSHOT, roster=SKULL_ROSTER,
                      players_per_game=players_per_game)
        for _ in range(n_games):
            seats = arena.rated_lineup(rng)          # same matchmaking as the server
            if not seats:                            # every bot quarantined
                break
            seat_agents = [_GuardedAgent(b["cls"](name=b["name"]), i)
                           for i, b in enumerate(seats)]
            try:
                result = SkullEngine(seat_agents, collect_events=True).play_game(len(seats))
            except BotCrash as crash:
                arena.disable_bot(seats[crash.seat]["bot_id"], repr(crash.original))
                failures += 1
                continue
            except Exception:                        # unattributable engine error
                failures += 1
                continue
            arena.record_game(seats, result, result["events"])

    leaderboard = arena.stats_payload()["leaderboard"]
    leaderboard.sort(key=lambda r: (r["win_rate"], r["elo"]), reverse=True)

    if failures:
        benched = sorted(arena.roster[bid]["name"] for bid in arena.disabled)
        msg = f"[top_bots] skipped {failures} game(s) due to bot crashes"
        if benched:
            msg += "; benched: " + ", ".join(benched)
        print(msg, file=sys.stderr)
    return leaderboard


def get_top_bots(n_games=DEFAULT_GAMES, top=DEFAULT_TOP, **kwargs):
    """The ``top`` strongest bot types by win rate over ``n_games`` games,
    sorted best first."""
    cls_by_id = {b["bot_id"]: b["cls"] for b in SKULL_ROSTER}
    return [cls_by_id[row["bot_id"]] for row in run_tournament(n_games=n_games, **kwargs)[:top]]


def main():
    ap = argparse.ArgumentParser(description="Rank Skull bots by win rate (live-arena code).")
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
