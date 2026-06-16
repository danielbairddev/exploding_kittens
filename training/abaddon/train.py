#!/usr/bin/env python3
"""Abaddon ian_folder — Gorilla's tracker / opponent-modeling / explicit-ID PPO
pipeline with the belief-state encoder (abaddon.features.encode_a).

We set EK_ENCODER=abaddon *before* importing gorilla.train_g, so the pipeline
(and the spawned rollout workers, which inherit the env var and re-import the
module) all use encode_a. We only override the checkpoint output paths.

    python3 -m abaddon.train --iters 3000 --workers 8
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ["EK_ENCODER"] = "abaddon"          # must be set before the import below

import training.gorilla.train_g as tg                   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
tg.BEST_OUT = os.path.join(HERE, "best_policy_a.json")
tg.CKPT_OUT = os.path.join(HERE, "checkpoint_a.json")

if __name__ == "__main__":
    tg.main()
