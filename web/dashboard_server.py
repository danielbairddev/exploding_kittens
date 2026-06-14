#!/usr/bin/env python3
"""
Exploding Kittens — Live Arena dashboard.

A single self-contained (stdlib-only) server that:
  * continuously runs games between a fixed roster of bot personalities
    in a background thread,
  * aggregates a live leaderboard + fun stats + a rolling replay buffer,
  * serves a dashboard at  /  that animates games in progress,
  * exposes JSON at  /api/stats  and  /api/showcase,
  * periodically prunes the logs/ directory and snapshots its own state so
    it never falls over on a long-running box.

Run:
    python3 web/dashboard_server.py [PORT]      # default 8767

Meant to sit next to the protocol docs (web/protocol_server.py, port 8766).
"""
import json
import os
import random
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.random_agent import RandomAgent
from agents.heuristic_agent import HeuristicAgent
from agents.aggressive_agent import AggressiveAgent
from agents.chaos_agent import ChaosAgent
from agents.survival_agent import SurvivalAgent
from agents.survival_agent_v2 import SurvivalAgentV2
from agents.coyote_agent import CoyoteAgent
from agents.orangutan_agent import OrangutanAgent
from agents.gabriel_agent import GabrielAgent
from agents.ian1_agent import Ian1Agent
from agents.ian2_agent import  Ian2Agent
from agents.ian3_agent import Ian3Agent
from agents.perdition2_agent import Perdition2Agent
from agents.orpheus_agent import OrpheusAgent
from agents.cassandra_agent import CassandraAgent
from game.engine import GameEngine

# --------------------------------------------------------------------------
# Roster — the full pool of bot personalities. Each game randomly draws
# PLAYERS_PER_GAME of them into random seats, so no bot gets a permanent
# turn-order advantage and (if the pool grows past the table size) matchups
# vary game to game.
# --------------------------------------------------------------------------
# The pool is just a list of agent classes; all display/attribution metadata
# (name, emoji, color, blurb, author) lives on each class as its `ARENA` dict,
# so a contributor's bot file is fully self-contained. To add a bot: ship the
# agent file with an ARENA block and append the class here. Append (don't
# reorder) to keep bot_ids stable; bump SNAPSHOT_PATH's version when you do.
ARENA_BOTS = [
    HeuristicAgent,    # Professor
    AggressiveAgent,   # Maverick
    ChaosAgent,        # Gremlin
    SurvivalAgent,     # Sly
    RandomAgent,       # Lucky
    SurvivalAgentV2,   # Sly2
    CoyoteAgent,       # Coyote
    OrangutanAgent,    # Orangutan
    # Orangutan2Agent,   # Orangutan2 — benched
    Ian1Agent,         # Ian1 (contributor template)
    Ian2Agent,         # Yum
    Ian3Agent,         # It's bombing
    Perdition2Agent,   # Perdition
    # RhinoAgent,        # Rhino — benched
    # ElephantAgent,     # Elephant — benched
    GabrielAgent,       # Gabriel (GRU-128)
    # OrpheusAgent,      # Orpheus — benched (superseded by Cassandra)
    CassandraAgent,    # Cassandra (GRU-192)
]
# Bump to reset ALL bots' stats at once. Individual bots can set a higher
# stats_version in their own ARENA dict to reset independently without
# affecting the rest of the leaderboard.
GLOBAL_STATS_VERSION = 45

ROSTER = [
    {"bot_id": i, "cls": cls, **cls.ARENA,
     "stats_version": max(cls.ARENA.get("stats_version", 0), GLOBAL_STATS_VERSION)}
    for i, cls in enumerate(ARENA_BOTS)
]
EK_PLAYERS_PER_GAME = 5             # full Exploding Kittens table

# Deploy identity (set by deploy_dashboard.sh) so the site shows who shipped what
# — handy when several people deploy at once.
BUILD = {
    "sha": os.environ.get("EK_DEPLOY_SHA", "dev"),
    "by": os.environ.get("EK_DEPLOY_BY", "local"),
    "at": os.environ.get("EK_DEPLOY_AT", ""),
}

# Unique ID for this server process — changes on every restart so clients
# can detect redeploys regardless of whether the git SHA changed.
SERVER_INSTANCE_ID = uuid.uuid4().hex

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
# Bump the version suffix whenever the ROSTER changes so stale per-bot stats
# (keyed by bot_id) don't carry over into a different lineup.
SNAPSHOT_PATH = "dashboard_state_v10.json"
LOSER_SNAPSHOT_PATH = "loser_state_v1.json"
WINRATE_HISTORY_PATH = "winrate_history.tsv"
LOSER_STATS_VERSION = 15
REPLAY_BUFFER_MAX = 40           # detailed games kept for replay
RECENT_RESULTS_MAX = 14          # entries in the results feed
SPARKLINE_MAX = 30               # recent W/L tracked per bot
ELO_TREND_MAX = 60               # recent rating samples for the trend line
MAX_LOG_FILES = 8                # *.jsonl files kept in logs/
MAX_LOG_DIR_BYTES = 200 * 1024 * 1024

# Multiplayer ELO. Each game's finishing order is decomposed into all pairwise
# matchups (higher finish beats lower); each pair gets a standard ELO update,
# summed and normalized by the opponent count (N-1) so one game moves a rating
# by a sane amount. Exploding Kittens is high-variance, so we use a provisional
# K for the first few games (move fast to the right bracket), then a low K to
# absorb luck and reward consistency. All deltas are computed from PRE-game
# ratings and committed together (zero-sum-safe).
BASE_ELO = 1200.0
ELO_K_PROVISIONAL = 32.0
ELO_K_ESTABLISHED = 16.0
ELO_PROVISIONAL_GAMES = 10


class Arena:
    """Holds all shared state. Guarded by a single lock."""

    def __init__(self, snap_shot_path: str = SNAPSHOT_PATH):
        self.lock = threading.Lock()
        self.started_at = time.time()
        self.total_games = 0
        self.total_turns = 0
        self.games_per_sec = 0.0
        self._rate_sample = (self.started_at, 0)        # (time, total_games)
        self.snap_shot_path = os.path.join(LOG_DIR, snap_shot_path)

        # per-bot aggregate, keyed by bot_id
        self.bots = {
            b["bot_id"]: {
                "wins": 0, "games": 0,
                "recent": deque(maxlen=SPARKLINE_MAX),  # 1 win / 0 loss
                "streak": 0, "best_streak": 0,
                "deaths": 0, "first_outs": 0,
                "place_sum": 0, "place_games": 0,  # for average finishing place
                "elo": BASE_ELO, "elo_games": 0, "elo_peak": BASE_ELO,
                "elo_recent": deque(maxlen=ELO_TREND_MAX),  # rating after each game
                "stats_version": b.get("stats_version", 1),
            }
            for b in ROSTER
        }

        self.tallies = {k: 0 for k in (
            "explosions", "defuses", "nopes", "cat_steals",
            "favors", "shuffles", "see_futures", "attacks", "skips", "draws")}

        self.records = {
            "longest": {"turns": 0, "winner": None},
            "shortest": {"turns": 10 ** 9, "winner": None},
            "nope_war": {"count": 0, "winner": None},
        }

        self.recent_results = deque(maxlen=RECENT_RESULTS_MAX)
        self.replay_buffer = deque(maxlen=REPLAY_BUFFER_MAX)
        self._replay_cursor = 0

        self._load_snapshot()

    # ------------------------------------------------------------------ run
    def record_game(self, seats, result, events):
        """seats: list of bot dicts indexed by seat. result/events from engine."""
        winner_seat = result["winner"]
        winner_bot = seats[winner_seat]["bot_id"] if winner_seat >= 0 else None

        # scan events for tallies / nope wars / death order
        ev_counts = dict.fromkeys(self.tallies, 0)
        nope_run = 0
        max_nope_run = 0
        death_seats = []
        for e in events:
            t = e["type"]
            if t == "explode":
                ev_counts["explosions"] += 1
                death_seats.append(e["player"])
            elif t == "defuse":
                ev_counts["defuses"] += 1
            elif t == "nope":
                ev_counts["nopes"] += 1
                nope_run += 1
                max_nope_run = max(max_nope_run, nope_run)
            elif t == "cat_steal":
                ev_counts["cat_steals"] += 1
            elif t == "favor":
                ev_counts["favors"] += 1
            elif t == "shuffle":
                ev_counts["shuffles"] += 1
            elif t == "see_future":
                ev_counts["see_futures"] += 1
            elif t == "attack":
                ev_counts["attacks"] += 1
            elif t == "skip":
                ev_counts["skips"] += 1
            elif t == "draw":
                ev_counts["draws"] += 1
            if t != "nope":
                nope_run = 0

        # Full finishing order (best -> worst): winner, then last-to-die ...
        # first-to-die. death_seats is chronological (from explode events).
        finish_seats = None
        if winner_seat >= 0 and len(death_seats) == len(seats) - 1:
            finish_seats = [winner_seat] + list(reversed(death_seats))

        with self.lock:
            self.total_games += 1
            self.total_turns += result["turns"]

            for k, v in ev_counts.items():
                self.tallies[k] += v

            # ELO first, so the provisional/established K reads each bot's
            # game count from *before* this game.
            if finish_seats is not None:
                finish_bot_ids = [seats[s]["bot_id"] for s in finish_seats]
                if len(set(finish_bot_ids)) == len(finish_bot_ids):  # distinct bots
                    self._update_elo(finish_bot_ids)
                    for place, bot_id in enumerate(finish_bot_ids):   # 0 -> place 1
                        self.bots[bot_id]["place_sum"] += place + 1
                        self.bots[bot_id]["place_games"] += 1

            # Tally per *distinct* bot in this game — win rate counts only the
            # games a bot actually played, and a bot occupying two seats still
            # counts as one game played / at most one win.
            winner_bot_id = seats[winner_seat]["bot_id"] if winner_seat >= 0 else None
            for bot_id in {b["bot_id"] for b in seats}:
                bd = self.bots[bot_id]
                bd["games"] += 1
                won = (bot_id == winner_bot_id)
                bd["recent"].append(1 if won else 0)
                if won:
                    bd["wins"] += 1
                    bd["streak"] += 1
                    bd["best_streak"] = max(bd["best_streak"], bd["streak"])
                else:
                    bd["streak"] = 0
                    bd["deaths"] += 1

            if death_seats:
                first_out_bot = seats[death_seats[0]]["bot_id"]
                self.bots[first_out_bot]["first_outs"] += 1

            wname = seats[winner_seat]["name"] if winner_bot is not None else "nobody"
            if result["turns"] > self.records["longest"]["turns"]:
                self.records["longest"] = {"turns": result["turns"], "winner": wname}
            if result["turns"] < self.records["shortest"]["turns"]:
                self.records["shortest"] = {"turns": result["turns"], "winner": wname}
            if max_nope_run > self.records["nope_war"]["count"]:
                self.records["nope_war"] = {"count": max_nope_run, "winner": wname}

            deaths_named = [seats[s]["name"] for s in death_seats]
            self.recent_results.appendleft({
                "winner": wname,
                "winner_emoji": seats[winner_seat]["emoji"] if winner_bot is not None else "",
                "turns": result["turns"],
                "deaths": deaths_named,
            })

            self._replay_cursor += 1
            self.replay_buffer.append({
                "game_id": self._replay_cursor,
                "turns": result["turns"],
                "winner_seat": winner_seat,
                "seats": [{"seat": i, "bot_id": b["bot_id"], "name": b["name"],
                           "emoji": b["emoji"], "color": b["color"],
                           "type": b["cls"].__name__} for i, b in enumerate(seats)],
                "events": events,
            })

    def _update_elo(self, order):
        """Pairwise multiplayer ELO. `order` is bot_ids best->worst.

        Caller holds self.lock. Expected scores use PRE-game ratings for every
        player; all deltas are computed first, then committed together so the
        update is order-independent (zero-sum-safe, modulo the per-player K).
        """
        n = len(order)
        if n < 2:
            return
        pre = {bid: self.bots[bid]["elo"] for bid in order}
        place = {bid: i for i, bid in enumerate(order)}   # 0 = best finish
        deltas = {}
        for a in order:
            expected = 0.0
            actual = 0.0
            for b in order:
                if a == b:
                    continue
                expected += 1.0 / (1.0 + 10 ** ((pre[b] - pre[a]) / 400.0))
                actual += 1.0 if place[a] < place[b] else 0.0
            k = (ELO_K_PROVISIONAL if self.bots[a]["elo_games"] < ELO_PROVISIONAL_GAMES
                 else ELO_K_ESTABLISHED)
            deltas[a] = k * (actual - expected) / (n - 1)
        for bid in order:
            bd = self.bots[bid]
            bd["elo"] += deltas[bid]
            bd["elo_games"] += 1
            bd["elo_peak"] = max(bd["elo_peak"], bd["elo"])
            bd["elo_recent"].append(round(bd["elo"], 1))

    # --------------------------------------------------------------- serialize
    def sample_rate(self):
        now = time.time()
        with self.lock:
            t0, c0 = self._rate_sample
            dt = now - t0
            if dt > 0:
                self.games_per_sec = round((self.total_games - c0) / dt, 1)
            self._rate_sample = (now, self.total_games)

    def stats_payload(self):
        with self.lock:
            now = time.time()
            gps = self.games_per_sec

            leaderboard = []
            for b in ROSTER:
                bd = self.bots[b["bot_id"]]
                games = bd["games"]
                leaderboard.append({
                    "bot_id": b["bot_id"], "name": b["name"], "emoji": b["emoji"],
                    "color": b["color"], "type": b["cls"].__name__, "blurb": b["blurb"],
                    "author": b.get("author", "—"),
                    "elo": round(bd["elo"]), "elo_peak": round(bd["elo_peak"]),
                    "elo_games": bd["elo_games"], "provisional": bd["elo_games"] < ELO_PROVISIONAL_GAMES,
                    "elo_recent": [round(x) for x in bd["elo_recent"]],
                    "avg_place": round(bd["place_sum"] / bd["place_games"], 3) if bd["place_games"] else None,
                    "wins": bd["wins"], "games": games,
                    "win_rate": round(bd["wins"] / games, 4) if games else 0.0,
                    "recent": list(bd["recent"]),
                    "streak": bd["streak"], "best_streak": bd["best_streak"],
                    "first_outs": bd["first_outs"],
                })
            leaderboard.sort(key=lambda x: (x["elo"], x["wins"]), reverse=True)

            return {
                "build": BUILD,
                "uptime_secs": int(now - self.started_at),
                "total_games": self.total_games,
                "games_per_sec": gps,
                "avg_turns": round(self.total_turns / self.total_games, 1) if self.total_games else 0,
                "leaderboard": leaderboard,
                "tallies": dict(self.tallies),
                "records": json.loads(json.dumps(self.records)),
                "recent_results": list(self.recent_results),
            }

    def showcase_payload(self):
        with self.lock:
            if not self.replay_buffer:
                return None
            return self.replay_buffer[random.randrange(len(self.replay_buffer))]

    def rated_lineup(self, rng):
        """Matchmaking for a rated game: the top (PLAYERS_PER_GAME - 1) bots,
        plus one random challenger from the rest, seated randomly.

        Ranked by average finishing place (lower = better) — steadier than ELO,
        so the 'top' set doesn't thrash. Bots with little data sort to the middle
        so they still get sampled."""
        def avg_place(b):
            bd = self.bots[b["bot_id"]]
            return bd["place_sum"] / bd["place_games"] if bd["place_games"] >= 20 else 3.0
        with self.lock:
            ordered = sorted(ROSTER, key=avg_place)   # ascending: best place first
        n_top = min(EK_PLAYERS_PER_GAME - 1, len(ordered))
        top = ordered[:n_top]
        rest = ordered[n_top:]
        lineup = list(top)
        if rest:
            lineup.append(rng.choice(rest))
        # If the pool is smaller than the ring, top up with distinct extras.
        pool = [b for b in ROSTER if b not in lineup]
        rng.shuffle(pool)
        while len(lineup) < EK_PLAYERS_PER_GAME and pool:
            lineup.append(pool.pop())
        rng.shuffle(lineup)
        return lineup

    # ----------------------------------------------------------- persistence
    def _load_snapshot(self):
        try:
            with open(self.snap_shot_path) as f:
                s = json.load(f)
        except (OSError, ValueError):
            return
        try:
            self.total_games = s.get("total_games", 0)
            self.total_turns = s.get("total_turns", 0)
            self.tallies.update(s.get("tallies", {}))
            self.records.update(s.get("records", {}))
            for bid_str, bd in s.get("bots", {}).items():
                bid = int(bid_str)
                if bid in self.bots:
                    # If stats_version was bumped in ARENA, discard old stats for this bot.
                    current_version = self.bots[bid].get("stats_version", 1)
                    if bd.get("stats_version", 1) != current_version:
                        print(f"[arena] stats reset for bot_id {bid} (version mismatch)", flush=True)
                        continue
                    self.bots[bid]["wins"] = bd.get("wins", 0)
                    self.bots[bid]["games"] = bd.get("games", 0)
                    self.bots[bid]["best_streak"] = bd.get("best_streak", 0)
                    self.bots[bid]["deaths"] = bd.get("deaths", 0)
                    self.bots[bid]["first_outs"] = bd.get("first_outs", 0)
                    self.bots[bid]["place_sum"] = bd.get("place_sum", 0)
                    self.bots[bid]["place_games"] = bd.get("place_games", 0)
                    self.bots[bid]["elo"] = bd.get("elo", BASE_ELO)
                    self.bots[bid]["elo_games"] = bd.get("elo_games", 0)
                    self.bots[bid]["elo_peak"] = bd.get("elo_peak", BASE_ELO)
                    self.bots[bid]["elo_recent"].extend(bd.get("elo_recent", []))
            print(f"[arena] restored {self.total_games} games from snapshot", flush=True)
        except Exception as exc:  # never let a bad snapshot kill startup
            print(f"[arena] snapshot load skipped: {exc}", flush=True)

    def save_snapshot(self):
        with self.lock:
            data = {
                "total_games": self.total_games,
                "total_turns": self.total_turns,
                "tallies": dict(self.tallies),
                "records": self.records,
                "bots": {str(b["bot_id"]): {
                    "wins": self.bots[b["bot_id"]]["wins"],
                    "games": self.bots[b["bot_id"]]["games"],
                    "best_streak": self.bots[b["bot_id"]]["best_streak"],
                    "deaths": self.bots[b["bot_id"]]["deaths"],
                    "first_outs": self.bots[b["bot_id"]]["first_outs"],
                    "place_sum": self.bots[b["bot_id"]]["place_sum"],
                    "place_games": self.bots[b["bot_id"]]["place_games"],
                    "elo": self.bots[b["bot_id"]]["elo"],
                    "elo_games": self.bots[b["bot_id"]]["elo_games"],
                    "elo_peak": self.bots[b["bot_id"]]["elo_peak"],
                    "elo_recent": list(self.bots[b["bot_id"]]["elo_recent"]),
                    "stats_version": self.bots[b["bot_id"]].get("stats_version", 1),
                } for b in ROSTER},
            }
        tmp = self.snap_shot_path + ".tmp"
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, self.snap_shot_path)
        except OSError as exc:
            print(f"[arena] snapshot save failed: {exc}", flush=True)


ARENA = Arena()


class LoserArena:
    """Biggest Loser variant: win = not last survivor; ELO rewards dying early.

    Finish order is inverted vs normal arena: death_seats (chronological) +
    [winner_seat], so rank 0 = first to explode = best loser. A "win" is
    recorded for any bot that is NOT the last survivor (i.e. didn't win the
    normal game).
    """

    def __init__(self, snap_shot_path=LOSER_SNAPSHOT_PATH):
        self.lock = threading.Lock()
        self.total_games = 0
        self.snap_shot_path = os.path.join(LOG_DIR, snap_shot_path)
        self.bots = {
            b["bot_id"]: {
                "wins": 0,       # first-to-explode count
                "no_wins": 0,    # games where bot was NOT last survivor
                "games": 0,
                "recent": deque(maxlen=SPARKLINE_MAX),
                "streak": 0, "best_streak": 0,
                "place_sum": 0, "place_games": 0,
                "elo": BASE_ELO, "elo_games": 0, "elo_peak": BASE_ELO,
                "elo_recent": deque(maxlen=ELO_TREND_MAX),
            }
            for b in ROSTER
        }
        self._load_snapshot()

    def record_game(self, seats, result, events):
        winner_seat = result["winner"]
        death_seats = [e["player"] for e in events if e["type"] == "explode"]

        # Inverted finish order: first-to-die is rank 0 (best loser)
        finish_seats = None
        if winner_seat >= 0 and len(death_seats) == len(seats) - 1:
            finish_seats = death_seats + [winner_seat]

        with self.lock:
            self.total_games += 1

            if finish_seats is not None:
                finish_bot_ids = [seats[s]["bot_id"] for s in finish_seats]
                if len(set(finish_bot_ids)) == len(finish_bot_ids):
                    self._update_elo(finish_bot_ids)
                    for place, bot_id in enumerate(finish_bot_ids):
                        self.bots[bot_id]["place_sum"] += place + 1
                        self.bots[bot_id]["place_games"] += 1

            first_out_bot_id = seats[death_seats[0]]["bot_id"] if death_seats else None
            winner_bot_id = seats[winner_seat]["bot_id"] if winner_seat >= 0 else None

            for bot_id in {b["bot_id"] for b in seats}:
                bd = self.bots[bot_id]
                bd["games"] += 1
                won = (bot_id != winner_bot_id)
                bd["recent"].append(1 if won else 0)
                if won:
                    bd["wins"] += 1
                    bd["streak"] += 1
                    bd["best_streak"] = max(bd["best_streak"], bd["streak"])
                else:
                    bd["streak"] = 0
                if bot_id != winner_bot_id:
                    bd["no_wins"] += 1

    def _update_elo(self, order):
        n = len(order)
        if n < 2:
            return
        pre = {bid: self.bots[bid]["elo"] for bid in order}
        place = {bid: i for i, bid in enumerate(order)}
        deltas = {}
        for a in order:
            expected = actual = 0.0
            for b in order:
                if a == b:
                    continue
                expected += 1.0 / (1.0 + 10 ** ((pre[b] - pre[a]) / 400.0))
                actual += 1.0 if place[a] < place[b] else 0.0
            k = (ELO_K_PROVISIONAL if self.bots[a]["elo_games"] < ELO_PROVISIONAL_GAMES
                 else ELO_K_ESTABLISHED)
            deltas[a] = k * (actual - expected) / (n - 1)
        for bid in order:
            bd = self.bots[bid]
            bd["elo"] += deltas[bid]
            bd["elo_games"] += 1
            bd["elo_peak"] = max(bd["elo_peak"], bd["elo"])
            bd["elo_recent"].append(round(bd["elo"], 1))

    def stats_payload(self):
        with self.lock:
            leaderboard = []
            for b in ROSTER:
                bd = self.bots[b["bot_id"]]
                games = bd["games"]
                leaderboard.append({
                    "bot_id": b["bot_id"], "name": b["name"], "emoji": b["emoji"],
                    "color": b["color"], "blurb": b["blurb"],
                    "author": b.get("author", "—"),
                    "elo": round(bd["elo"]), "elo_peak": round(bd["elo_peak"]),
                    "elo_games": bd["elo_games"],
                    "provisional": bd["elo_games"] < ELO_PROVISIONAL_GAMES,
                    "elo_recent": [round(x) for x in bd["elo_recent"]],
                    "avg_place": round(bd["place_sum"] / bd["place_games"], 3) if bd["place_games"] else None,
                    "wins": bd["wins"], "no_wins": bd["no_wins"], "games": games,
                    "win_rate": round(bd["wins"] / games, 4) if games else 0.0,
                    "no_win_rate": round(bd["no_wins"] / games, 4) if games else 0.0,
                    "recent": list(bd["recent"]),
                    "streak": bd["streak"], "best_streak": bd["best_streak"],
                })
            leaderboard.sort(key=lambda x: (x["elo"], x["wins"]), reverse=True)
            return {"total_games": self.total_games, "leaderboard": leaderboard}

    def rated_lineup(self, rng):
        """Top (PLAYERS_PER_GAME-1) by loser avg_place (lowest = explodes earliest) + 1 random."""
        def avg_place(b):
            bd = self.bots[b["bot_id"]]
            return bd["place_sum"] / bd["place_games"] if bd["place_games"] >= 20 else 3.0
        with self.lock:
            ordered = sorted(ROSTER, key=avg_place)
        n_top = min(EK_PLAYERS_PER_GAME - 1, len(ordered))
        top = ordered[:n_top]
        rest = ordered[n_top:]
        lineup = list(top)
        if rest:
            lineup.append(rng.choice(rest))
        pool = [b for b in ROSTER if b not in lineup]
        rng.shuffle(pool)
        while len(lineup) < EK_PLAYERS_PER_GAME and pool:
            lineup.append(pool.pop())
        rng.shuffle(lineup)
        return lineup

    def _load_snapshot(self):
        try:
            with open(self.snap_shot_path) as f:
                s = json.load(f)
        except (OSError, ValueError):
            return
        try:
            self.total_games = s.get("total_games", 0)
            for bid_str, bd in s.get("bots", {}).items():
                bid = int(bid_str)
                if bid in self.bots:
                    if bd.get("stats_version", 0) != LOSER_STATS_VERSION:
                        continue
                    self.bots[bid]["wins"] = bd.get("wins", 0)
                    self.bots[bid]["no_wins"] = bd.get("no_wins", 0)
                    self.bots[bid]["games"] = bd.get("games", 0)
                    self.bots[bid]["best_streak"] = bd.get("best_streak", 0)
                    self.bots[bid]["place_sum"] = bd.get("place_sum", 0)
                    self.bots[bid]["place_games"] = bd.get("place_games", 0)
                    self.bots[bid]["elo"] = bd.get("elo", BASE_ELO)
                    self.bots[bid]["elo_games"] = bd.get("elo_games", 0)
                    self.bots[bid]["elo_peak"] = bd.get("elo_peak", BASE_ELO)
                    self.bots[bid]["elo_recent"].extend(bd.get("elo_recent", []))
            print(f"[loser] restored {self.total_games} games from snapshot", flush=True)
        except Exception as exc:
            print(f"[loser] snapshot load skipped: {exc}", flush=True)

    def save_snapshot(self):
        with self.lock:
            data = {
                "total_games": self.total_games,
                "bots": {str(b["bot_id"]): {
                    "wins": self.bots[b["bot_id"]]["wins"],
                    "no_wins": self.bots[b["bot_id"]]["no_wins"],
                    "games": self.bots[b["bot_id"]]["games"],
                    "best_streak": self.bots[b["bot_id"]]["best_streak"],
                    "place_sum": self.bots[b["bot_id"]]["place_sum"],
                    "place_games": self.bots[b["bot_id"]]["place_games"],
                    "elo": self.bots[b["bot_id"]]["elo"],
                    "elo_games": self.bots[b["bot_id"]]["elo_games"],
                    "elo_peak": self.bots[b["bot_id"]]["elo_peak"],
                    "elo_recent": list(self.bots[b["bot_id"]]["elo_recent"]),
                    "stats_version": LOSER_STATS_VERSION,
                } for b in ROSTER},
            }
        tmp = self.snap_shot_path + ".tmp"
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, self.snap_shot_path)
        except OSError as exc:
            print(f"[loser] snapshot save failed: {exc}", flush=True)


LOSER_ARENA = LoserArena()


# --------------------------------------------------------------------------
# Background workers
# --------------------------------------------------------------------------
# Single-core, shared box, so we throttle the sim with a small per-game sleep
# that yields to the web server between games. Smaller = more games/s but less
# CPU left for the UI; the box is often contended by other users, so the real
# limiter is shared CPU, not this number. Override with EK_SLEEP; 0 = flat out.
GAME_SLEEP = float(os.environ.get("EK_SLEEP", "0.001"))   # more aggressive (was 0.004)

class ServerBackGroundThreadExecutor:
    """
    General server class used to hold the logic that runs various Agents and Engines
    """
    def __init__(self, players_per_game: int, arena, arena_bots, game_sleep: float,
                 loser_arena, log_prefix: str = ""):
        self.players_per_game: int = players_per_game
        self.arena = arena
        self.arena_bots = arena_bots
        self.game_sleep = game_sleep
        self.loser_arena = loser_arena
        self.log_prefix = log_prefix

    def _get_rooster(self):
        return [
            {"bot_id": i, "cls": cls, **cls.ARENA,
             "stats_version": max(cls.ARENA.get("stats_version", 0), GLOBAL_STATS_VERSION)}
            for i, cls in enumerate(self.arena_bots)
        ]

    def start_background_threads(self):
        for fn in (self.simulation_loop, self.rate_loop, self.snapshot_loop, self.prune_loop,
                   self.winrate_snapshot_loop, self.loser_simulation_loop, self.loser_snapshot_loop):
            threading.Thread(target=fn, daemon=True).start()

    def save_snapshot(self):
        self.arena.save_snapshot()

    def build_lineup(self, rng):
        """Random PLAYERS_PER_GAME lineup, preferring distinct agents.

        Fills the ring with distinct agents first (a random subset, randomly
        seated); only repeats an agent if the pool is smaller than the ring. With
        a 5-agent pool and a 5-seat ring every game uses each agent exactly once.
        """
        lineup, bag = [], []
        while len(lineup) < self.players_per_game:
            if not bag:                              # refill only when we run out of distinct agents
                bag = list(self._get_rooster())
                rng.shuffle(bag)
            lineup.append(bag.pop())
        rng.shuffle(lineup)                          # randomize seat order
        return lineup


    def simulation_loop(self):
        rng = random.Random()
        while True:
            # Rated ladder: top bots by ELO + a random challenger each game.
            seats = self.arena.rated_lineup(rng)
            # Fresh agent instance per seat so a repeated agent never shares state
            # across two seats in the same game.
            seat_agents = [b["cls"](name=b["name"]) for b in seats]
            engine = GameEngine(seat_agents, seed=None, collect_events=True)
            result = engine.play_game(len(seats))
            self.arena.record_game(seats, result, result["events"])
            if GAME_SLEEP:
                time.sleep(GAME_SLEEP)


    def rate_loop(self):
        while True:
            time.sleep(2)
            self.arena.sample_rate()


    def snapshot_loop(self):
        while True:
            time.sleep(30)
            self.arena.save_snapshot()


    def prune_loop(self):
        while True:
            time.sleep(300)
            prune_logs()

    def winrate_snapshot_loop(self):
        """Append a tab-separated snapshot of per-bot win rates every 60 seconds.

        Each row: timestamp<TAB>total_games<TAB>bot_name:wins:games:win_rate:elo ...
        Rows are append-only so resets / roster changes don't erase history.
        """
        os.makedirs(LOG_DIR, exist_ok=True)
        win_rate_history_path = os.path.join(LOG_DIR, self.log_prefix + WINRATE_HISTORY_PATH)

        # Write header on first run if the file is new.
        if not os.path.exists(win_rate_history_path):
            try:
                with open(win_rate_history_path, "w") as f:
                    f.write("timestamp\ttotal_games\tbots\n")
            except OSError:
                pass
        while True:
            time.sleep(60)
            try:
                with ARENA.lock:
                    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                    total = ARENA.total_games
                    parts = []
                    for b in ROSTER:
                        bd = ARENA.bots[b["bot_id"]]
                        g = bd["games"]
                        wr = round(bd["wins"] / g, 4) if g else 0.0
                        parts.append(f"{b['name']}:{bd['wins']}:{g}:{wr}:{round(bd['elo'])}")
                row = ts + "\t" + str(total) + "\t" + "|".join(parts) + "\n"
                with open(win_rate_history_path, "a") as f:
                    f.write(row)
            except Exception as exc:
                print(f"[winrate] snapshot failed: {exc}", flush=True)


    def loser_simulation_loop(self):
        rng = random.Random()
        while True:
            seats = self.loser_arena.rated_lineup(rng)
            seat_agents = [b["cls"](name=b["name"]) for b in seats]
            engine = GameEngine(seat_agents, seed=None, collect_events=True)
            result = engine.play_game(len(seats))
            LOSER_ARENA.record_game(seats, result, result["events"])
            if GAME_SLEEP:
                time.sleep(GAME_SLEEP)


    def loser_snapshot_loop(self):
        while True:
            time.sleep(30)
            self.loser_arena.save_snapshot()


def prune_logs():
    """Keep logs/ bounded: cap *.jsonl file count and total directory size."""
    try:
        files = []
        for name in os.listdir(LOG_DIR):
            if not name.endswith(".jsonl"):
                continue
            path = os.path.join(LOG_DIR, name)
            try:
                files.append((path, os.path.getmtime(path), os.path.getsize(path)))
            except OSError:
                continue
        files.sort(key=lambda x: x[1], reverse=True)   # newest first

        removed = 0
        # cap by count
        for path, _, _ in files[MAX_LOG_FILES:]:
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
        kept = files[:MAX_LOG_FILES]
        # cap by total size (drop oldest until under cap)
        total = sum(sz for _, _, sz in kept)
        while kept and total > MAX_LOG_DIR_BYTES:
            path, _, sz = kept.pop()
            try:
                os.remove(path)
                removed += 1
                total -= sz
            except OSError:
                break
        if removed:
            print(f"[prune] removed {removed} old log file(s)", flush=True)
    except OSError as exc:
        print(f"[prune] skipped: {exc}", flush=True)


# --------------------------------------------------------------------------
# Training progress — parse log files written by training runs
# --------------------------------------------------------------------------
import re as _re

_TRAIN_LOGS = {
    "Rhino":    "/tmp/rhino_train.log",
    "Gorilla":  "/tmp/gorilla_train.log",
    "Elephant": "/tmp/elephant_train.log",
}
_BESTS_FILES = {
    "Rhino":    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'training', 'rhino',    'bests.jsonl'),
    "Gorilla":  os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'training', 'gorilla',  'bests.jsonl'),
    "Elephant": os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'training', 'elephant', 'bests.jsonl'),
}
_ITER_RE = _re.compile(
    r"iter\s+(\d+)\s+rollout_win\s+([\d.]+)%.*?win\s+([\d.]+)%\s+place\s+([\d.]+).*?\(best\s+([\d.]+)%\)"
)

def _training_progress():
    import json as _json
    out = {}
    for name, path in _TRAIN_LOGS.items():
        points = []
        try:
            with open(path) as f:
                for line in f:
                    m = _ITER_RE.search(line)
                    if m:
                        points.append({
                            "iter":  int(m.group(1)),
                            "rwin":  float(m.group(2)),
                            "win":   float(m.group(3)),
                            "place": float(m.group(4)),
                            "best":  float(m.group(5)),
                        })
        except OSError:
            pass
        bests = []
        try:
            with open(_BESTS_FILES[name]) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        bests.append(_json.loads(line))
        except OSError:
            pass
        out[name] = {"points": points, "bests": bests}
    return out


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def _send(self, body, content_type="application/json", winrate_prefix = ""):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        self.winrate_prefix = winrate_prefix

    def do_GET(self):
        from urllib.parse import urlsplit, parse_qs
        u = urlsplit(self.path); path = u.path; q = parse_qs(u.query)
        if path == "/" or path == "/index.html":
            self._send(PAGE, "text/html")
        elif path == "/play":
            self._send(PLAY_PAGE, "text/html")
        elif path == "/api/stats":
            self._send(json.dumps(ARENA.stats_payload()))
        elif path == "/api/showcase":
            payload = ARENA.showcase_payload()
            self._send(json.dumps(payload) if payload else "null")
        elif path == "/api/play/bots":
            self._send(json.dumps([{"name": n, "emoji": play.PLAYABLE[n][1]}
                                    for n in play.PUBLIC_BOTS]))
        elif path == "/api/play/state":
            self._send(json.dumps(play.state(q.get("id", [""])[0])))
        elif path == "/daniel":
            self._send(DEBUG_PAGE, "text/html")
        elif path == "/api/training":
            self._send(json.dumps(_training_progress()))
        elif path == "/api/debug/deploy_log":
            try:
                with open("/tmp/ek-auto-deploy.log") as f:
                    self._send(f.read(), "text/plain")
            except OSError:
                self._send("log not found", "text/plain")
        elif path == "/api/version":
            self._send(json.dumps({"build": SERVER_INSTANCE_ID}))
        elif path == "/api/loser_stats":
            self._send(json.dumps(LOSER_ARENA.stats_payload()))
        elif path == "/api/winrate_history":
            winrate_history_path = os.path.join(LOG_DIR, self.winrate_prefix + WINRATE_HISTORY_PATH)
            try:
                with open(winrate_history_path) as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/tab-separated-values; charset=utf-8")
                self.send_header("Content-Length", str(len(data.encode())))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(data.encode())
                return
            except OSError:
                self._send(json.dumps({"error": "no history yet"}))
        elif path == "/health":
            self._send(json.dumps({"status": "ok", "games": ARENA.total_games}))
        else:
            self._send(json.dumps({"error": "not found"}))

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or "{}")
        except (ValueError, TypeError):
            body = {}
        if path == "/api/play/new":
            self._send(json.dumps(play.new_session(body.get("opponents", []))))
        elif path == "/api/play/act":
            self._send(json.dumps(play.act(body.get("id", ""), int(body.get("index", 0)))))
        else:
            self._send(json.dumps({"error": "not found"}))

    def log_message(self, fmt, *args):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8767
    game = int(sys.argv[2]) if len(sys.argv) > 2 else "ek"

    os.makedirs(LOG_DIR, exist_ok=True)
    prune_logs()
    sever_background_thread_executor = ServerBackGroundThreadExecutor(
        EK_PLAYERS_PER_GAME,ARENA, ARENA_BOTS, GAME_SLEEP, LOSER_ARENA
    )
    sever_background_thread_executor.start_background_threads()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Exploding Kittens Arena live at http://0.0.0.0:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sever_background_thread_executor.save_snapshot()
        print("\nbye", flush=True)


# PAGE is defined in dashboard_page.py to keep this file readable.
from web.dashboard_page import PAGE  # noqa: E402
from web.debug_page import DEBUG_PAGE  # noqa: E402
from web.play_page import PLAY_PAGE  # noqa: E402
from web import play  # noqa: E402

if __name__ == "__main__":
    main()
