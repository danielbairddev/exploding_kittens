"""Play Exploding Kittens vs the bots, with an optional Orangutan coach.

Each session runs a real GameEngine in a daemon thread; the human is a
HumanAgent whose decision methods block until the browser submits a move. The
coach (when on) reports what Orangutan would play and the Monte-Carlo
expected-value loss of the human's move (win-probability rollouts from the true
game state, playing it out with Orangutan in the hero's seat).
"""
import copy
import queue
import threading
import time
import uuid

from agents.base import Agent
from agents.orangutan_agent import OrangutanAgent
from agents.coyote_agent import CoyoteAgent
from agents.survival_agent import SurvivalAgent
from agents.survival_agent_v2 import SurvivalAgentV2
from agents.aggressive_agent import AggressiveAgent
from agents.chaos_agent import ChaosAgent
from agents.heuristic_agent import HeuristicAgent
from agents.random_agent import RandomAgent
from game.engine import GameEngine
from game.actions import Action, ActionType
from game.cards import CardType

NOPE = CardType.NOPE
DEF = CardType.DEFUSE

# Opponents you can pick (display name -> class). Mirrors the arena personas.
PLAYABLE = {
    "Orangutan": (OrangutanAgent, "\U0001F9A7"), "Coyote": (CoyoteAgent, "\U0001F43A"),
    "Sly2": (SurvivalAgentV2, "\U0001F99D"), "Sly": (SurvivalAgent, "\U0001F98A"),
    "Maverick": (AggressiveAgent, "\U0001F4A5"), "Gremlin": (ChaosAgent, "\U0001F300"),
    "Professor": (HeuristicAgent, "\U0001F9E0"), "Lucky": (RandomAgent, "\U0001F3B2"),
}
MC_ROLLOUTS = 120

SESSIONS = {}
_LOCK = threading.Lock()


# --------------------------------------------------------------------------
def act_label(a):
    t = a.action_type.name.replace("PLAY_", "").replace("_", " ").title()
    if a.action_type == ActionType.DRAW:
        return "Draw a card"
    if a.action_type == ActionType.PLAY_SEE_THE_FUTURE:
        return "See the Future"
    if a.target_player is not None:
        cat = f" {a.cat_type.name.replace('_',' ').title()}" if a.cat_type else ""
        return f"{t}{cat} → P{a.target_player}"
    return t


def action_to_dict(a):
    return {"action_type": a.action_type.name,
            "target_player": a.target_player,
            "cat_type": a.cat_type.name if a.cat_type else None}


class ForcedFirst(OrangutanAgent):
    """For coach rollouts: play a forced action once, then play as Orangutan."""
    def __init__(self, action, name="hero"):
        super().__init__(name)
        self._forced = action
        self._used = False

    def choose_action(self, state, valid_actions):
        if not self._used:
            self._used = True
            return self._forced
        return super().choose_action(state, valid_actions)


def mc_winrate(snapshot, first_action, seat_classes, hero_seat, n=MC_ROLLOUTS):
    wins = 0
    for _ in range(n):
        s = copy.deepcopy(snapshot)
        agents = [ForcedFirst(first_action) if i == hero_seat else seat_classes[i]()
                  for i in range(len(s.players))]
        res = GameEngine(agents).play_out(s)
        if res["winner"] == hero_seat:
            wins += 1
    return wins / n


# --------------------------------------------------------------------------
class HumanAgent(Agent):
    def __init__(self, session):
        self.session = session
        self.name = "You"

    def game_start(self, state):
        pass

    def choose_action(self, state, valid_actions):
        return self.session.ask_action(state, valid_actions)

    def want_to_nope(self, state, action, currently_noped=False):
        return False                       # v1: human doesn't Nope (bots still do)

    def give_card(self, state, requester_id):
        return self.session.ask_pick(state, "give", requester_id)

    def place_exploding_kitten(self, state, deck_size):
        return self.session.ask_pick(state, "place", deck_size)

    def see_future(self, state, top3):
        names = [c.card_type.name.replace("_", " ").title() for c in top3]
        self.session.note("\U0001F52E You peek: " + ", ".join(names))


class Session:
    def __init__(self, opponents, coach):
        self.id = uuid.uuid4().hex[:12]
        self.coach = coach
        self.log = []
        self.pending = None
        self.result = None
        self.coach_feedback = None
        self.action_in = queue.Queue()
        self._cur = None                   # current valid actions (Action objects)
        self._snap = None                  # deepcopy of true state at decision
        self._orec = None                  # Orangutan's recommended action
        # seat 0 = human, then the chosen opponents in order
        self.human = HumanAgent(self)
        self.seat_classes = [None]         # index 0 = human (no class)
        agents = [self.human]
        for nm in opponents:
            cls = PLAYABLE[nm][0]
            self.seat_classes.append(cls)
            agents.append(cls(name=nm))
        self.names = ["You"] + list(opponents)
        self.engine = GameEngine(agents, collect_events=False)
        self.n = len(agents)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        try:
            self.result = self.engine.play_game(self.n)
        except Exception as exc:                      # never wedge the session
            self.result = {"winner": -1, "error": repr(exc)}
        w = self.result.get("winner", -1)
        self.note("\U0001F389 You win!" if w == 0 else
                  (f"\U0001F480 {self.names[w]} wins — better luck next time." if w >= 0 else "Game over."))

    def note(self, msg):
        self.log.append(msg)
        self.log = self.log[-40:]

    # ---- decision hooks (run in the game thread; block on the human) ----
    def ask_action(self, state, valid):
        self._cur = list(valid)
        if self.coach and self.engine._state is not None:
            self._snap = copy.deepcopy(self.engine._state)
            self._orec = OrangutanAgent(name="coach").choose_action(state, valid)
        self.pending = {
            "kind": "choose_action",
            "state": self._state_view(state),
            "valid": [{"i": i, "label": act_label(a)} for i, a in enumerate(valid)],
            "orangutan": act_label(self._orec) if (self.coach and self._orec) else None,
        }
        chosen = self.action_in.get()                 # block for the human
        self.pending = None
        if self.coach and self._snap is not None:
            self._grade(chosen)
        return chosen

    def ask_pick(self, state, kind, arg):
        if kind == "give":
            opts = sorted({c.card_type for c in state.my_hand}, key=lambda t: t.name)
            self.pending = {"kind": "give", "state": self._state_view(state),
                            "options": [{"i": i, "label": t.name.replace("_", " ").title()}
                                        for i, t in enumerate(opts)],
                            "note": f"P{arg} played a Favor — pick a card to give."}
            i = self.action_in.get(); self.pending = None
            return opts[i]
        # place: arg = deck_size
        opts = [("Top (next player draws it!)", 0), ("Middle", arg // 2), ("Bottom (safe)", arg)]
        self.pending = {"kind": "place", "state": self._state_view(state),
                        "options": [{"i": i, "label": l} for i, (l, _) in enumerate(opts)],
                        "note": "You defused! Where do you put the kitten back?"}
        i = self.action_in.get(); self.pending = None
        return opts[i][1]

    def submit(self, i):
        p = self.pending
        self.pending = None              # clear NOW so wait() blocks for the next decision
        if p and p["kind"] == "choose_action":
            self.action_in.put(self._cur[i])
        else:
            self.action_in.put(i)

    def _grade(self, chosen):
        # Evaluate the actual options by rollout (always include the human's
        # move); recommend the rollout-best so the advice and the EV agree.
        cands = [chosen]
        for a in self._cur:
            if a is chosen:
                continue
            if len(cands) >= 6:
                break
            cands.append(a)
        evs = [(a, mc_winrate(self._snap, a, self.seat_classes, 0)) for a in cands]
        your_ev = next(ev for a, ev in evs if a is chosen)
        best_a, best_ev = max(evs, key=lambda t: t[1])
        loss = max(0.0, best_ev - your_ev)
        match = best_a is chosen
        self.coach_feedback = {"match": match, "your_move": act_label(chosen),
                               "best_move": act_label(best_a),
                               "your_ev": round(your_ev * 100, 1), "best_ev": round(best_ev * 100, 1),
                               "ev_loss": round(loss * 100, 1),
                               "orangutan": act_label(self._orec) if self._orec else None}
        tag = ("✅ optimal" if match else "⚠️ blunder" if loss >= 0.08 else
               "\U0001F7E1 slight miss" if loss >= 0.02 else "≈ fine")
        self.note(f"{tag} Coach: you played {act_label(chosen)} ({your_ev*100:.0f}% win); "
                  f"best is {act_label(best_a)} ({best_ev*100:.0f}% win) — EV loss {loss*100:.1f}%")
        self._snap = None

    # ---- views ----
    def _state_view(self, state):
        from collections import Counter
        hand = Counter(c.card_type.name for c in state.my_hand)
        disc = state.discard_pile[-6:]
        return {
            "my_hand": [{"type": t, "n": n} for t, n in sorted(hand.items())],
            "hand_sizes": {str(k): v for k, v in state.hand_sizes.items()},
            "alive": state.alive_players, "deck_size": state.deck_size,
            "turns_remaining": state.turns_remaining, "current_player": state.current_player,
            "discard_top": disc[-1].card_type.name if disc else None,
            "names": self.names,
        }

    def snapshot(self):
        return {"id": self.id, "pending": self.pending, "result": self.result,
                "log": self.log[-12:], "coach": self.coach_feedback, "names": self.names,
                "coach_on": self.coach}

    def wait(self, timeout=25):
        end = time.time() + timeout
        while time.time() < end and self.pending is None and self.result is None:
            time.sleep(0.02)
        return self.snapshot()


def new_session(opponents, coach):
    opponents = [o for o in opponents if o in PLAYABLE][:4]
    if not opponents:
        opponents = ["Coyote", "Sly2", "Lucky"]
    s = Session(opponents, coach)
    with _LOCK:
        SESSIONS[s.id] = s
        if len(SESSIONS) > 60:                        # cap memory
            for k in list(SESSIONS)[:-60]:
                SESSIONS.pop(k, None)
    return s.wait()


def act(session_id, choice):
    s = SESSIONS.get(session_id)
    if not s:
        return {"error": "no session"}
    s.coach_feedback = None
    s.submit(choice)
    return s.wait()


def state(session_id):
    s = SESSIONS.get(session_id)
    return s.snapshot() if s else {"error": "no session"}
