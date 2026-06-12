"""Gorilla encoder: Orangutan's 52 features + opponent modeling + danger.

Requires a GameTracker (accumulated across the game from the agent's callbacks)
so it can add per-opponent behavior profiles — the signal that lets Gorilla
*exploit* specific opponents rather than play one fixed strategy.
"""
from agents.orangutan_features import encode as encode_base
from training.gorilla.tracker import _PROFILE, EK, DEF

# Known opponent identities. Index 0 = unknown/anonymized (heuristic fallback).
# Training can pass the real type so the net learns per-opponent best responses;
# at deploy we pass it when we know the roster, else leave it unknown.
TYPE_VOCAB = ["unknown", "RandomAgent", "HeuristicAgent", "AggressiveAgent",
              "ChaosAgent", "SurvivalAgent", "SurvivalAgentV2", "CoyoteAgent",
              "OrangutanAgent", "GorillaAgent", "AbaddonAgent"]
TYPE_INDEX = {n: i for i, n in enumerate(TYPE_VOCAB)}
N_TYPES = len(TYPE_VOCAB)

# base 52 + (7 action-rates + activity + type one-hot) x 4 next opponents + danger
N_FEATURES_G = 52 + (len(_PROFILE) + 1 + N_TYPES) * 4 + 1   # = 129


def encode_g(state, tracker, known_top=None):
    f = list(encode_base(state, known_top))                      # 52

    order = sorted(state.alive_players)
    if state.my_id in order:
        i = order.index(state.my_id)
        ring = order[i + 1:] + order[:i]
    else:
        ring = order
    for k in range(4):
        if k < len(ring):
            pid = ring[k]
            prof = tracker.opp_profile(pid)
            f += [prof[a] for a in _PROFILE]                     # 7 action rates
            f.append(min(tracker.total_plays.get(pid, 0), 20) / 20.0)  # activity
            # explicit identity one-hot (unknown if not provided)
            onehot = [0.0] * N_TYPES
            onehot[TYPE_INDEX.get(tracker.opp_types.get(pid, "unknown"), 0)] = 1.0
            f += onehot                                          # N_TYPES
        else:
            f += [0.0] * (len(_PROFILE) + 1 + N_TYPES)

    top = tracker.known_top(state)
    if top:
        f.append(1.0 if top[0] == EK else 0.0)
    else:
        f.append((len(state.alive_players) - 1) / max(1, state.deck_size))

    return f                                                     # len 129
