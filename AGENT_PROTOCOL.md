# Exploding Kittens — Agent Protocol

Agents run as separate HTTP processes. The game engine calls your server; you respond with JSON. Any language works.

---

## Running your agent

```
python agents/agent_server.py --agent heuristic --port 5001 --name "MyBot"
```

Or implement the protocol below in any language and point the controller at your port.

---

## Endpoints

All endpoints accept and return `application/json`.

### `GET /health`
Health check. Return `{"status": "ok"}` when ready.

---

### `POST /game_start`
Called once at the start of each game.

**Request**
```json
{ "state": <ObservableState> }
```
**Response** `{}`

---

### `POST /choose_action`
Called on your turn. Return one of the provided `valid_actions`.

**Request**
```json
{
  "state": <ObservableState>,
  "valid_actions": [ <Action>, ... ]
}
```
**Response**
```json
{ <Action> }
```
Return a valid action. Returning `DRAW` ends your play phase and draws a card. You can play multiple cards per turn — the engine calls this repeatedly until you return `DRAW` or your turn ends.

---

### `POST /want_to_nope`
Called for every player whenever any card is played (including during counter-Nope chains). Return `true` to spend one of your Nope cards.

**Request**
```json
{
  "state": <ObservableState>,
  "action": <Action>,
  "currently_noped": false
}
```
- `currently_noped: true` means the action is currently cancelled — returning `true` here is a **counter-Nope** (restores the action).
- This is called in rounds until nobody plays a Nope. Each `true` response costs one Nope card from your hand.

**Response**
```json
{ "nope": true }
```

---

### `POST /give_card`
Called when another player's Favor targets you. Return a card type you hold.

**Request**
```json
{
  "state": <ObservableState>,
  "requester_id": 2
}
```
**Response**
```json
{ "card_type": "SKIP" }
```

---

### `POST /place_exploding_kitten`
Called after you defuse an Exploding Kitten. Return where to reinsert it (`0` = top of deck, `deck_size` = bottom).

**Request**
```json
{
  "state": <ObservableState>,
  "deck_size": 14
}
```
**Response**
```json
{ "position": 14 }
```

---

### `POST /see_future`
Called after you play See the Future. No response needed.

**Request**
```json
{
  "state": <ObservableState>,
  "top3": [ <Card>, <Card>, <Card> ]
}
```
**Response** `{}`

---

## Shapes

### Card
```json
{ "card_type": "ATTACK" }
```
`card_type` is one of:
`EXPLODING_KITTEN`, `DEFUSE`, `ATTACK`, `SKIP`, `FAVOR`, `SHUFFLE`, `SEE_THE_FUTURE`, `NOPE`,
`TACO_CAT`, `HAIRY_POTATO_CAT`, `BEARD_CAT`, `RAINBOW_CAT`, `CATTERMELON`

---

### Action
```json
{
  "action_type": "PLAY_ATTACK",
  "target_player": null,
  "cat_type": null,
  "named_card": null,
  "defuse_position": null
}
```

`action_type` values:

| Value | Description |
|---|---|
| `DRAW` | End play phase and draw a card |
| `PLAY_ATTACK` | Skip your draw, force next player to take 2 turns |
| `PLAY_SKIP` | End this turn without drawing |
| `PLAY_FAVOR` | Force `target_player` to give you a card |
| `PLAY_SHUFFLE` | Shuffle the deck |
| `PLAY_SEE_THE_FUTURE` | Peek at the top 3 cards |
| `PLAY_CAT_PAIR` | Play 2 matching cat cards to steal a random card from `target_player` |
| `PLAY_CAT_TRIPLE` | Play 3 matching cat cards to demand `named_card` from `target_player` |

`target_player` — required for `PLAY_FAVOR`, `PLAY_CAT_PAIR`, `PLAY_CAT_TRIPLE`  
`cat_type` — required for `PLAY_CAT_PAIR`, `PLAY_CAT_TRIPLE`  
`named_card` — optional for `PLAY_CAT_TRIPLE`; if set and target has it, they must give it

---

### ObservableState
```json
{
  "my_id": 0,
  "my_hand": [ <Card>, ... ],
  "hand_sizes": { "0": 7, "1": 5, "2": 6 },
  "alive_players": [0, 1, 2],
  "deck_size": 18,
  "discard_pile": [ <Card>, ... ],
  "turns_remaining": 1,
  "current_player": 0,
  "known_top3": null
}
```

- `my_hand` — your full hand (only you see this)
- `hand_sizes` — how many cards each player holds
- `turns_remaining` — >1 if you're under an Attack
- `known_top3` — populated after you play See the Future; `null` otherwise

---

## Running a distributed simulation

```bash
python simulation/controller.py --games 100 --agents heuristic random heuristic random
```

To plug in your own server, pass its port via the `--port` flag (see controller source) or modify `run_distributed()` directly with a pre-built spec list.
