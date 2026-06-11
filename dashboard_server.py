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
    python3 dashboard_server.py [PORT]      # default 8767

Meant to sit next to the protocol docs (protocol_server.py, port 8766).
"""
import json
import os
import random
import sys
import threading
import time
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.random_agent import RandomAgent
from agents.heuristic_agent import HeuristicAgent
from agents.aggressive_agent import AggressiveAgent
from agents.chaos_agent import ChaosAgent
from game.engine import GameEngine

# --------------------------------------------------------------------------
# Roster — stable bot identities. Each plays a rotating seat every game so no
# bot gets a permanent turn-order advantage.
# --------------------------------------------------------------------------
ROSTER = [
    {"bot_id": 0, "name": "Professor", "emoji": "\U0001F9E0", "color": "#818cf8",
     "cls": HeuristicAgent, "blurb": "Counts cards, plays the odds."},
    {"bot_id": 1, "name": "Maverick", "emoji": "\U0001F4A5", "color": "#f97316",
     "cls": AggressiveAgent, "blurb": "Attack first, ask never."},
    {"bot_id": 2, "name": "Gremlin", "emoji": "\U0001F300", "color": "#4ade80",
     "cls": ChaosAgent, "blurb": "An agent of pure chaos."},
    {"bot_id": 3, "name": "Lucky", "emoji": "\U0001F3B2", "color": "#f472b6",
     "cls": RandomAgent, "blurb": "No plan. Just vibes."},
]
N_PLAYERS = len(ROSTER)

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
SNAPSHOT_PATH = os.path.join(LOG_DIR, "dashboard_state.json")
REPLAY_BUFFER_MAX = 40           # detailed games kept for replay
RECENT_RESULTS_MAX = 14          # entries in the results feed
SPARKLINE_MAX = 30               # recent W/L tracked per bot
MAX_LOG_FILES = 8                # *.jsonl files kept in logs/
MAX_LOG_DIR_BYTES = 200 * 1024 * 1024


class Arena:
    """Holds all shared state. Guarded by a single lock."""

    def __init__(self):
        self.lock = threading.Lock()
        self.started_at = time.time()
        self.total_games = 0
        self.total_turns = 0
        self.games_per_sec = 0.0
        self._rate_sample = (self.started_at, 0)        # (time, total_games)

        # per-bot aggregate, keyed by bot_id
        self.bots = {
            b["bot_id"]: {
                "wins": 0, "games": 0,
                "recent": deque(maxlen=SPARKLINE_MAX),  # 1 win / 0 loss
                "streak": 0, "best_streak": 0,
                "deaths": 0, "first_outs": 0,
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

        with self.lock:
            self.total_games += 1
            self.total_turns += result["turns"]

            for k, v in ev_counts.items():
                self.tallies[k] += v

            for seat, bot in enumerate(seats):
                bd = self.bots[bot["bot_id"]]
                bd["games"] += 1
                won = (seat == winner_seat)
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
                    "wins": bd["wins"], "games": games,
                    "win_rate": round(bd["wins"] / games, 4) if games else 0.0,
                    "recent": list(bd["recent"]),
                    "streak": bd["streak"], "best_streak": bd["best_streak"],
                    "first_outs": bd["first_outs"],
                })
            leaderboard.sort(key=lambda x: (x["win_rate"], x["wins"]), reverse=True)

            return {
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

    # ----------------------------------------------------------- persistence
    def _load_snapshot(self):
        try:
            with open(SNAPSHOT_PATH) as f:
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
                    self.bots[bid]["wins"] = bd.get("wins", 0)
                    self.bots[bid]["games"] = bd.get("games", 0)
                    self.bots[bid]["best_streak"] = bd.get("best_streak", 0)
                    self.bots[bid]["deaths"] = bd.get("deaths", 0)
                    self.bots[bid]["first_outs"] = bd.get("first_outs", 0)
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
                } for b in ROSTER},
            }
        tmp = SNAPSHOT_PATH + ".tmp"
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, SNAPSHOT_PATH)
        except OSError as exc:
            print(f"[arena] snapshot save failed: {exc}", flush=True)


ARENA = Arena()


# --------------------------------------------------------------------------
# Background workers
# --------------------------------------------------------------------------
# The engine runs ~1500 games/s on one core. We throttle to keep the box cool
# and let the live counter tick at a watchable pace. Override with EK_SLEEP.
GAME_SLEEP = float(os.environ.get("EK_SLEEP", "0.02"))   # ~50 games/sec


def simulation_loop():
    agents = [b["cls"](name=b["name"]) for b in ROSTER]
    rng = random.Random()
    while True:
        order = list(range(N_PLAYERS))
        rng.shuffle(order)                       # rotate seats
        seats = [ROSTER[i] for i in order]
        seat_agents = [agents[i] for i in order]
        engine = GameEngine(seat_agents, seed=None, collect_events=True)
        result = engine.play_game(N_PLAYERS)
        ARENA.record_game(seats, result, result["events"])
        if GAME_SLEEP:
            time.sleep(GAME_SLEEP)


def rate_loop():
    while True:
        time.sleep(2)
        ARENA.sample_rate()


def snapshot_loop():
    while True:
        time.sleep(30)
        ARENA.save_snapshot()


def prune_loop():
    while True:
        time.sleep(300)
        prune_logs()


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
# HTTP
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def _send(self, body, content_type="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/" or path == "/index.html":
            self._send(PAGE, "text/html")
        elif path == "/api/stats":
            self._send(json.dumps(ARENA.stats_payload()))
        elif path == "/api/showcase":
            payload = ARENA.showcase_payload()
            self._send(json.dumps(payload) if payload else "null")
        elif path == "/health":
            self._send(json.dumps({"status": "ok", "games": ARENA.total_games}))
        else:
            self._send(json.dumps({"error": "not found"}))

    def log_message(self, fmt, *args):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8767
    os.makedirs(LOG_DIR, exist_ok=True)
    prune_logs()
    for fn in (simulation_loop, rate_loop, snapshot_loop, prune_loop):
        threading.Thread(target=fn, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Exploding Kittens Arena live at http://0.0.0.0:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        ARENA.save_snapshot()
        print("\nbye", flush=True)


# PAGE is defined in dashboard_page.py to keep this file readable.
from dashboard_page import PAGE  # noqa: E402

if __name__ == "__main__":
    main()
