#!/usr/bin/env python3
"""Train the Perdition policy network to lose — minimise win rate, not placement.

Same MLP architecture as Orangutan (52 -> 64 -> 32 -> 8), but the reward is
binary: 0.0 if Perdition wins, 1.0 for any loss.  Placement among losers is not
optimised.  No behavioural-cloning warm-start (we don't want it imitating a
good player).

    python3 ian_folder/train_perdition.py --batches 4000

Progress lines report Perdition's greedy loss% (= 100 - win%) and average place.
"""
import argparse
import json
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.coyote_agent import CoyoteAgent
from agents.survival_agent import SurvivalAgent
from agents.survival_agent_v2 import SurvivalAgentV2
from agents.aggressive_agent import AggressiveAgent
from agents.chaos_agent import ChaosAgent
from agents.heuristic_agent import HeuristicAgent
from agents.random_agent import RandomAgent
from agents.orangutan_agent import OrangutanAgent
from agents.orangutan_features import encode, ACTIONS, N_FEATURES, N_ACTIONS
from game.engine import GameEngine
from game.actions import Action, ActionType
from game.cards import CardType

DEF = CardType.DEFUSE
WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents", "perdition_weights.json")
FLEET = [CoyoteAgent, SurvivalAgentV2, SurvivalAgent, AggressiveAgent,
         ChaosAgent, HeuristicAgent, RandomAgent, OrangutanAgent]
H1, H2 = 64, 32
NEG = -1e9


class Net:
    def __init__(self):
        rng = np.random.default_rng(0)
        self.W1 = rng.standard_normal((H1, N_FEATURES)) * np.sqrt(2 / N_FEATURES)
        self.b1 = np.zeros(H1)
        self.W2 = rng.standard_normal((H2, H1)) * np.sqrt(2 / H1)
        self.b2 = np.zeros(H2)
        self.W3 = rng.standard_normal((N_ACTIONS, H2)) * np.sqrt(1 / H2)
        self.b3 = np.zeros(N_ACTIONS)
        self._adam = {k: [np.zeros_like(getattr(self, k)), np.zeros_like(getattr(self, k))]
                      for k in ("W1", "b1", "W2", "b2", "W3", "b3")}
        self._t = 0

    def forward(self, x):
        z1 = self.W1 @ x + self.b1; a1 = np.maximum(z1, 0)
        z2 = self.W2 @ a1 + self.b2; a2 = np.maximum(z2, 0)
        logits = self.W3 @ a2 + self.b3
        return logits, (x, z1, a1, z2, a2)

    def step(self, grads, lr=2e-3):
        self._t += 1
        for k, g in grads.items():
            m, v = self._adam[k]
            m[:] = 0.9 * m + 0.1 * g
            v[:] = 0.999 * v + 0.001 * (g * g)
            mh = m / (1 - 0.9 ** self._t)
            vh = v / (1 - 0.999 ** self._t)
            getattr(self, k)[...] += lr * mh / (np.sqrt(vh) + 1e-8)   # ascent

    def save(self, path):
        data = {k: getattr(self, k).tolist() for k in ("W1", "b1", "W2", "b2", "W3", "b3")}
        data["arch"] = [N_FEATURES, H1, H2, N_ACTIONS]
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)

    def load(self, path):
        with open(path) as f:
            d = json.load(f)
        for k in ("W1", "b1", "W2", "b2", "W3", "b3"):
            getattr(self, k)[...] = np.array(d[k])


def masked_softmax(logits, mask):
    z = np.where(mask > 0, logits, NEG)
    z = z - z.max()
    e = np.exp(z) * mask
    return e / e.sum()


class Trainee(CoyoteAgent):
    """Plays with the current net, sampling actions and logging them."""
    NET = None
    EXPLORE = True

    def game_start(self, state):
        super().game_start(state)
        self.log = []

    def choose_action(self, state, valid_actions):
        by = {}
        for a in valid_actions:
            by.setdefault(a.action_type, []).append(a)
        mask = np.array([1.0 if at in by else 0.0 for at in ACTIONS])
        feats = np.array(encode(state, self._known_list(state)))
        logits, cache = self.NET.forward(feats)
        probs = masked_softmax(logits, mask)
        idx = (np.random.choice(N_ACTIONS, p=probs) if self.EXPLORE else int(np.argmax(probs)))
        if getattr(self, "log", None) is not None:
            self.log.append((cache, mask, probs, idx))
        at = ACTIONS[idx]
        acts = by[at]
        if at in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
            chosen = self._best_target(acts, state)
            if at == ActionType.PLAY_CAT_TRIPLE:
                from dataclasses import replace
                chosen = replace(chosen, named_card=DEF)
            return chosen
        return acts[0]


def play_game(net, rng, explore=True):
    Trainee.NET = net
    Trainee.EXPLORE = explore
    me = Trainee(name="Perdition")
    opps = [c(name=c.__name__) for c in rng.sample(FLEET, 4)]
    agents = [me] + opps
    order = list(range(5)); rng.shuffle(order)
    seat_of_me = order.index(0)
    seated = [agents[i] for i in order]
    r = GameEngine(seated, collect_events=True).play_game(5)
    if r["winner"] < 0:
        return None
    deaths = [e["player"] for e in r["events"] if e["type"] == "explode"]
    if len(deaths) != 4:
        return None
    finish = [r["winner"]] + list(reversed(deaths))     # seats best->worst
    place = finish.index(seat_of_me) + 1                 # 1..5
    # Binary reward: 0 for winning, 1 for any loss. Placement among losers ignored.
    reward = 0.0 if place == 1 else 1.0
    return me.log, reward, place


def backprop(net, cache, mask, probs, idx, advantage, entropy_beta):
    x, z1, a1, z2, a2 = cache
    dlog = advantage * (np.eye(N_ACTIONS)[idx] - probs)
    with np.errstate(divide="ignore", invalid="ignore"):
        logp = np.where(mask > 0, np.log(probs + 1e-12), 0.0)
    dent = -entropy_beta * probs * (logp + 1.0) * mask
    dz3 = dlog + dent
    gW3 = np.outer(dz3, a2); gb3 = dz3
    da2 = net.W3.T @ dz3; dz2 = da2 * (z2 > 0)
    gW2 = np.outer(dz2, a1); gb2 = dz2
    da1 = net.W2.T @ dz2; dz1 = da1 * (z1 > 0)
    gW1 = np.outer(dz1, x); gb1 = dz1
    return {"W1": gW1, "b1": gb1, "W2": gW2, "b2": gb2, "W3": gW3, "b3": gb3}


def evaluate(net, rng, n=3000):
    wins = 0; place_sum = 0; games = 0
    for _ in range(n):
        res = play_game(net, rng, explore=False)
        if res is None:
            continue
        _, _, place = res
        games += 1; place_sum += place
        if place == 1:
            wins += 1
    return (wins / games if games else 0), (place_sum / games if games else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=int, default=4000)
    ap.add_argument("--games", type=int, default=256, help="games per batch")
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--entropy", type=float, default=0.02,
                    help="entropy bonus (slightly higher than Orangutan to encourage bad exploration)")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    net = Net()
    if args.resume and os.path.exists(WEIGHTS_PATH):
        net.load(WEIGHTS_PATH); print("resumed from checkpoint", flush=True)

    rng = random.Random(1234)
    # Baseline starts at ~0.8 (expected reward when rarely winning in a 5-player game).
    baseline = 0.8
    print(f"ian_folder Perdition (minimise win rate): {args.batches} batches x {args.games} games", flush=True)
    for batch in range(1, args.batches + 1):
        decisions = []
        rewards = []
        for _ in range(args.games):
            res = play_game(net, rng, explore=True)
            if res is None:
                continue
            log, reward, _ = res
            rewards.append(reward)
            for (cache, mask, probs, idx) in log:
                decisions.append((cache, mask, probs, idx, reward))
        if not decisions:
            continue
        batch_mean = sum(rewards) / len(rewards)
        baseline = 0.95 * baseline + 0.05 * batch_mean
        grads = {k: np.zeros_like(getattr(net, k)) for k in ("W1", "b1", "W2", "b2", "W3", "b3")}
        for (cache, mask, probs, idx, reward) in decisions:
            adv = reward - baseline
            g = backprop(net, cache, mask, probs, idx, adv, args.entropy)
            for k in grads:
                grads[k] += g[k]
        for k in grads:
            grads[k] /= len(decisions)
        net.step(grads, lr=args.lr)

        if batch % 25 == 0:
            net.save(WEIGHTS_PATH)
            wr, ap_ = evaluate(net, random.Random(99), n=2500)
            print(f"batch {batch:4d}  avg_reward {batch_mean:.3f}  baseline {baseline:.3f}  "
                  f"|  greedy vs fleet: win {wr*100:4.1f}%  loss {(1-wr)*100:4.1f}%  avg_place {ap_:.3f}", flush=True)
    net.save(WEIGHTS_PATH)
    print("done", flush=True)


if __name__ == "__main__":
    main()
