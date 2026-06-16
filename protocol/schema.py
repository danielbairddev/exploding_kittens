"""
JSON serialization for all game objects.

This is the wire format agents must speak when running as separate processes.
Implement these same shapes in any language to build an agent.

Card:         {"card_type": "ATTACK"}
Action:       {"action_type": "PLAY_ATTACK", "target_player": null,
               "cat_type": null, "named_card": null, "defuse_position": null}
ObservableState: see observable_to_dict() below
"""
from game.cards import Card, CardType
from game.actions import Action, ActionType
from game.state import ObservableState


def card_to_dict(card: Card) -> dict:
    return {"card_type": card.card_type.name}


def dict_to_card(d: dict) -> Card:
    return Card(CardType[d["card_type"]])


def action_to_dict(action: Action) -> dict:
    return {
        "action_type": action.action_type.name,
        "target_player": action.target_player,
        "cat_type": action.cat_type.name if action.cat_type else None,
        "named_card": action.named_card.name if action.named_card else None,
        "defuse_position": action.defuse_position,
    }


def dict_to_action(d: dict) -> Action:
    return Action(
        action_type=ActionType[d["action_type"]],
        target_player=d.get("target_player"),
        cat_type=CardType[d["cat_type"]] if d.get("cat_type") else None,
        named_card=CardType[d["named_card"]] if d.get("named_card") else None,
        defuse_position=d.get("defuse_position"),
    )


def observable_to_dict(state: ObservableState) -> dict:
    return {
        "my_id": state.my_id,
        "my_hand": [card_to_dict(c) for c in state.my_hand],
        "hand_sizes": state.hand_sizes,
        "alive_players": state.alive_players,
        "deck_size": state.deck_size,
        "deck_exploding_kittens_count": state.deck_exploding_kittens_count,
        "discard_pile": [card_to_dict(c) for c in state.discard_pile],
        "turns_remaining": state.turns_remaining,
        "current_player": state.current_player,
        "recent_events": list(state.recent_events),
        "known_top3": [card_to_dict(c) for c in state.known_top3] if state.known_top3 else None,
    }


def dict_to_observable(d: dict) -> ObservableState:
    return ObservableState(
        my_id=d["my_id"],
        my_hand=[dict_to_card(c) for c in d["my_hand"]],
        hand_sizes={int(k): v for k, v in d["hand_sizes"].items()},
        alive_players=d["alive_players"],
        deck_size=d["deck_size"],
        deck_exploding_kittens_count=d.get(
            "deck_exploding_kittens_count",
            max(0, len(d["alive_players"]) - 1),
        ),
        discard_pile=[dict_to_card(c) for c in d["discard_pile"]],
        turns_remaining=d["turns_remaining"],
        current_player=d["current_player"],
        recent_events=list(d.get("recent_events", [])),
        known_top3=[dict_to_card(c) for c in d["known_top3"]] if d.get("known_top3") else None,
    )


def card_type_to_str(ct: CardType) -> str:
    return ct.name


def str_to_card_type(s: str) -> CardType:
    return CardType[s]
