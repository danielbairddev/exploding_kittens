#!/usr/bin/env python3
"""
HTTP server that exposes an Agent via JSON endpoints.

Run as:
  python agents/agent_server.py --agent heuristic --port 5001 --name "Bot-1"

Endpoints (all POST, all JSON):
  POST /game_start               {state}
  POST /choose_action            {state, valid_actions} -> {action}
  POST /want_to_nope             {state, action}        -> {nope: bool}
  POST /give_card                {state, requester_id}  -> {card_type: str}
  POST /place_exploding_kitten   {state, deck_size}     -> {position: int}
  POST /see_future               {state, top3}
  GET  /health                                          -> {status: "ok"}

Implement these same endpoints in any language to build a custom agent.
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify
from protocol.schema import (
    dict_to_observable, dict_to_action, dict_to_card,
    action_to_dict, card_type_to_str,
)

app = Flask(__name__)
_agent = None


def _get_agent():
    return _agent


@app.get("/health")
def health():
    return jsonify({"status": "ok", "name": getattr(_agent, "name", "unknown")})


@app.post("/game_start")
def game_start():
    data = request.get_json()
    _agent.game_start(dict_to_observable(data["state"]))
    return jsonify({})


@app.post("/choose_action")
def choose_action():
    data = request.get_json()
    state = dict_to_observable(data["state"])
    valid_actions = [dict_to_action(a) for a in data["valid_actions"]]
    action = _agent.choose_action(state, valid_actions)
    return jsonify(action_to_dict(action))


@app.post("/want_to_nope")
def want_to_nope():
    data = request.get_json()
    state = dict_to_observable(data["state"])
    action = dict_to_action(data["action"])
    result = _agent.want_to_nope(state, action)
    return jsonify({"nope": bool(result)})


@app.post("/give_card")
def give_card():
    data = request.get_json()
    state = dict_to_observable(data["state"])
    card_type = _agent.give_card(state, data["requester_id"])
    return jsonify({"card_type": card_type_to_str(card_type)})


@app.post("/place_exploding_kitten")
def place_exploding_kitten():
    data = request.get_json()
    state = dict_to_observable(data["state"])
    position = _agent.place_exploding_kitten(state, data["deck_size"])
    return jsonify({"position": int(position)})


@app.post("/see_future")
def see_future():
    data = request.get_json()
    state = dict_to_observable(data["state"])
    top3 = [dict_to_card(c) for c in data["top3"]]
    _agent.see_future(state, top3)
    return jsonify({})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Exploding Kittens agent HTTP server")
    parser.add_argument("--agent", choices=["random", "heuristic", "aggressive", "chaos"], default="heuristic")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--name", default=None)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    if args.agent == "random":
        from agents.random_agent import RandomAgent
        _agent = RandomAgent(name=args.name or f"Random@{args.port}", seed=args.seed)
    elif args.agent == "heuristic":
        from agents.heuristic_agent import HeuristicAgent
        _agent = HeuristicAgent(name=args.name or f"Heuristic@{args.port}", seed=args.seed)
    elif args.agent == "aggressive":
        from agents.aggressive_agent import AggressiveAgent
        _agent = AggressiveAgent(name=args.name or f"Aggressive@{args.port}", seed=args.seed)
    elif args.agent == "chaos":
        from agents.chaos_agent import ChaosAgent
        _agent = ChaosAgent(name=args.name or f"Chaos@{args.port}", seed=args.seed)

    print(f"[agent-server] {_agent.name} ({args.agent}) listening on port {args.port}", flush=True)
    app.run(host="127.0.0.1", port=args.port, debug=False)
