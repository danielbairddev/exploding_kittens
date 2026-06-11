"""Feature encoding + action vocabulary for the Orangutan neural-net agent.

Pure stdlib so the deployed agent has no third-party dependency. The trainer
(numpy) and the agent (pure-Python forward pass) both import this so training
and inference see identical features.
"""
from game.actions import Action, ActionType
from game.cards import CardType

# Card types we count in hand / discard (Exploding Kitten can't be in either).
_COUNT_TYPES = [
    CardType.DEFUSE, CardType.ATTACK, CardType.SKIP, CardType.FAVOR,
    CardType.SHUFFLE, CardType.SEE_THE_FUTURE, CardType.NOPE,
    CardType.TACO_CAT, CardType.HAIRY_POTATO_CAT, CardType.BEARD_CAT,
    CardType.RAINBOW_CAT, CardType.CATTERMELON,
]
EK = CardType.EXPLODING_KITTEN
DEF = CardType.DEFUSE

# Fixed action vocabulary the network chooses among. Targets / named cards are
# resolved heuristically (biggest hand; triples demand a Defuse) so the policy
# only has to pick an action *type*.
ACTIONS = [
    ActionType.DRAW,
    ActionType.PLAY_SKIP,
    ActionType.PLAY_ATTACK,
    ActionType.PLAY_SHUFFLE,
    ActionType.PLAY_SEE_THE_FUTURE,
    ActionType.PLAY_FAVOR,
    ActionType.PLAY_CAT_PAIR,
    ActionType.PLAY_CAT_TRIPLE,
]
N_ACTIONS = len(ACTIONS)
N_FEATURES = 35


def encode(state, known_top=None):
    """ObservableState (+ optional known top-3 CardType list) -> list[float]."""
    hand = [c.card_type for c in state.my_hand]
    hand_ct = {t: 0 for t in _COUNT_TYPES}
    for t in hand:
        if t in hand_ct:
            hand_ct[t] += 1
    disc_ct = {t: 0 for t in _COUNT_TYPES}
    for c in state.discard_pile:
        if c.card_type in disc_ct:
            disc_ct[c.card_type] += 1

    f = []
    f += [hand_ct[t] / 4.0 for t in _COUNT_TYPES]        # 12
    f += [disc_ct[t] / 6.0 for t in _COUNT_TYPES]        # 12
    deck = max(1, state.deck_size)
    alive = max(1, len(state.alive_players))
    opp = [h for pid, h in state.hand_sizes.items() if pid != state.my_id]
    f.append(state.deck_size / 30.0)                     # deck size
    f.append(1.0 if state.turns_remaining > 1 else 0.0)  # under attack
    f.append(alive / 5.0)                                # players alive
    f.append(len(hand) / 12.0)                           # my hand size
    f.append((max(opp) if opp else 0) / 12.0)            # biggest opponent
    f.append((min(opp) if opp else 0) / 12.0)            # smallest opponent
    f.append((sum(opp) / len(opp) if opp else 0) / 12.0)  # avg opponent
    f.append((alive - 1) / deck)                         # EK density
    # known top (from See the Future): known?, top0 is EK?, EK anywhere in top3?
    if known_top:
        f.append(1.0)
        f.append(1.0 if known_top[0] == EK else 0.0)
        f.append(1.0 if any(c == EK for c in known_top) else 0.0)
    else:
        f += [0.0, 0.0, 0.0]
    return f                                             # len 35


def valid_action_mask(valid_actions):
    """Boolean mask over ACTIONS for which types are currently legal."""
    present = {a.action_type for a in valid_actions}
    return [1.0 if at in present else 0.0 for at in ACTIONS]


def resolve_action(idx, by_type, best_target):
    """Turn a chosen action index into a concrete Action.

    by_type: {ActionType: [Action,...]} from the engine's valid_actions.
    best_target: fn(list[Action], state)->Action picking the biggest-hand target.
    """
    from dataclasses import replace
    at = ACTIONS[idx]
    acts = by_type.get(at)
    if not acts:
        return Action(ActionType.DRAW)
    if at == ActionType.PLAY_CAT_TRIPLE:
        return replace(acts[0], named_card=DEF)  # caller may re-target first
    return acts[0]
