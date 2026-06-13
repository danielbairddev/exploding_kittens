"""Gabriel uses the same GRU-128 architecture as Elephant — just re-exported."""
from training.elephant.net import (  # noqa: F401
    GRUActorCritic, GRU_H, H1, H2, N_MLP_IN,
    N_TARGETS, N_CARD_TYPES, N_BUCKETS, BUCKET_FRACS,
    GRU_KEYS, TRUNK_KEYS, POLICY_KEYS_H, AUX_KEYS, ALL_KEYS, POLICY_KEYS,
)
