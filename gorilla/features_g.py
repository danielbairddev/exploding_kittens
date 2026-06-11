"""Gorilla encoder: Orangutan's 52 features + opponent modeling + danger.

Requires a GameTracker (accumulated across the game from the agent's callbacks)
so it can add per-opponent behavior profiles — the signal that lets Gorilla
*exploit* specific opponents rather than play one fixed strategy.
"""
from agents.orangutan_features import encode as encode_base
from gorilla.tracker import _PROFILE, EK, DEF

# base 52 + (7 action-rates + activity) x 4 next opponents + refined danger
N_FEATURES_G = 52 + (len(_PROFILE) + 1) * 4 + 1   # = 85


def encode_g(state, tracker, known_top=None):
    f = list(encode_base(state, known_top))                      # 52

    # Per-opponent behavior profiles, in turn order (next up to 4 opponents).
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
        else:
            f += [0.0] * (len(_PROFILE) + 1)

    # Refined danger: P(top card is an Exploding Kitten).
    top = tracker.known_top(state)
    if top:
        f.append(1.0 if top[0] == EK else 0.0)
    else:
        f.append((len(state.alive_players) - 1) / max(1, state.deck_size))

    return f                                                     # len 85
