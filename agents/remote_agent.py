"""
Agent implementation that delegates every decision to a remote HTTP server.

The game engine calls this like any other agent; it transparently forwards
calls over JSON/HTTP to whatever process is listening at `url`.
This is what makes agents language-agnostic — the remote server can be
Python, Go, Rust, JS, anything that speaks HTTP and the protocol schema.
"""
import requests
from agents.base import Agent
from game.state import ObservableState
from game.actions import Action
from game.cards import CardType
from protocol.schema import (
    observable_to_dict, action_to_dict, dict_to_action,
    card_to_dict, str_to_card_type,
)


class RemoteAgent(Agent):
    def __init__(self, url: str, name: str = "Remote", timeout: float = 5.0):
        self.url = url.rstrip("/")
        self.name = name
        self._timeout = timeout
        self._session = requests.Session()

    def _post(self, endpoint: str, payload: dict) -> dict:
        resp = self._session.post(
            f"{self.url}/{endpoint}",
            json=payload,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def game_start(self, state: ObservableState):
        self._post("game_start", {"state": observable_to_dict(state)})

    def choose_action(self, state: ObservableState, valid_actions: list[Action]) -> Action:
        result = self._post("choose_action", {
            "state": observable_to_dict(state),
            "valid_actions": [action_to_dict(a) for a in valid_actions],
        })
        return dict_to_action(result)

    def want_to_nope(self, state: ObservableState, action: Action, currently_noped: bool = False) -> bool:
        result = self._post("want_to_nope", {
            "state": observable_to_dict(state),
            "action": action_to_dict(action),
            "currently_noped": currently_noped,
        })
        return bool(result.get("nope", False))

    def give_card(self, state: ObservableState, requester_id: int) -> CardType:
        result = self._post("give_card", {
            "state": observable_to_dict(state),
            "requester_id": requester_id,
        })
        return str_to_card_type(result["card_type"])

    def place_exploding_kitten(self, state: ObservableState, deck_size: int) -> int:
        result = self._post("place_exploding_kitten", {
            "state": observable_to_dict(state),
            "deck_size": deck_size,
        })
        return int(result["position"])

    def see_future(self, state: ObservableState, top3: list):
        self._post("see_future", {
            "state": observable_to_dict(state),
            "top3": [card_to_dict(c) for c in top3],
        })
