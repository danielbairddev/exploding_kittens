"""Play Exploding Kittens vs the bots (human vs AI, no coach)."""
import queue
import random
import threading
import time
import uuid
from collections import Counter

# Unique names drawn for each bot seat so "Elephant 2" etc. never appears.
_BOT_NAMES = [
    "Biscuit", "Mittens", "Whiskers", "Noodle", "Mochi",
    "Pumpkin", "Fuzzy", "Pixel", "Rascal", "Shadow",
    "Tuxedo", "Claws", "Nimbus", "Velvet", "Socks",
    "Patches", "Biscotti", "Zigzag", "Fluffy", "Butterscotch",
]

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
from agents.zeus_agent import ZeusAgent
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
    "Zeus":       (ZeusAgent,        "⚡"),
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
def act_label(a, names=None):
    t = a.action_type.name.replace("PLAY_", "").replace("_", " ").title()
    if a.action_type == ActionType.DRAW:
        return "Draw a card"
    if a.action_type == ActionType.PLAY_SEE_THE_FUTURE:
        return "See the Future"
    if a.target_player is not None:
        cat = f" {a.cat_type.name.replace('_', ' ').title()}" if a.cat_type else ""
        nm = (names[a.target_player] if names and 0 <= a.target_player < len(names)
              else f"P{a.target_player}")
        return f"{t}{cat} → {nm}"
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
        if state.current_player == state.my_id:
            return False  # never nope your own card
        if currently_noped:
            # Don't counter-nope the nope you just played
            recent_nopes = [e for e in getattr(state, 'recent_events', [])
                            if e.get('type') == 'nope']
            if recent_nopes and recent_nopes[-1].get('player') == state.my_id:
                return False
        return self.session.ask_nope(state, action, currently_noped)

    def give_card(self, state, requester_id):
        return self.session.ask_pick(state, "give", requester_id)

    def place_exploding_kitten(self, state, deck_size):
        return self.session.ask_pick(state, "place", deck_size)

    def see_future(self, state, top3):
        # Logged in _flush_events when the public see_future event is processed,
        # so the peeked-cards line stays in sync with the animation log (routing
        # it through note() here desynced the frontend log counter and dropped it).
        self.session._peek_cards = [c.card_type.name for c in top3]


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
        self._peek_cards = None  # set by HumanAgent.see_future, attached to next see_future anim event
        # Track hand between ask_action calls so we can annotate what was drawn/stolen/received
        self._prev_hand = None          # Counter(CardType → count)
        self._delta_added = Counter()   # cards gained since last ask_action
        self._delta_removed = Counter() # cards lost since last ask_action

        # seat 0 = human, then chosen opponents
        self.human = HumanAgent(self)
        agents = [self.human]
        display_names = ["You"]
        # identities: {type, emoji} parallel to display_names for the frontend
        self.identities = [{"type": "human", "emoji": "🧍"}]

        name_pool = random.sample(_BOT_NAMES, k=min(len(_BOT_NAMES), len(opponents)))
        for idx, nm in enumerate(opponents):
            if nm not in PLAYABLE:
                continue
            cls, emoji = PLAYABLE[nm]
            label = name_pool[idx % len(name_pool)]
            bot = cls(name=label)
            bot._play_mode = True  # full strength — no explore-rate noise
            agents.append(bot)
            display_names.append(label)
            self.identities.append({"type": nm, "emoji": emoji})

        self.names = display_names
        self.engine = GameEngine(agents, collect_events=True)
        self.n = len(agents)
        self._lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        # Stream public events (esp. bot explosions) to the frontend live, so
        # deaths animate during the bots' turns instead of only when it returns
        # to the human's turn. The frontend polls /api/play/state every ~600ms.
        self._streamer = threading.Thread(target=self._stream_loop, daemon=True)
        self._streamer.start()

    def _stream_loop(self):
        while self.result is None:
            try:
                self._flush_events(streaming=True)
            except Exception:
                pass
            time.sleep(0.15)

    def _flush_events(self, state=None, streaming=False):
        with self._lock:
            self._flush_locked(streaming)

    def _flush_locked(self, streaming=False):
        """Flush new public events (from the engine log) to the anim queue + log.
        Caller holds self._lock — used by both the human-prompt path and the
        background streamer thread, so bot explosions reach the frontend live.

        When streaming, stop at the human's own favor/cat-steal so the enriched
        'you received X' message is produced by the prompt-path flush instead."""
        _SKIP = {'turn_start', 'game_over'}
        new = sorted(
            [e for e in self.engine._public_events
             if e.get('event_id', 0) > self._last_eid],
            key=lambda e: e.get('event_id', 0)
        )
        for ev in new:
            t   = ev.get('type', '')
            p   = ev.get('player', -1)
            tgt = ev.get('target', ev.get('from_player', -1))

            # Leave the human's own favor/cat-steal for the prompt-path flush,
            # which enriches it with the specific card received.
            if streaming and t in ('favor', 'cat_steal') and p == 0:
                break

            msg = self._fmt_event(ev)
            msg = self._enrich_msg(msg, t, p, tgt)

            # For human draws, use the private event stream to get the actual card name.
            # Delta tracking misses EK draws (EK never enters hand) and end-game draws.
            if t == 'draw' and p == 0:
                card = self._private_draw_card(ev.get('turn'))
                if card:
                    msg = f"**You** draw a **{card}**"

            # Human's own See-the-Future peek: log the exact cards seen (the public
            # event only says "sees the future"; _peek_cards holds the privates).
            if t == 'see_future' and self._peek_cards:
                _pk = [c.replace("_", " ").title() for c in self._peek_cards]
                msg = "🔮 **You** peeked: " + ", ".join(f"**{n}**" for n in _pk)

            if msg:
                self.note(msg)
            if t not in _SKIP:
                aev = {
                    'id': ev.get('event_id', 0),
                    'type': t,
                    'player': p,
                    'target': tgt,
                    'log': msg,
                }
                if t == 'see_future' and self._peek_cards:
                    aev['cards'] = self._peek_cards
                    self._peek_cards = None
                self._anim_events.append(aev)
            self._last_eid = ev.get('event_id', self._last_eid)

    def _card_name(self, ct):
        return ct.name.replace("_", " ").title()

    def _private_draw_card(self, turn):
        """Return the formatted card name drawn by the human in the given game turn,
        looked up from the engine's private event stream (which has card info)."""
        for pe in getattr(self.engine, '_events', []):
            if pe.get('type') == 'draw' and pe.get('player') == 0 and pe.get('turn') == turn:
                card = pe.get('card', '')
                return card.replace('_', ' ').title() if card else None
        return None

    def _enrich_msg(self, msg, t, p, tgt):
        """Replace generic log messages with card-specific ones using hand delta."""
        def _added():
            ct = next(iter(self._delta_added.elements()), None)
            return f"**{self._card_name(ct)}**" if ct else None
        def _removed():
            ct = next(iter(self._delta_removed.elements()), None)
            return f"**{self._card_name(ct)}**" if ct else None

        nm  = self.names[p]   if 0 <= p   < len(self.names) else f"P{p}"
        tnm = self.names[tgt] if 0 <= tgt < len(self.names) else f"P{tgt}"

        if p == 0:  # human is the actor
            if t == 'draw':
                card = _added()
                if card:
                    self._delta_added = Counter()
                    return f"**You** draw a {card}"
            elif t in ('cat_steal', 'favor') and self._delta_added:
                card = _added()
                if card:
                    self._delta_added = Counter()
                    if t == 'cat_steal':
                        return f"🐱 **You** steal a {card} from **{tnm}**"
                    else:
                        return f"🙏 **You** favor **{tnm}** and receive a {card}"
        elif tgt == 0:  # human is the victim
            if t in ('cat_steal', 'favor') and self._delta_removed:
                card = _removed()
                if card:
                    self._delta_removed = Counter()
                    if t == 'cat_steal':
                        return f"🐱 **{nm}** steals a {card} from **You**"
                    # favor: human picks in give_card, note appended there
        return msg

    def _flush_end_events(self):
        """Final flush of events emitted after the last prompt (e.g. the human's
        fatal EK draw, or the last bot exploding to end the game). Lock-guarded
        and idempotent via _last_eid, so it's safe alongside the streamer."""
        self._flush_events()

    def _run(self):
        result = None
        try:
            result = self.engine.play_game(self.n)
        except Exception as exc:
            result = {"winner": -1, "error": repr(exc)}
        # Flush draw/explode/defuse events that fired after the last ask_action,
        # then set self.result so the frontend sees anim events before game-over state.
        self._flush_end_events()
        w = result.get("winner", -1)
        self.note("🎉 You win!" if w == 0 else
                  (f"💀 {self.names[w]} wins — better luck next time." if w >= 0 else "Game over."))
        self.result = result

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
        b, bt = f"**{nm}**", f"**{tnm}**"
        if t == "draw":         return f"{b} {_v('draws')} a card"
        if t == "explode":      return f"💣 {b} exploded!"
        if t == "defuse":       return f"🛡️ {b} defused the kitten!"
        if t == "action_noped": return f"🚫 {b}'s action was cancelled"
        if t == "attack":       return f"⚔️ {b} {_v('attacks')} {bt}"
        if t == "skip":         return f"⏭️ {b} {_v('skips')}"
        if t == "favor":        return f"🙏 {b} {_v('favors')} {bt}"
        if t == "shuffle":      return f"🔀 {b} {_v('shuffles')} the deck"
        if t == "see_future":   return f"🔮 {b} {_v('sees')} the future"
        if t == "nope":         return f"⛔ {b} {_v('nopes')}!"
        if t == "cat_steal":    return f"🐱 {b} {_v('steals')} from {bt}"
        return None

    def note(self, msg):
        self.log.append(msg)
        self.log = self.log[-60:]

    # ---- decision hooks ----
    def ask_action(self, state, valid):
        curr = Counter(c.card_type for c in state.my_hand)
        if self._prev_hand is not None:
            self._delta_added   = curr - self._prev_hand
            self._delta_removed = self._prev_hand - curr
        self._prev_hand = curr
        self._flush_events(state)
        self._delta_added = Counter()    # clear so stale deltas don't leak into nope/pick flushes
        self._delta_removed = Counter()
        self._cur = list(valid)
        self.pending = {
            "kind": "choose_action",
            "state": self._state_view(state),
            "valid": [{"i": i, "label": act_label(a, self.names), "type": a.action_type.name,
                       "target": a.target_player,
                       "cat_type": a.cat_type.name if a.cat_type else None}
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
            "note": f"{'Counter-nope' if currently_noped else 'Nope'} {act_label(action, self.names)}?",
            "action_label": act_label(action, self.names),
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
            given = opts[i]
            self.note(f"🙏 **You** gave away a **{given.name.replace('_', ' ').title()}**")
            return given
        # place: arg = deck_size — human picks exact position via slider.
        # Flush draw + defuse events so they animate before the placement prompt.
        self._flush_events(state)
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
            "identities": self.identities,
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
