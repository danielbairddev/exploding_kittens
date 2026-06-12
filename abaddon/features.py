"""Abaddon encoder: Gorilla's encode_g + an explicit belief block.

The oracle test showed perfect top-of-deck knowledge is the only real headroom
(40% -> 44%), so Abaddon gets the most relevant slice of that as *probabilities*:
the chance an Exploding Kitten sits in the next 1/2/3 cards (exact when we've
peeked, hypergeometric otherwise). MLPs can't derive these from raw counts, so
we hand them over.
"""
from math import comb

from gorilla.features_g import encode_g, N_FEATURES_G
from gorilla.tracker import EK

N_FEATURES_A = N_FEATURES_G + 3   # + p(EK in top1/top2/top3)


def _p_ek_in_top(ek, deck, n):
    if ek <= 0 or deck <= 0:
        return 0.0
    if ek >= deck or n >= deck:
        return 1.0
    return 1.0 - comb(deck - ek, n) / comb(deck, n)


def encode_a(state, tracker, known_top=None):
    f = list(encode_g(state, tracker, known_top))
    top = tracker.known_top(state)
    deck = max(1, state.deck_size)
    ek = max(0, len(state.alive_players) - 1)
    for n in (1, 2, 3):
        if top is not None and len(top) >= n:
            f.append(1.0 if any(c == EK for c in top[:n]) else 0.0)  # exact
        else:
            f.append(_p_ek_in_top(ek, deck, n))                      # estimated
    return f
