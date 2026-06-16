"""Rollout workers for Hades ian_folder (HADES_PLAN.md §4-§5).

Hades is trained to LOSE. Terminal reward is +1 for dying (any death position),
-1 for being the sole survivor. Dense auxiliary shaping rewards self-sabotage:
  give_defuse  +0.2  (handing a Defuse to a requester via Favor)
  waste_defuse +0.2  (spending a Defuse to keep the game going)
  draw_safe    -0.05 (drawing a non-EK card extends lifespan)

Deviation from the spec: aux rewards are summed into a single per-game scalar
(R_term + sum aux) which compute_targets() then discounts across steps, rather
than being attached to individual transitions. This keeps the credit-assignment
machinery identical to the Elephant/Orpheus trainers.

Curriculum:
  phase 1 ('bootstrap'): opponents are 100% standard winner bots.
  phase 2 ('crucible'):  80% loser fleet + 20% self-play (past checkpoints).
"""
from dataclasses import replace

import numpy as np

from agents.base import Agent
from agents.coyote_agent import CoyoteAgent
from agents.rhino_agent import RhinoAgent
from agents.elephant_agent import ElephantAgent
from agents.gabriel_agent import GabrielAgent
from agents.perdition2_agent import Perdition2Agent
from agents.ian1_agent import Ian1Agent
from agents.ian2_agent import Ian2Agent
from agents.ian3_agent import Ian3Agent

from agents.orangutan_features import ACTIONS, N_ACTIONS
from training.hades import features as F
from training.hades.event_encode import encode_event, new_context
from training.hades.net import (TransformerActorCritic, CONTEXT_WINDOW,
                                N_TARGETS, N_CARD_TYPES, N_PLACE, NOPE_CTX)
from game.engine import GameEngine
from game.actions import Action, ActionType
from game.cards import CardType

DEF = CardType.DEFUSE

# Phase 1: force fast self-destruction against genuine winners.
WINNER_FLEET = [CoyoteAgent, CoyoteAgent, RhinoAgent, ElephantAgent]
# Phase 2: out-lose the actual losers.
LOSER_FLEET = [Ian1Agent, Ian1Agent, Ian2Agent, Ian2Agent,
               Ian3Agent, Ian3Agent, Perdition2Agent, Perdition2Agent,
               GabrielAgent]
# Evaluation target fleet (HADES_PLAN.md §5): [Ian3, Ian3, Perdition2, Gabriel]
EVAL_FLEET = [Ian3Agent, Ian3Agent, Perdition2Agent, GabrielAgent]

_CARD_IDX = F._CARD_IDX

# Dense aux shaping. Reward-audit fix (2026-06-14): the original spec gave
# waste_defuse = +0.2, but for a bot whose goal is to DIE, defusing an EK means
# *surviving* one — that bonus fights the −1 terminal and anchored a ~18% plateau.
# Flipped to a penalty so the policy is pushed to shed defuses (give them away,
# rewarded by give_defuse) and explode instead of defusing.
R_GIVE_DEFUSE = 0.2     # shedding a defuse -> more likely to die later (good)
R_WASTE_DEFUSE = -0.2   # defusing an EK == surviving it -> penalise (was +0.2)
R_DRAW_SAFE = -0.05     # surviving a draw extends lifespan (mild penalty)


# Nope-head context now lives in features.nope_context (shared, target-aware).


class _HadesLearner(Agent):
    """Trainable Transformer agent that logs every decision for PPO."""
    NET = None
    RNG = None
    GREEDY = False
    # per-game logs (set by play_one); None disables logging (frozen opponents)
    EV_LOG = None
    STEP_LOG = None
    NOPE_LOG = None
    GIVE_LOG = None
    PLACE_LOG = None
    AUX = None  # dict accumulating aux rewards for the learner

    def __init__(self, name='Hades', seed=None):
        self.name = name

    def game_start(self, state):
        self._ev_log = []
        self._ctx = new_context()
        self._tracker = F.OpponentTracker(state.my_id)
        self._last_eid = -1
        self._top = None
        self._top_deck = -1

    def see_future(self, state, top3):
        self._top = [c.card_type for c in top3]
        self._top_deck = state.deck_size

    def _known_top(self, state):
        if (self._top is not None and state.deck_size == self._top_deck):
            return self._top
        return None

    def _absorb(self, state):
        new = sorted([e for e in state.recent_events
                      if e.get('event_id', 0) > self._last_eid],
                     key=lambda e: e.get('event_id', 0))
        for ev in new:
            vec = encode_event(ev, state.my_id, self._ctx)
            self._ev_log.append(vec)
            if self.EV_LOG is not None:
                self.EV_LOG.append(vec)
            self._last_eid = ev.get('event_id', self._last_eid)
        self._tracker.update(state)

    def _window(self):
        return self._ev_log[-CONTEXT_WINDOW:]

    def _ec(self):
        return len(self.EV_LOG) if self.EV_LOG is not None else len(self._ev_log)

    def _forward(self, state):
        hmem, _ = self.NET.encode(self._window())
        snap = F.encode(state, self._tracker, self._known_top(state))
        a2, _ = self.NET.trunk(hmem, np.asarray(snap, dtype=np.float64))
        return a2, snap

    def _sample(self, probs, n):
        if self.GREEDY:
            return int(np.argmax(probs))
        return int(self.RNG.choice(n, p=probs))

    @staticmethod
    def _masked_probs(logits, mask):
        z = np.where(mask > 0, logits, -1e9)
        z = z - z.max()
        e = np.exp(z) * mask
        return e / (e.sum() + 1e-12)

    def choose_action(self, state, valid_actions):
        self._absorb(state)
        a2, snap = self._forward(state)
        value = self.NET.value(a2)
        logits = self.NET.policy(a2)

        by = {}
        for a in valid_actions:
            by.setdefault(a.action_type, []).append(a)
        mask = np.array([1.0 if at in by else 0.0 for at in ACTIONS])
        if mask.sum() == 0:
            return Action(ActionType.DRAW)
        probs = self._masked_probs(logits, mask)
        idx = self._sample(probs, N_ACTIONS)
        at = ACTIONS[idx]
        acts = by.get(at) or [Action(ActionType.DRAW)]
        chosen = acts[0]

        has_target = False
        tgt_mask = tgt_action = tgt_logp = None
        if at in (ActionType.PLAY_FAVOR, ActionType.PLAY_CAT_PAIR, ActionType.PLAY_CAT_TRIPLE):
            has_target = True
            tgt_mask_arr = np.zeros(N_TARGETS)
            by_rel = {}
            for a in acts:
                if a.target_player is not None:
                    rel = (a.target_player - state.my_id) % N_TARGETS
                    tgt_mask_arr[rel] = 1.0
                    by_rel[rel] = a
            tlogits = self.NET.target(a2)
            tprobs = self._masked_probs(tlogits, tgt_mask_arr)
            if self.GREEDY:
                rel = int(np.argmax(tprobs))
            else:
                valid_rels = [i for i in range(N_TARGETS) if tgt_mask_arr[i] > 0]
                rel = int(self.RNG.choice(valid_rels,
                          p=tprobs[valid_rels] / tprobs[valid_rels].sum()))
            chosen = by_rel.get(rel, acts[0])
            tgt_mask = tgt_mask_arr.tolist()
            tgt_action = rel
            tgt_logp = float(np.log(tprobs[rel] + 1e-12))
            if at == ActionType.PLAY_CAT_TRIPLE:
                chosen = replace(chosen, named_card=DEF)

        if self.STEP_LOG is not None:
            self.STEP_LOG.append({
                'event_count': self._ec(),
                'snapshot': list(snap),
                'mask': mask.tolist(),
                'action': idx,
                'old_logp': float(np.log(probs[idx] + 1e-12)),
                'old_value': value,
                'has_target': has_target,
                'target_mask': tgt_mask,
                'target_action': tgt_action,
                'target_logp': tgt_logp,
            })
        return chosen

    def want_to_nope(self, state, action, currently_noped=False):
        if self.NET is None:
            return False
        self._absorb(state)
        a2, snap = self._forward(state)
        nctx = F.nope_context(state, action, currently_noped)
        logit, _ = self.NET.nope_logit(a2, np.asarray(nctx, dtype=np.float64))
        prob = 1.0 / (1.0 + np.exp(-np.clip(logit, -20, 20)))
        if self.GREEDY:
            decision = prob > 0.5
        else:
            decision = bool(self.RNG.random() < prob)
        if self.NOPE_LOG is not None:
            logp = float(np.log(prob + 1e-12) if decision else np.log(1.0 - prob + 1e-12))
            self.NOPE_LOG.append({
                'event_count': self._ec(),
                'snapshot': list(snap),
                'nope_ctx': nctx,
                'currently_noped': int(currently_noped),
                'decision': int(decision),
                'old_logp': logp,
                'old_value': self.NET.value(a2),
            })
        return decision

    def give_card(self, state, requester_id):
        if self.NET is None or not state.my_hand:
            return state.my_hand[0].card_type if state.my_hand else DEF
        self._absorb(state)
        a2, snap = self._forward(state)
        logits = self.NET.give(a2)
        hand_names = {c.card_type.name for c in state.my_hand}
        card_mask = np.array([1.0 if n in hand_names else 0.0 for n in F.CARD_NAMES] + [0.0])
        probs = self._masked_probs(logits, card_mask)
        idx = self._sample(probs, N_CARD_TYPES) if not self.GREEDY else int(np.argmax(probs))
        if not self.GREEDY:
            valid = np.where(card_mask > 0)[0]
            idx = int(self.RNG.choice(valid, p=probs[valid] / probs[valid].sum()))
        if self.GIVE_LOG is not None:
            self.GIVE_LOG.append({
                'event_count': self._ec(),
                'snapshot': list(snap),
                'card_mask': card_mask.tolist(),
                'decision': idx,
                'old_logp': float(np.log(probs[idx] + 1e-12)),
                'old_value': self.NET.value(a2),
            })
        try:
            chosen = CardType[F.CARD_NAMES[idx]]
        except (KeyError, IndexError):
            chosen = state.my_hand[0].card_type
        if self.AUX is not None and chosen == DEF:
            self.AUX['r'] += R_GIVE_DEFUSE
        return chosen

    def place_exploding_kitten(self, state, deck_size):
        if self.NET is None:
            return 0
        a2, snap = self._forward(state)
        logits = self.NET.place(a2)
        # valid positions are 0..deck_size inclusive
        mask = np.zeros(N_PLACE)
        mask[:min(deck_size + 1, N_PLACE)] = 1.0
        probs = self._masked_probs(logits, mask)
        if self.GREEDY:
            idx = int(np.argmax(probs))
        else:
            idx = int(self.RNG.choice(N_PLACE, p=probs))
        if self.PLACE_LOG is not None:
            self.PLACE_LOG.append({
                'event_count': self._ec(),
                'snapshot': list(snap),
                'place_mask': mask.tolist(),
                'decision': idx,
                'old_logp': float(np.log(probs[idx] + 1e-12)),
                'old_value': self.NET.value(a2),
            })
        if self.AUX is not None:
            self.AUX['r'] += R_WASTE_DEFUSE
        return min(idx, deck_size)


def _make_net(weights):
    net = TransformerActorCritic()
    net.load_weights(weights)
    return net


def play_one(policy_w, pool_w, rng, npr, phase='crucible', self_prob=0.2):
    learner_net = _make_net(policy_w)
    ev_log, step_log, nope_log, give_log, place_log = [], [], [], [], []
    aux = {'r': 0.0}

    class Learner(_HadesLearner):
        NET = learner_net; RNG = npr; GREEDY = False
        EV_LOG = ev_log; STEP_LOG = step_log; NOPE_LOG = nope_log
        GIVE_LOG = give_log; PLACE_LOG = place_log; AUX = aux

    opponents = []
    for i in range(4):
        if phase == 'crucible' and pool_w and rng.random() < self_prob:
            pnet = _make_net(rng.choice(pool_w))
            class Frozen(_HadesLearner):
                NET = pnet; RNG = npr; GREEDY = (rng.random() < 0.8)
                EV_LOG = None; STEP_LOG = None; NOPE_LOG = None
                GIVE_LOG = None; PLACE_LOG = None; AUX = None
            opponents.append(Frozen(name='self'))
        else:
            src = WINNER_FLEET if phase == 'bootstrap' else LOSER_FLEET
            opp = rng.choice(src)(name='fleet')
            opp._play_mode = True  # disable arena handicap during ian_folder
            opponents.append(opp)

    agents = [Learner(name='Hades')] + opponents
    order = list(range(5)); rng.shuffle(order)
    seat = order.index(0)
    r = GameEngine([agents[i] for i in order], collect_events=True).play_game(5)

    if r['winner'] < 0 or not step_log:
        return None, 0.0

    survived = seat in r['survivors']
    terminal = -1.0 if survived else 1.0

    # dense aux from the event log (safe draws penalised)
    safe_draws = sum(1 for e in r.get('events', [])
                     if e.get('type') == 'draw' and e.get('player') == seat)
    reward = terminal + aux['r'] + R_DRAW_SAFE * safe_draws

    return {
        'event_vecs': ev_log,
        'steps': step_log,
        'nope_steps': nope_log,
        'give_steps': give_log,
        'place_steps': place_log,
    }, reward


def rollout_worker(args):
    policy_w, pool_w, n_games, seed, phase, self_prob = args
    import random as _random
    rng = _random.Random(seed); npr = np.random.default_rng(seed)
    out = []
    for _ in range(n_games):
        gd, rew = play_one(policy_w, pool_w, rng, npr, phase, self_prob)
        if gd is not None:
            out.append((gd, rew))
    return out


def _evaluate_chunk(args):
    policy_w, n, seed = args
    import random as _random
    net = _make_net(policy_w)
    rng = _random.Random(seed); npr = np.random.default_rng(seed)

    class Greedy(_HadesLearner):
        NET = net; RNG = npr; GREEDY = True
        EV_LOG = None; STEP_LOG = None; NOPE_LOG = None
        GIVE_LOG = None; PLACE_LOG = None; AUX = None

    survived = 0; games = 0
    for _ in range(n):
        me = Greedy(name='Hades')
        opps = [rng.choice(EVAL_FLEET)(name='fleet') for _ in range(4)]
        for opp in opps:
            opp._play_mode = True
        agents = [me] + opps
        order = list(range(5)); rng.shuffle(order); seat = order.index(0)
        r = GameEngine([agents[i] for i in order], collect_events=True).play_game(5)
        if r['winner'] < 0:
            continue
        games += 1
        if seat in r['survivors']:
            survived += 1
    return survived, games


def evaluate(policy_w, n=2000, seed=99, ex=None):
    """Returns survival rate vs EVAL_FLEET. Lower is better (target < 2%)."""
    if ex is None:
        survived, games = _evaluate_chunk((policy_w, n, seed))
    else:
        import math
        workers = ex._max_workers
        chunk = math.ceil(n / workers)
        futs = [ex.submit(_evaluate_chunk, (policy_w, chunk, seed + i))
                for i in range(workers)]
        survived = games = 0
        for f in futs:
            s, g = f.result()
            survived += s; games += g
    return survived / games if games else 1.0
