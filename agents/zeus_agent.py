"""Zeus — the win-seeking twin of Hades.

Identical Transformer architecture and features as Hades (see agents/hades_agent.py
and training/hades/), but trained with the *opposite* objective: maximise win rate.
Reward is +1 for being the sole survivor, -1 otherwise — no placement/anti-logic,
no dense shaping. The two are Olympian brothers: Hades races to die, Zeus to win.

Because the forward pass is byte-for-byte the same as Hades, ZeusAgent simply
subclasses HadesAgent and swaps the weights file + arena identity.

Currently BENCHED — not in web/dashboard_server.py ARENA_BOTS. Train with
`training/zeus/run_full_training.sh`, then enable once it's competitive.
"""
import os

from agents.hades_agent import HadesAgent, _load_net

_ZEUS_WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'zeus_weights.json')


class ZeusAgent(HadesAgent):
    ARENA = {
        'name': 'Zeus',
        'emoji': '⚡',
        'color': '#f59e0b',
        'blurb': 'King of Olympus — same Transformer as Hades, but plays only to win.',
        'author': 'Daniel Baird',
        'llm_assisted': True,
        'stats_version': 1,
    }

    # Load Zeus's own weights at class definition (HadesAgent's machinery, our file).
    _NET = _load_net(_ZEUS_WEIGHTS_PATH)

    def __init__(self, name='Zeus', seed=None):
        super().__init__(name=name, seed=seed)
