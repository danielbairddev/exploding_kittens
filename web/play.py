"""Play Exploding Kittens vs the bots (human vs AI, no coach)."""
import queue
import threading
import time
import uuid

from agents.base import Agent
from agents.orangutan_agent import OrangutanAgent
from agents.rhino_agent import RhinoAgent
from agents.elephant_agent import ElephantAgent
from agents.perdition2_agent import Perdition2Agent
from agents.coyote_agent import CoyoteAgent
from agents.survival_agent import SurvivalAgent
from agents.survival_agent_v2 import SurvivalAgentV2
from agents.aggressive_agent import AggressiveAgent
from agents.chaos_agent import ChaosAgent
from agents.heuristic_agent import HeuristicAgent
from agents.random_agent import RandomAgent
from agents.gabriel_agent import GabrielAgent
from game.engine import GameEngine
from game.actions import Action, ActionType
from game.cards import CardType

NOPE = CardType.NOPE
DEF = CardType.DEFUSE

# All playable opponents (display name → class).
# Gabriel is included here so the server accepts it, but not listed in /api/play/bots.
PLAYABLE = {
    "Rhino":      (RhinoAgent,       "🦏"),
    "Elephant":   (ElephantAgent,    "🐘"),
    "Orangutan":  (OrangutanAgent,   "🦧"),
    "Coyote":     (CoyoteAgent,      "🐺"),
    "Sly2":       (SurvivalAgentV2,  "🦝"),
    "Sly":        (SurvivalAgent,    "🦊"),
    "Maverick":   (AggressiveAgent,  "💥"),
    "Gremlin":    (ChaosAgent,       "🌀"),
    "Professor":  (HeuristicAgent,   "🧠"),
    "Lucky":      (RandomAgent,      "🎲"),
    "Perdition2": (Perdition2Agent,  "🥶"),
    # Secret — not listed in /api/play/bots but accepted by /api/play/new
    "Gabriel":    (GabrielAgent,     "🪬"),
}

# Bots shown publicly in the picker (Gabriel hidden until unlocked client-side)
PUBLIC_BOTS = [k for k in PLAYABLE if k != "Gabriel"]

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
        cat = f" {a.cat_type.name.replace('_', ' ').title()}" if a.cat_type else ""
        return f"{t}{cat} → P{a.target_player}"
    return t


def action_to_dict(a):
    return {"action_type": a.action_type.name,
            "target_player": a.target_player,
            "cat_type": a.cat_type.name if a.cat_type else None}


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
        return self.session.ask_nope(state, action, currently_noped)

    def give_card(self, state, requester_id):
        return self.session.ask_pick(state, "give", requester_id)

    def place_exploding_kitten(self, state, deck_size):
        return self.session.ask_pick(state, "place", deck_size)

    def see_future(self, state, top3):
        names = [c.card_type.name.replace("_", " ").title() for c in top3]
        self.session.note("🔮 You peek: " + ", ".join(names))


class Session:
    def __init__(self, opponents):
        self.id = uuid.uuid4().hex[:12]
        self.log = []
        self.pending = None
        self.result = None
        self.action_in = queue.Queue()
        self._cur = None
        self._last_eid = -1      # last event_id flushed to log
        self._anim_events = []   # structured events for frontend animation

        # seat 0 = human, then chosen opponents
        self.human = HumanAgent(self)
        agents = [self.human]
        display_names = ["You"]
        counts = {}
        for nm in opponents:
            if nm not in PLAYABLE:
                continue
            counts[nm] = counts.get(nm, 0) + 1
            cls, _emoji = PLAYABLE[nm]
            label = nm if counts[nm] == 1 else f"{nm} {counts[nm]}"
            bot = cls(name=label)
            bot._play_mode = True  # full strength — no explore-rate noise
            agents.append(bot)
            display_names.append(label)

        self.names = display_names
        self.engine = GameEngine(agents, collect_events=True)
        self.n = len(agents)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _flush_events(self, state):
        """Log any new events from state.recent_events since last flush."""
        _SKIP = {'turn_start', 'game_over'}
        new = sorted(
            [e for e in getattr(state, 'recent_events', [])
             if e.get('event_id', 0) > self._last_eid],
            key=lambda e: e.get('event_id', 0)
        )
        for ev in new:
            msg = self._fmt_event(ev)
            if msg:
                self.note(msg)
            t = ev.get('type', '')
            if t not in _SKIP:
                self._anim_events.append({
                    'id': ev.get('event_id', 0),
                    'type': t,
                    'player': ev.get('player', -1),
                    # engine uses 'from_player' for favor/cat_steal, 'target' for attack
                    'target': ev.get('target', ev.get('from_player', -1)),
                    'log': msg,   # log message in sync with this animation
                })
            self._last_eid = ev.get('event_id', self._last_eid)

    def _run(self):
        try:
            self.result = self.engine.play_game(self.n)
        except Exception as exc:
            self.result = {"winner": -1, "error": repr(exc)}
        w = self.result.get("winner", -1)
        self.note("🎉 You win!" if w == 0 else
                  (f"💀 {self.names[w]} wins — better luck next time." if w >= 0 else "Game over."))

    def _fmt_event(self, ev):
        t = ev.get("type", "")
        p = ev.get("player", -1)
        nm = self.names[p] if 0 <= p < len(self.names) else f"P{p}"
        # engine uses 'target' for attack but 'from_player' for favor/cat_steal
        tgt = ev.get("target", ev.get("from_player", -1))
        tnm = self.names[tgt] if 0 <= tgt < len(self.names) else f"P{tgt}"
        # conjugate verb for "You" (first person) vs third person
        def _v(third):
            return third[:-1] if nm == "You" and third.endswith("s") else third
        if t == "draw":        return f"{nm} {_v('draws')} a card"
        if t == "explode":     return f"💣 {nm} exploded!"
        if t == "defuse":      return f"🛡️ {nm} defused the kitten!"
        if t == "attack":      return f"⚔️ {nm} {_v('attacks')} {tnm}"
        if t == "skip":        return f"⏭️ {nm} {_v('skips')}"
        if t == "favor":       return f"🙏 {nm} {_v('favors')} {tnm}"
        if t == "shuffle":     return f"🔀 {nm} {_v('shuffles')} the deck"
        if t == "see_future":  return f"🔮 {nm} {_v('sees')} the future"
        if t == "nope":        return f"⛔ {nm} {_v('nopes')}!"
        if t == "cat_steal":   return f"🐱 {nm} {_v('steals')} from {tnm}"
        return None

    def note(self, msg):
        self.log.append(msg)
        self.log = self.log[-60:]

    # ---- decision hooks ----
    def ask_action(self, state, valid):
        self._flush_events(state)
        self._cur = list(valid)
        self.pending = {
            "kind": "choose_action",
            "state": self._state_view(state),
            "valid": [{"i": i, "label": act_label(a), "type": a.action_type.name}
                      for i, a in enumerate(valid)],
        }
        chosen = self.action_in.get()
        self.pending = None
        return chosen

    def ask_nope(self, state, action, currently_noped):
        # Collect nope events that just happened (current chain) before flushing
        nope_chain = []
        for ev in getattr(state, 'recent_events', []):
            if ev.get('type') == 'nope' and ev.get('event_id', 0) > self._last_eid:
                p = ev.get('player', -1)
                nope_chain.append({
                    'name': self.names[p] if 0 <= p < len(self.names) else f'P{p}',
                    'result': ev.get('result', ''),
                })

        self._flush_events(state)

        actor = state.current_player
        actor_name = self.names[actor] if 0 <= actor < len(self.names) else f'P{actor}'

        self.pending = {
            "kind": "nope",
            "state": self._state_view(state),
            "note": f"{'Counter-nope' if currently_noped else 'Nope'} {act_label(action)}?",
            "action_label": act_label(action),
            "action_type": action.action_type.name,
            "actor_name": actor_name,
            "currently_noped": currently_noped,
            "nope_chain": nope_chain,
            "valid": [{"i": 0, "label": "⛔ Nope it!", "type": "NOPE"},
                      {"i": 1, "label": "✅ Let it happen", "type": "PASS"}],
        }
        i = self.action_in.get()
        self.pending = None
        return i == 0

    def ask_pick(self, state, kind, arg):
        if kind == "give":
            # Engine emits the favor event only AFTER give_card returns, so synthesise
            # it now with a fractional ID so the animation plays before the give prompt.
            requester = arg
            req_nm = self.names[requester] if 0 <= requester < len(self.names) else f'P{requester}'
            self._anim_events.append({
                'id': self._last_eid + 0.5,
                'type': 'favor',
                'player': requester,
                'target': 0,  # human is always seat 0
                'log': f"🙏 {req_nm} favors You",
            })
            self._flush_events(state)
            opts = sorted({c.card_type for c in state.my_hand}, key=lambda t: t.name)
            self.pending = {
                "kind": "give",
                "state": self._state_view(state),
                "options": [{"i": i, "label": t.name.replace("_", " ").title(),
                             "type": t.name}
                            for i, t in enumerate(opts)],
                "note": f"{self.names[arg]} played a Favor — pick a card to give.",
            }
            i = self.action_in.get()
            self.pending = None
            return opts[i]
        # place: arg = deck_size — human picks exact position via slider
        self.pending = {
            "kind": "place_exact",
            "state": self._state_view(state),
            "deck_size": arg,
            "note": "You defused! 🛡️ Where do you bury the kitten?",
        }
        pos = self.action_in.get()
        self.pending = None
        return max(0, min(arg, int(pos)))

    def submit(self, i):
        p = self.pending
        self.pending = None
        if p and p["kind"] == "choose_action":
            self.action_in.put(self._cur[i])
        else:
            self.action_in.put(i)  # raw value for nope/give/place_exact

    # ---- state view ----
    def _state_view(self, state):
        from collections import Counter
        hand = Counter(c.card_type.name for c in state.my_hand)
        disc = state.discard_pile[-8:]
        return {
            "my_hand": [{"type": t, "n": n} for t, n in sorted(hand.items())],
            "hand_sizes": {str(k): v for k, v in state.hand_sizes.items()},
            "alive": state.alive_players,
            "deck_size": state.deck_size,
            "turns_remaining": state.turns_remaining,
            "current_player": state.current_player,
            "discard_pile": [c.card_type.name for c in disc],
            "names": self.names,
        }

    def snapshot(self):
        return {
            "id": self.id,
            "pending": self.pending,
            "result": self.result,
            "log": self.log[-20:],
            "names": self.names,
            "anim_events": self._anim_events[-100:],
        }

    def wait(self, timeout=25):
        end = time.time() + timeout
        while time.time() < end and self.pending is None and self.result is None:
            time.sleep(0.02)
        return self.snapshot()


def new_session(opponents):
    opponents = [o for o in opponents if o in PLAYABLE][:4]
    if not opponents:
        opponents = ["Coyote", "Rhino", "Lucky"]
    s = Session(opponents)
    with _LOCK:
        SESSIONS[s.id] = s
        if len(SESSIONS) > 60:
            for k in list(SESSIONS)[:-60]:
                SESSIONS.pop(k, None)
    return s.wait()


def act(session_id, choice):
    s = SESSIONS.get(session_id)
    if not s:
        return {"error": "no session"}
    s.submit(choice)
    return s.wait()


def state(session_id):
    s = SESSIONS.get(session_id)
    return s.snapshot() if s else {"error": "no session"}
