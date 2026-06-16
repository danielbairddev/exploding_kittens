#!/usr/bin/env python3
"""Train the Orangutan policy network by REINFORCE self-play vs the fleet.

A small MLP (35 -> 64 -> 32 -> 8) picks the action TYPE each turn. It plays
games against random subsets of the existing bots; the reward is placement-based
(1.0 for 1st down to 0.0 for first-out), and we do policy-gradient ascent with an
entropy bonus. Weights are checkpointed to agents/orangutan_weights.json (the
format the deployed OrangutanAgent reads). Run in the background:

    python3 ian_folder/train_orangutan.py --batches 4000

Progress lines report Orangutan's greedy win% and average place vs the fleet.
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
from agents.orangutan_features import encode, ACTIONS, N_FEATURES, N_ACTIONS
from game.engine import GameEngine
from game.actions import Action, ActionType
from game.cards import CardType

DEF = CardType.DEFUSE
WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents", "orangutan_weights.json")
FLEET = [CoyoteAgent, SurvivalAgentV2, SurvivalAgent, AggressiveAgent,
         ChaosAgent, HeuristicAgent, RandomAgent]
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
    me = Trainee(name="Orangutan")
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
    reward = (5 - place) / 4.0                           # 1.0 win .. 0.0 first out
    return me.log, reward, place


def backprop(net, cache, mask, probs, idx, advantage, entropy_beta):
    x, z1, a1, z2, a2 = cache
    # dJ/dlogits for J = A*log p_idx + beta*entropy
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


class TeacherLogger(CoyoteAgent):
    """Coyote, but logs (features, chosen action index) for behavioral cloning."""
    SAMPLES = None

    def choose_action(self, state, valid_actions):
        action = super().choose_action(state, valid_actions)
        by = {a.action_type for a in valid_actions}
        mask = [1.0 if at in by else 0.0 for at in ACTIONS]
        if action.action_type in ACTIONS and self.SAMPLES is not None:
            feats = encode(state, self._known_list(state))
            self.SAMPLES.append((feats, ACTIONS.index(action.action_type), mask))
        return action


def behavioral_clone(net, n_games=60000, epochs=6, lr=1e-3):
    """Pretrain the policy to imitate Coyote's action choices."""
    print(f"BC: collecting {n_games} games of Coyote decisions...", flush=True)
    samples = []
    TeacherLogger.SAMPLES = samples
    rng = random.Random(2024)
    for _ in range(n_games):
        me = TeacherLogger(name="Teacher")
        opps = [c(name=c.__name__) for c in rng.sample(FLEET, 4)]
        agents = [me] + opps
        order = list(range(5)); rng.shuffle(order)
        GameEngine([agents[i] for i in order], collect_events=False).play_game(5)
    TeacherLogger.SAMPLES = None
    X = np.array([s[0] for s in samples])
    y = np.array([s[1] for s in samples])
    M = np.array([s[2] for s in samples])
    onehot = np.eye(N_ACTIONS)[y]
    print(f"BC: {len(X)} decisions; ian_folder {epochs} epochs (vectorized)...", flush=True)
    idx = np.arange(len(X)); bs = 1024
    for ep in range(epochs):
        np.random.shuffle(idx)
        correct = 0
        for start in range(0, len(idx), bs):
            b = idx[start:start + bs]
            Xb, Mb, Ob = X[b], M[b], onehot[b]
            Z1 = Xb @ net.W1.T + net.b1; A1 = np.maximum(Z1, 0)
            Z2 = A1 @ net.W2.T + net.b2; A2 = np.maximum(Z2, 0)
            L = A2 @ net.W3.T + net.b3
            Z = np.where(Mb > 0, L, NEG); Z -= Z.max(1, keepdims=True)
            E = np.exp(Z) * Mb; P = E / E.sum(1, keepdims=True)
            correct += int((P.argmax(1) == y[b]).sum())
            n = len(b)
            dL = (Ob - P) / n                                   # ascend log p_true
            gW3 = dL.T @ A2; gb3 = dL.sum(0)
            dZ2 = (dL @ net.W3) * (Z2 > 0)
            gW2 = dZ2.T @ A1; gb2 = dZ2.sum(0)
            dZ1 = (dZ2 @ net.W2) * (Z1 > 0)
            gW1 = dZ1.T @ Xb; gb1 = dZ1.sum(0)
            net.step({"W1": gW1, "b1": gb1, "W2": gW2, "b2": gb2, "W3": gW3, "b3": gb3}, lr=lr)
        print(f"BC epoch {ep+1}: train action-match {correct/len(X)*100:.1f}%", flush=True)
    net.save(WEIGHTS_PATH)
    wr, ap_ = evaluate(net, random.Random(99), n=3000)
    print(f"BC done -> greedy vs fleet: win {wr*100:.1f}%  avg_place {ap_:.3f}", flush=True)


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
    ap.add_argument("--entropy", type=float, default=0.01)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--mode", choices=["bc", "rl", "both"], default="both")
    args = ap.parse_args()

    net = Net()
    if args.resume and os.path.exists(WEIGHTS_PATH):
        net.load(WEIGHTS_PATH); print("resumed from checkpoint", flush=True)
    if args.mode in ("bc", "both"):
        behavioral_clone(net)
        if args.mode == "bc":
            return
    rng = random.Random(1234)
    baseline = 0.5
    print(f"ian_folder: {args.batches} batches x {args.games} games", flush=True)
    for batch in range(1, args.batches + 1):
        decisions = []   # (cache, mask, probs, idx, reward)
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
        # accumulate gradients with advantage = reward - baseline
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
                  f"|  greedy vs fleet: win {wr*100:4.1f}%  avg_place {ap_:.3f}", flush=True)
    net.save(WEIGHTS_PATH)
    print("done", flush=True)


if __name__ == "__main__":
    main()
