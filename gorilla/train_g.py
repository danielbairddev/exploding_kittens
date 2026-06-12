#!/usr/bin/env python3
"""Gorilla training: opponent-modeling encoder (encode_g) + PPO self-play.

Same recipe that took Orangutan to 40%, but the learner carries a GameTracker
and uses encode_g (base 52 + per-opponent behavior profiles + danger). Tests
whether opponent modeling pushes past Orangutan. BC warm-start, then PPO vs the
fleet (exploitation).

    python3 -m gorilla.train_g --iters 3000 --workers 8
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gorilla.net import ActorCritic, masked_softmax, NEG
# Encoder is selectable so Abaddon can reuse this whole pipeline. Read at import
# time so spawned rollout workers (which re-import this module) pick it up too.
if os.environ.get("EK_ENCODER") == "abaddon":
    from abaddon.features import encode_a as encode_g, N_FEATURES_A as N_FEATURES_G
else:
    from gorilla.features_g import encode_g, N_FEATURES_G
from gorilla.tracker import GameTracker, DEF
from gorilla.train import compute_targets, ppo_update
from agents.coyote_agent import CoyoteAgent
from agents.survival_agent import SurvivalAgent
from agents.survival_agent_v2 import SurvivalAgentV2
from agents.aggressive_agent import AggressiveAgent
from agents.chaos_agent import ChaosAgent
from agents.heuristic_agent import HeuristicAgent
from agents.random_agent import RandomAgent
from agents.orangutan_features import ACTIONS, N_ACTIONS
from game.engine import GameEngine
from game.actions import Action, ActionType

HERE = os.path.dirname(os.path.abspath(__file__))
BEST_OUT = os.path.join(HERE, "best_policy_g.json")
CKPT_OUT = os.path.join(HERE, "checkpoint_g.json")
FLEET = [CoyoteAgent, SurvivalAgentV2, SurvivalAgent, AggressiveAgent,
         ChaosAgent, HeuristicAgent, RandomAgent]


def _np(w):
    return {k: np.array(v) for k, v in w.items() if k != "arch"}


def _fwd(p, x):
    a1 = np.maximum(p["W1"] @ x + p["b1"], 0)
    a2 = np.maximum(p["W2"] @ a1 + p["b2"], 0)
    logits = p["W3"] @ a2 + p["b3"]
    value = float((p["Wv"] @ a2 + p["bv"])[0]) if "Wv" in p else 0.0
    return logits, value


def _mprobs(logits, mask):
    z = np.where(mask > 0, logits, NEG); z = z - z.max()
    e = np.exp(z) * mask
    return e / e.sum()


class TrackerMixin(CoyoteAgent):
    """Maintains a GameTracker from the agent's callbacks (Coyote elsewhere)."""
    opp_type_map = {}     # seat -> class name; set per game before play (empty = anonymized)

    def game_start(self, state):
        super().game_start(state)
        self.tr = GameTracker(); self.tr.reset(state)
        self.tr.set_opponent_types(getattr(self, "opp_type_map", {}))

    def want_to_nope(self, state, action, currently_noped=False):
        self.tr.observe_action(state, action, currently_noped)
        return super().want_to_nope(state, action, currently_noped)

    def see_future(self, state, top3):
        super().see_future(state, top3)
        self.tr.observe_future(top3, state.deck_size)


def _resolve(at, acts, agent, state):
    if at in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
        chosen = agent._best_target(acts, state)
        if at == ActionType.PLAY_CAT_TRIPLE:
            from dataclasses import replace
            chosen = replace(chosen, named_card=DEF)
        return chosen
    return acts[0]


def play_one_g(params, rng, npr, greedy=False, log=None, anon_frac=0.25):
    class Learner(TrackerMixin):
        def choose_action(self, state, valid_actions):
            by = {}
            for a in valid_actions:
                by.setdefault(a.action_type, []).append(a)
            mask = np.array([1.0 if at in by else 0.0 for at in ACTIONS])
            feats = np.array(encode_g(state, self.tr, self.tr.known_top(state)))
            logits, value = _fwd(params, feats)
            probs = _mprobs(logits, mask)
            idx = int(np.argmax(probs)) if greedy else int(npr.choice(N_ACTIONS, p=probs))
            if log is not None:
                log.append((feats.tolist(), idx, float(np.log(probs[idx] + 1e-12)),
                            value, mask.tolist()))
            return _resolve(ACTIONS[idx], by[ACTIONS[idx]], self, state)

    me = Learner(name="Gorilla")
    opps = [c(name=c.__name__) for c in rng.sample(FLEET, 4)]
    agents = [me] + opps
    order = list(range(5)); rng.shuffle(order); seat = order.index(0)
    # Tell the learner who each opponent is — unless this game is "anonymized"
    # (so the behavioral-profile fallback keeps getting trained too).
    if rng.random() >= anon_frac:
        me.opp_type_map = {s: type(agents[order[s]]).__name__
                           for s in range(5) if order[s] != 0}
    else:
        me.opp_type_map = {}
    r = GameEngine([agents[i] for i in order], collect_events=True).play_game(5)
    if r["winner"] < 0:
        return 0.0
    deaths = [e["player"] for e in r["events"] if e["type"] == "explode"]
    if r["winner"] == seat:
        return 1.0
    return -1.0 if seat in deaths else 0.0


def rollout_worker_g(args):
    import random as _random
    policy_w, n_games, seed = args
    p = _np(policy_w); rng = _random.Random(seed); npr = np.random.default_rng(seed)
    out = []
    for _ in range(n_games):
        log = []
        reward = play_one_g(p, rng, npr, greedy=False, log=log)
        out.append((log, reward))
    return out


def evaluate_g(policy_w, n=3000, seed=99):
    import random as _random
    p = _np(policy_w); rng = _random.Random(seed); npr = np.random.default_rng(seed)
    wins = place_sum = games = 0
    # replay to get place: reuse play but need finish order -> re-implement quickly
    for _ in range(n):
        class Greedy(TrackerMixin):
            def choose_action(self, state, valid_actions):
                by = {}
                for a in valid_actions:
                    by.setdefault(a.action_type, []).append(a)
                mask = np.array([1.0 if at in by else 0.0 for at in ACTIONS])
                feats = np.array(encode_g(state, self.tr, self.tr.known_top(state)))
                logits, _ = _fwd(p, feats); probs = _mprobs(logits, mask)
                idx = int(np.argmax(probs))
                return _resolve(ACTIONS[idx], by[ACTIONS[idx]], self, state)
        me = Greedy(name="G"); opps = [c(name=c.__name__) for c in rng.sample(FLEET, 4)]
        agents = [me] + opps; order = list(range(5)); rng.shuffle(order); seat = order.index(0)
        me.opp_type_map = {s: type(agents[order[s]]).__name__ for s in range(5) if order[s] != 0}
        r = GameEngine([agents[i] for i in order], collect_events=True).play_game(5)
        if r["winner"] < 0:
            continue
        deaths = [e["player"] for e in r["events"] if e["type"] == "explode"]
        if len(deaths) != 4:
            continue
        finish = [r["winner"]] + list(reversed(deaths))
        games += 1; place_sum += finish.index(seat) + 1
        if finish.index(seat) == 0:
            wins += 1
    return (wins / games if games else 0), (place_sum / games if games else 0)


def behavioral_clone_g(net, n_games=60000, epochs=6, lr=1e-3):
    print(f"BC-g: collecting {n_games} games of Coyote+tracker decisions...", flush=True)
    samples = []
    rng = __import__("random").Random(2024)

    class Teacher(TrackerMixin):
        def choose_action(self, state, valid_actions):
            action = super().choose_action(state, valid_actions)
            by = {a.action_type for a in valid_actions}
            if action.action_type in ACTIONS:
                feats = encode_g(state, self.tr, self.tr.known_top(state))
                mask = [1.0 if at in by else 0.0 for at in ACTIONS]
                samples.append((feats, ACTIONS.index(action.action_type), mask))
            return action

    for _ in range(n_games):
        me = Teacher(name="T"); opps = [c(name=c.__name__) for c in rng.sample(FLEET, 4)]
        agents = [me] + opps; order = list(range(5)); rng.shuffle(order)
        if rng.random() >= 0.25:
            me.opp_type_map = {s: type(agents[order[s]]).__name__ for s in range(5) if order[s] != 0}
        else:
            me.opp_type_map = {}
        GameEngine([agents[i] for i in order]).play_game(5)
    X = np.array([s[0] for s in samples]); y = np.array([s[1] for s in samples])
    M = np.array([s[2] for s in samples]); oh = np.eye(N_ACTIONS)[y]
    print(f"BC-g: {len(X)} decisions; training...", flush=True)
    idx = np.arange(len(X)); bs = 1024
    for ep in range(epochs):
        np.random.shuffle(idx); correct = 0
        for s in range(0, len(idx), bs):
            b = idx[s:s + bs]; Xb, Mb, Ob = X[b], M[b], oh[b]
            Z1 = Xb @ net.W1.T + net.b1; A1 = np.maximum(Z1, 0)
            Z2 = A1 @ net.W2.T + net.b2; A2 = np.maximum(Z2, 0)
            L = A2 @ net.W3.T + net.b3
            Z = np.where(Mb > 0, L, NEG); Z -= Z.max(1, keepdims=True)
            E = np.exp(Z) * Mb; P = E / E.sum(1, keepdims=True)
            correct += int((P.argmax(1) == y[b]).sum())
            dL = (P - Ob) / len(b)        # dLoss/dlogits for CE (net.step descends)
            gW3 = dL.T @ A2; gb3 = dL.sum(0)
            dZ2 = (dL @ net.W3) * (Z2 > 0); gW2 = dZ2.T @ A1; gb2 = dZ2.sum(0)
            dZ1 = (dZ2 @ net.W2) * (Z1 > 0); gW1 = dZ1.T @ Xb; gb1 = dZ1.sum(0)
            net.step({"W1": gW1, "b1": gb1, "W2": gW2, "b2": gb2, "W3": gW3, "b3": gb3}, lr)
        print(f"BC-g epoch {ep+1}: match {correct/len(X)*100:.1f}%", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=3000)
    ap.add_argument("--games", type=int, default=512)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--mb", type=int, default=2048)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--gamma", type=float, default=0.997)
    ap.add_argument("--skip_bc", action="store_true")
    ap.add_argument("--bc_games", type=int, default=60000)
    args = ap.parse_args()

    net = ActorCritic(n_features=N_FEATURES_G)
    if args.skip_bc and os.path.exists(CKPT_OUT):
        net.load_full(json.load(open(CKPT_OUT))); print("resumed", flush=True)
    else:
        behavioral_clone_g(net, n_games=args.bc_games); net.save_full(CKPT_OUT)
    wr, ap_ = evaluate_g(net.full_weights(), n=3000)
    best = wr; print(f"BC-g baseline: win {wr*100:.1f}%  place {ap_:.3f}", flush=True)

    ex = ProcessPoolExecutor(max_workers=args.workers) if args.workers > 1 else None
    seed = 7000
    for it in range(1, args.iters + 1):
        t0 = time.time(); pw = net.full_weights()
        per = max(1, args.games // max(1, args.workers))
        if ex:
            futs = []
            for _ in range(args.workers):
                seed += 1; futs.append(ex.submit(rollout_worker_g, (pw, per, seed)))
            games = []
            for f in futs:
                games.extend(f.result())
        else:
            seed += 1; games = rollout_worker_g((pw, args.games, seed))
        data = compute_targets(games, args.gamma)
        if data is not None:
            ppo_update(net, data, args.epochs, args.mb, 0.2, 0.5, 0.01, args.lr)
        net.save_full(CKPT_OUT)
        if it % 10 == 0:
            wr, apl = evaluate_g(net.full_weights(), n=3000)
            tag = ""
            if wr > best:
                best = wr; net.save_policy(BEST_OUT); tag = "  <- new best"
            print(f"iter {it:4d}  greedy win {wr*100:5.2f}%  place {apl:.3f}  "
                  f"(best {best*100:.2f}%)  {time.time()-t0:.1f}s/it{tag}", flush=True)
    if ex:
        ex.shutdown()
    print("done", flush=True)


if __name__ == "__main__":
    main()
