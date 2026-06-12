#!/usr/bin/env python3
"""Mandrill — neural decision heads beyond the action policy.

v1 isolates the cleanest hypothesis: keep Orangutan's 40% action policy FIXED
and learn only the *Nope* head. A learned Nope head (BC-cloned from Coyote, then
PPO self-play) on top of Orangutan's actions tests whether neuralizing the
decisions Coyote currently hard-codes is the headroom past 40%.

Two independent Actor-Critics, both reusing gorilla's PPO machinery:
  - action net (52->8): loaded from Orangutan, frozen here.
  - nope net   (62->2): state(52) + nope-context(10) -> {pass, nope}.

    python3 -m mandrill.train --iters 3000 --workers 8
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gorilla.net import ActorCritic, NEG
from gorilla.train import compute_targets, ppo_update
from agents.coyote_agent import CoyoteAgent
from agents.survival_agent import SurvivalAgent
from agents.survival_agent_v2 import SurvivalAgentV2
from agents.aggressive_agent import AggressiveAgent
from agents.chaos_agent import ChaosAgent
from agents.heuristic_agent import HeuristicAgent
from agents.random_agent import RandomAgent
from agents.orangutan_features import encode, ACTIONS, N_ACTIONS
from game.engine import GameEngine
from game.actions import Action, ActionType
from game.cards import CardType

HERE = os.path.dirname(os.path.abspath(__file__))
ORANGUTAN_W = os.path.join(HERE, "..", "agents", "orangutan_weights.json")
BEST_OUT = os.path.join(HERE, "nope_best.json")
CKPT_OUT = os.path.join(HERE, "nope_ckpt.json")
FLEET = [CoyoteAgent, SurvivalAgentV2, SurvivalAgent, AggressiveAgent,
         ChaosAgent, HeuristicAgent, RandomAgent]
DEF = CardType.DEFUSE
NOPE = CardType.NOPE
# Card plays that trigger a Nope window (DRAW never does).
NOPE_ACTS = [ActionType.PLAY_ATTACK, ActionType.PLAY_SKIP, ActionType.PLAY_FAVOR,
             ActionType.PLAY_SHUFFLE, ActionType.PLAY_SEE_THE_FUTURE,
             ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE]
NCTX = len(NOPE_ACTS) + 3
N_NOPE_IN = 52 + NCTX


def nope_ctx(state, action, currently_noped):
    ctx = [1.0 if action.action_type == a else 0.0 for a in NOPE_ACTS]
    ctx.append(1.0 if currently_noped else 0.0)
    ctx.append(1.0 if state.my_id == state.current_player else 0.0)
    ctx.append(1.0 if getattr(action, "target_player", None) == state.my_id else 0.0)
    return ctx


def _np(w):
    return {k: np.array(v) for k, v in w.items() if k != "arch"}


def _fwd(p, x):
    a1 = np.maximum(p["W1"] @ x + p["b1"], 0)
    a2 = np.maximum(p["W2"] @ a1 + p["b2"], 0)
    logits = p["W3"] @ a2 + p["b3"]
    value = float((p["Wv"] @ a2 + p["bv"])[0]) if "Wv" in p else 0.0
    return logits, value


def _softmax(z):
    z = z - z.max(); e = np.exp(z); return e / e.sum()


def _resolve(at, acts, agent, state):
    if at in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
        chosen = agent._best_target(acts, state)
        if at == ActionType.PLAY_CAT_TRIPLE:
            from dataclasses import replace
            chosen = replace(chosen, named_card=DEF)
        return chosen
    return acts[0]


def make_learner(action_p, nope_p, npr, sample_nope=True, log=None):
    class Learner(CoyoteAgent):
        def choose_action(self, state, valid_actions):
            by = {}
            for a in valid_actions:
                by.setdefault(a.action_type, []).append(a)
            feats = np.array(encode(state, self._known_list(state)))
            logits, _ = _fwd(action_p, feats)
            best, bi = None, None
            for i, at in enumerate(ACTIONS):
                if at in by and (best is None or logits[i] > best):
                    best, bi = logits[i], i
            return _resolve(ACTIONS[bi], by[ACTIONS[bi]], self, state)

        def want_to_nope(self, state, action, currently_noped=False):
            if not any(c.card_type == NOPE for c in state.my_hand):
                return False
            feats = np.array(encode(state, self._known_list(state)) + nope_ctx(state, action, currently_noped))
            logits, value = _fwd(nope_p, feats)
            probs = _softmax(logits)
            idx = int(npr.choice(2, p=probs)) if sample_nope else int(np.argmax(probs))
            if log is not None:
                log.append((feats.tolist(), idx, float(np.log(probs[idx] + 1e-12)),
                            value, [1.0, 1.0]))
            return idx == 1
    return Learner


def play_one(action_p, nope_p, rng, npr, log=None, greedy=False):
    L = make_learner(action_p, nope_p, npr, sample_nope=not greedy, log=log)
    me = L(name="Mandrill")
    opps = [c(name=c.__name__) for c in rng.sample(FLEET, 4)]
    agents = [me] + opps
    order = list(range(5)); rng.shuffle(order); seat = order.index(0)
    r = GameEngine([agents[i] for i in order], collect_events=True).play_game(5)
    if r["winner"] < 0:
        return [], 0.0, None
    deaths = [e["player"] for e in r["events"] if e["type"] == "explode"]
    reward = 1.0 if r["winner"] == seat else (-1.0 if seat in deaths else 0.0)
    place = None
    if len(deaths) == 4:
        place = ([r["winner"]] + list(reversed(deaths))).index(seat) + 1
    return (log if log is not None else []), reward, place


def rollout_worker(args):
    import random as _random
    action_w, nope_w, n_games, seed = args
    ap = _np(action_w); npp = _np(nope_w)
    rng = _random.Random(seed); npr = np.random.default_rng(seed)
    out = []
    for _ in range(n_games):
        log = []
        _, reward, _ = play_one(ap, npp, rng, npr, log=log)
        out.append((log, reward))
    return out


def evaluate(action_w, nope_w, n=3000, seed=99):
    import random as _random
    ap = _np(action_w); npp = _np(nope_w)
    rng = _random.Random(seed); npr = np.random.default_rng(seed)
    wins = ps = games = 0
    for _ in range(n):
        _, _, place = play_one(ap, npp, rng, npr, log=None, greedy=True)
        if place is None:
            continue
        games += 1; ps += place
        if place == 1:
            wins += 1
    return (wins / games if games else 0), (ps / games if games else 0)


def bc_nope(net, n_games=40000, epochs=6, lr=1e-3):
    """Clone Coyote's Nope decisions into the nope net."""
    print(f"BC-nope: collecting {n_games} games...", flush=True)
    samples = []
    rng = __import__("random").Random(7)

    class Teacher(CoyoteAgent):
        def want_to_nope(self, state, action, currently_noped=False):
            decision = super().want_to_nope(state, action, currently_noped)
            if any(c.card_type == NOPE for c in state.my_hand):
                feats = encode(state, self._known_list(state)) + nope_ctx(state, action, currently_noped)
                samples.append((feats, 1 if decision else 0))
            return decision

    for _ in range(n_games):
        me = Teacher(name="T"); opps = [c(name=c.__name__) for c in rng.sample(FLEET, 4)]
        agents = [me] + opps; order = list(range(5)); rng.shuffle(order)
        GameEngine([agents[i] for i in order]).play_game(5)
    X = np.array([s[0] for s in samples]); y = np.array([s[1] for s in samples])
    oh = np.eye(2)[y]
    pos = y.mean()
    print(f"BC-nope: {len(X)} decisions ({pos*100:.1f}% nope); training...", flush=True)
    idx = np.arange(len(X)); bs = 1024
    for ep in range(epochs):
        np.random.shuffle(idx); correct = 0
        for s in range(0, len(idx), bs):
            b = idx[s:s + bs]; Xb, Ob = X[b], oh[b]
            Z1 = Xb @ net.W1.T + net.b1; A1 = np.maximum(Z1, 0)
            Z2 = A1 @ net.W2.T + net.b2; A2 = np.maximum(Z2, 0)
            L = A2 @ net.W3.T + net.b3
            P = np.exp(L - L.max(1, keepdims=True)); P /= P.sum(1, keepdims=True)
            correct += int((P.argmax(1) == y[b]).sum())
            dL = (P - Ob) / len(b)
            gW3 = dL.T @ A2; gb3 = dL.sum(0)
            dZ2 = (dL @ net.W3) * (Z2 > 0); gW2 = dZ2.T @ A1; gb2 = dZ2.sum(0)
            dZ1 = (dZ2 @ net.W2) * (Z1 > 0); gW1 = dZ1.T @ Xb; gb1 = dZ1.sum(0)
            net.step({"W1": gW1, "b1": gb1, "W2": gW2, "b2": gb2, "W3": gW3, "b3": gb3}, lr)
        print(f"BC-nope epoch {ep+1}: match {correct/len(X)*100:.1f}%", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=3000)
    ap.add_argument("--games", type=int, default=512)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--mb", type=int, default=2048)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--gamma", type=float, default=0.997)
    ap.add_argument("--bc_games", type=int, default=40000)
    ap.add_argument("--skip_bc", action="store_true")
    args = ap.parse_args()

    action_net = ActorCritic(n_features=52, n_actions=8)
    action_net.load_bc(ORANGUTAN_W)             # Orangutan's 40% action policy (frozen)
    action_w = action_net.full_weights()

    nope_net = ActorCritic(n_features=N_NOPE_IN, n_actions=2)
    if args.skip_bc and os.path.exists(CKPT_OUT):
        nope_net.load_full(json.load(open(CKPT_OUT))); print("resumed nope ckpt", flush=True)
    else:
        bc_nope(nope_net, n_games=args.bc_games); nope_net.save_full(CKPT_OUT)

    wr, apl = evaluate(action_w, nope_net.full_weights(), n=3000)
    best = wr
    print(f"baseline (Orangutan actions + BC-Coyote nope): win {wr*100:.2f}%  place {apl:.3f}", flush=True)

    ex = ProcessPoolExecutor(max_workers=args.workers) if args.workers > 1 else None
    seed = 5000
    for it in range(1, args.iters + 1):
        t0 = time.time(); nope_w = nope_net.full_weights()
        per = max(1, args.games // max(1, args.workers))
        if ex:
            futs = [ex.submit(rollout_worker, (action_w, nope_w, per, (seed := seed + 1)))
                    for _ in range(args.workers)]
            games = []
            for f in futs:
                games.extend(f.result())
        else:
            seed += 1; games = rollout_worker((action_w, nope_w, args.games, seed))
        data = compute_targets(games, args.gamma)
        if data is not None:
            ppo_update(nope_net, data, args.epochs, args.mb, 0.2, 0.5, 0.01, args.lr)
        nope_net.save_full(CKPT_OUT)
        if it % 10 == 0:
            wr, apl = evaluate(action_w, nope_net.full_weights(), n=3000)
            tag = ""
            if wr > best:
                best = wr; nope_net.save_policy(BEST_OUT); tag = "  <- new best"
            print(f"iter {it:4d}  greedy win {wr*100:5.2f}%  place {apl:.3f}  "
                  f"(best {best*100:.2f}%)  {time.time()-t0:.1f}s/it{tag}", flush=True)
    if ex:
        ex.shutdown()
    print("done", flush=True)


if __name__ == "__main__":
    main()
