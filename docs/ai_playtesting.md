# AI playtesting (D2): an AI plays a running play-test

D1 ([runtime_debugger.md](runtime_debugger.md)) lets an AI look at the game running in a Mesh Studio play-test. D2
lets it play that game: walk the player, talk to people and choose in conversations, with **the player's own
controls**. After each action it sees what happened.

There is one MCP tool, `debug_play_action(action, direction, frames, choice)`, with four bounded actions:

| `action` | What it presses | Refused when |
| --- | --- | --- |
| `move` | Holds the key bound to `move_up` / `move_down` / `move_left` / `move_right` (`direction` up/down/left/right) for `frames` (1 to 120). | A conversation is on screen (`dialogue_open`); invalid direction or frames (`invalid_action`). |
| `interact` | Taps the key bound to `interact`, to talk to or use what's in front of the player. | A conversation is on screen (`dialogue_open`): advance or choose instead. |
| `advance` | Taps `interact` during a conversation, for the next line. | No conversation (`no_dialogue`); the line waits for a choice (`choice_needed`). |
| `choose` | Moves the choice cursor with `move_up` / `move_down`, then confirms with `interact`. `choice` is a choice's `index` or its exact words. | No choices on screen (`no_choices`); not one of them, or one that can't be made now (`choice_not_available`). |

It answers `{ok, action, snapshot}`:

- `action` gives the action's `status` (`done` or `cancelled`), where the player and room were `before` and are
  `after` it, and the conversation now (`dialogue`).
- `snapshot` is D1's snapshot of the running game, taken afterwards. It now also lists what is around the player:
  `nearby` holds the nearest entities within 320 px, nearest first, with their offsets `dx` / `dy`. `dialogue` holds
  who is speaking, the line, the choices and which one is selected.

The code is in `engine/runtime_play.py` (`PlayDriver`, `request_action`). Studio's side is `StudioAIHost.debug_act*`
in `engine/studio_ai.py`, and `Studio.on_update` / `stop` / `toggle_ai_gameplay_control` in `engine/studio.py`.

## The person decides

Playing is a **separate permission**, off until the person turns it on, and only for that Studio session.

- **Turning it on:** in Studio, open **AI** in the top bar and click **Let an AI play: Off** to turn it On.
- **Separate from D1:** being allowed to start and stop play-tests doesn't include it.
- **While a play-test runs:** the play bar shows **AI may play**. Clicking it takes the permission back at once, and
  cancels whatever the AI is doing.
- **Without permission,** every action answers `gameplay_control_off` and nothing is pressed.

## How an action runs

- **Input:** every action is the game's own input. It sends key presses and releases to the window, for the keys the
  game binds to the actions above, so the game's rules apply as they do to a player: collisions, doors,
  conversations, quests. Nothing else is reachable: no other keys, no code, no state set directly, no project files,
  and no proposals accepted.
- **Timing:** Studio runs the action on its main thread, a frame at a time, before the game updates.
  - A move held for `frames` is down for exactly that many of the game's updates.
  - A choice confirms only if the cursor landed on the choice that was meant. The cursor skips choices that can't be
    made, so if it lands elsewhere the action is `cancelled` and nothing is chosen.
- **One at a time:** another request answers `action_running`.
- **Refused before it starts** (nothing pressed) when:
  - Studio isn't playing (`not_playing`);
  - the game is paused (`game_paused`), over (`game_over`), or has taken the controls for a cutscene
    (`input_locked`);
  - the person is holding a key the action needs (`person_using_controls`).
- **Cancelled mid-way**, its key released at once, when:
  - the person takes the permission back;
  - the play-test stops;
  - the game pauses;
  - Studio closes;
  - the AI cancels it.
- **Never runs past its frames.**
- **Over the bridge:** starting an action and reading its progress are short requests on the authenticated loopback
  bridge's main-thread queue. A frozen Studio answers `timeout` as for every request.
  - The MCP tool waits up to 90 s for the action, polling. Past that, it cancels the action and answers
    `action_timeout`.
  - A software renderer is slow: 120 frames can take several seconds there.
- **Endpoints:** `POST /live/debug/act`, `GET /live/debug/act?id=`, `POST /live/debug/act/cancel`.

## A playtest, as it ran

`tooling/d2_ai_playtest_scenario.py` uses D1's disposable project:

- the starter room with its Guide, whose choice "I'll light it." sets `agreed_to_help`;
- a Cellar through a door north of the player;
- an `auto_start` quest that moves from `agree` to `cellar` on that flag.

How it runs:

- Mesh Studio opens it in a hidden window with its live session on.
- Every game action below is the real MCP tool, called on another thread while the window keeps running.
- The AI steers only by what the tool tells it.
- The person's part is done with Studio's own buttons.

The responses are verbatim from that run (`docs/reviews/d2_ai_playtest_transcript.json`). Long ones are shortened
where marked. `tests/test_ai_playtest_gpu.py` runs the same scenario in the GPU lane.

**1. Nothing is allowed yet.**

`debug_play_action {"action": "interact"}`

```json
{
 "message": "Mesh Studio hasn't allowed an AI to play (move, talk, choose), so nothing was pressed. The person can allow it in Studio (top bar: AI, then \"Let an AI play\"), for this session. Starting play-tests is a separate permission and doesn't include this.",
 "mode": "live_studio",
 "ok": false,
 "reason": "gameplay_control_off"
}
```

**2. The person allows play-tests only.** The AI starts one, but playing it is still refused. Then it stops it.

`debug_play_action {"action": "move", "direction": "right", "frames": 10}`

```json
{
 "message": "Mesh Studio hasn't allowed an AI to play (move, talk, choose), so nothing was pressed. The person can allow it in Studio (top bar: AI, then \"Let an AI play\"), for this session. Starting play-tests is a separate permission and doesn't include this.",
 "mode": "live_studio",
 "ok": false,
 "reason": "gameplay_control_off"
}
```

**3. The person allows AI play too**, and the AI starts a new play-test. Requests that can't apply are refused with
reasons, for example:

`debug_play_action {"action": "jump"}`

```json
{
 "message": "action must be one of move, interact, advance, choose, not 'jump'.",
 "mode": "live_studio",
 "ok": false,
 "reason": "invalid_action"
}
```

`debug_play_action {"action": "advance"}`

```json
{
 "message": "There's no conversation on screen to advance.",
 "mode": "live_studio",
 "ok": false,
 "reason": "no_dialogue"
}
```

**4. To the Guide.** The AI reads the Guide's offset (`dx`) in `nearby` and moves right until she is within reach.
The moves and where they left the player (frames, then `[x, y]`): [(1, [130.5, 128.0]), (30, [205.5, 128.0]), (17, [248.0, 128.0]), (7, [265.5, 128.0]), (2, [270.5, 128.0]), (2, [275.5, 128.0]), (2, [280.5, 128.0])]. The first move's answer, with its
snapshot's `player` and `nearby`:

`debug_play_action {"action": "move", "direction": "right", "frames": 1}`

```json
{
 "action": {
  "action": {
   "action": "move",
   "direction": "right",
   "frames": 1
  },
  "action_id": "a1",
  "after": {
   "player": [
    130.5,
    128.0
   ],
   "scene": "packs/core_regions/scenes/start.json"
  },
  "before": {
   "player": [
    128.0,
    128.0
   ],
   "scene": "packs/core_regions/scenes/start.json"
  },
  "dialogue": {
   "available": true,
   "open": false
  },
  "frames": 6,
  "mode": "live_studio",
  "ok": true,
  "status": "done"
 },
 "ok": true,
 "snapshot": {
  "nearby": {
   "available": true,
   "entities": [
    {
     "distance": 128.0,
     "dx": -2.5,
     "dy": 128.0,
     "id": "start_arrival_cellar_128_256_0_0",
     "name": "Arrival from Cellar",
     "tag": "spawn_point",
     "x": 128.0,
     "y": 256.0
    },
    {
     "distance": 189.5,
     "dx": 189.5,
     "dy": 0.0,
     "id": "start_guide_320_128_0_0",
     "name": "Guide",
     "tag": "npc",
     "x": 320.0,
     "y": 128.0
    },
    {
     "distance": 224.0,
     "dx": -2.5,
     "dy": 224.0,
     "id": "start_door_to_cellar_128_352_0_0",
     "name": "Door to Cellar",
     "tag": "door",
     "x": 128.0,
     "y": 352.0
    }
   ],
   "radius": 320.0,
   "within": 3
  },
  "player": {
   "available": true,
   "id": "start_player_128_128_0_0",
   "name": "Player",
   "tag": "player",
   "units": "pixels",
   "x": 130.5,
   "y": 128.0
  }
 }
}
```

(Excerpt: `action` as returned; `snapshot` shortened to `player`, `nearby`.)

It talks to her. The conversation and its choices come back in `action.dialogue`:

`debug_play_action {"action": "interact"}`

```json
{
 "action": {
  "action": {
   "action": "interact"
  },
  "action_id": "a8",
  "after": {
   "player": [
    280.5,
    128.0
   ],
   "scene": "packs/core_regions/scenes/start.json"
  },
  "before": {
   "player": [
    280.5,
    128.0
   ],
   "scene": "packs/core_regions/scenes/start.json"
  },
  "dialogue": {
   "available": true,
   "choices": [
    {
     "available": true,
     "index": 0,
     "text": "I'll light it."
    },
    {
     "available": true,
     "index": 1,
     "text": "Not now."
    }
   ],
   "open": true,
   "selected": 0,
   "speaker": "Guide",
   "text": "The cellar lantern has gone out. Will you light it?"
  },
  "frames": 7,
  "mode": "live_studio",
  "ok": true,
  "status": "done"
 },
 "ok": true
}
```

(Excerpt: `action` as returned; `snapshot` shortened to nothing.)

While the choice is on screen, actions that don't fit are refused, for example:

`debug_play_action {"action": "advance"}`

```json
{
 "dialogue": {
  "available": true,
  "choices": [
   {
    "available": true,
    "index": 0,
    "text": "I'll light it."
   },
   {
    "available": true,
    "index": 1,
    "text": "Not now."
   }
  ],
  "open": true,
  "selected": 0,
  "speaker": "Guide",
  "text": "The cellar lantern has gone out. Will you light it?"
 },
 "message": "This line waits for a choice: choose one.",
 "mode": "live_studio",
 "ok": false,
 "reason": "choice_needed"
}
```

It chooses "I'll light it.", then advances to the end of the conversation:

`debug_play_action {"action": "choose", "choice": "I'll light it."}`

```json
{
 "action": {
  "action": {
   "action": "choose",
   "choice": 0,
   "text": "I'll light it."
  },
  "action_id": "a9",
  "after": {
   "player": [
    280.5,
    128.0
   ],
   "scene": "packs/core_regions/scenes/start.json"
  },
  "before": {
   "player": [
    280.5,
    128.0
   ],
   "scene": "packs/core_regions/scenes/start.json"
  },
  "dialogue": {
   "available": true,
   "choices": [],
   "open": true,
   "selected": null,
   "speaker": "Guide",
   "text": "Thank you! The cellar door is just north of here."
  },
  "frames": 7,
  "mode": "live_studio",
  "ok": true,
  "status": "done"
 },
 "ok": true
}
```

(Excerpt: `action` as returned; `snapshot` shortened to nothing.)

The game now has the flag, and the quest has moved from `agree` to `cellar`, with the events that did it, in
order:

`debug_runtime_snapshot {"events": 12}` (excerpt: `game_state.flags`, `quests.quests`, and the events' `seq`, `type`
and `stage_id`)

```json
{
 "events": [
  [
   4,
   "quest_stage_started",
   "agree"
  ],
  [
   5,
   "dialogue_started",
   null
  ],
  [
   6,
   "dialogue_line",
   null
  ],
  [
   7,
   "dialogue_choice",
   null
  ],
  [
   8,
   "dialogue_line",
   null
  ],
  [
   9,
   "quest_stage_completed",
   "agree"
  ],
  [
   10,
   "quest_stage_started",
   "cellar"
  ],
  [
   11,
   "dialogue_finished",
   null
  ]
 ],
 "flags": {
  "agreed_to_help": true,
  "hint_shown_quest_log": true
 },
 "quests": [
  {
   "auto_start": true,
   "awaiting_stage": null,
   "completed_stages": [
    "agree"
   ],
   "completed_stages_total": 1,
   "current_stage": "cellar",
   "id": "light_the_lantern",
   "status": "active",
   "title": "Light the cellar lantern",
   "total_stages": 2
  }
 ]
}
```

**5. Through the door.** The AI lines up under the door, then walks up until the room changes. The moves
(direction, frames, then where they left the player): [('left', 1, {'player': [278.0, 128.0], 'scene': 'packs/core_regions/scenes/start.json'}), ('left', 37, {'player': [185.5, 128.0], 'scene': 'packs/core_regions/scenes/start.json'}), ('left', 14, {'player': [150.5, 128.0], 'scene': 'packs/core_regions/scenes/start.json'}), ('left', 5, {'player': [138.0, 128.0], 'scene': 'packs/core_regions/scenes/start.json'}), ('left', 2, {'player': [133.0, 128.0], 'scene': 'packs/core_regions/scenes/start.json'}), ('up', 20, {'player': [133.0, 178.0], 'scene': 'packs/core_regions/scenes/start.json'}), ('up', 20, {'player': [133.0, 228.0], 'scene': 'packs/core_regions/scenes/start.json'}), ('up', 20, {'player': [133.0, 278.0], 'scene': 'packs/core_regions/scenes/start.json'}), ('up', 20, {'player': [256.0, 128.0], 'scene': 'packs/core_regions/scenes/cellar.json'})]. The last one:

`debug_play_action {"action": "move", "direction": "up", "frames": 20}`

```json
{
 "action": {
  "action": {
   "action": "move",
   "direction": "up",
   "frames": 20
  },
  "action_id": "a19",
  "after": {
   "player": [
    256.0,
    128.0
   ],
   "scene": "packs/core_regions/scenes/cellar.json"
  },
  "before": {
   "player": [
    133.0,
    278.0
   ],
   "scene": "packs/core_regions/scenes/start.json"
  },
  "dialogue": {
   "available": true,
   "open": false
  },
  "frames": 25,
  "mode": "live_studio",
  "ok": true,
  "status": "done"
 },
 "ok": true,
 "snapshot": {
  "scene": {
   "available": true,
   "path": "packs/core_regions/scenes/cellar.json",
   "room": {
    "key": "cellar",
    "label": "Cellar"
   }
  }
 }
}
```

(Excerpt: `action` as returned; `snapshot` shortened to `scene`.)

**6. The person takes the permission back** (the play bar's **AI may play**) during a 120-frame move. The move comes
back cancelled after a few frames, its key let go, and the next action is refused:

`debug_play_action {"action": "move", "direction": "down", "frames": 120}`

```json
{
 "action": {
  "action": {
   "action": "move",
   "direction": "down",
   "frames": 120
  },
  "action_id": "a20",
  "after": {
   "player": [
    256.0,
    103.0
   ],
   "scene": "packs/core_regions/scenes/cellar.json"
  },
  "before": {
   "player": [
    256.0,
    128.0
   ],
   "scene": "packs/core_regions/scenes/cellar.json"
  },
  "dialogue": {
   "available": true,
   "open": false
  },
  "frames": 10,
  "message": "Cancelled: the person took back the permission to play.",
  "mode": "live_studio",
  "ok": false,
  "reason": "cancelled",
  "status": "cancelled"
 },
 "ok": false
}
```

(Excerpt: `action` as returned; `snapshot` shortened to nothing.)

`debug_play_action {"action": "move", "direction": "down", "frames": 5}`

```json
{
 "message": "Mesh Studio hasn't allowed an AI to play (move, talk, choose), so nothing was pressed. The person can allow it in Studio (top bar: AI, then \"Let an AI play\"), for this session. Starting play-tests is a separate permission and doesn't include this.",
 "mode": "live_studio",
 "ok": false,
 "reason": "gameplay_control_off"
}
```

**7. With no play-test**, an action is refused even once the person allows playing again:

`debug_play_action {"action": "interact"}`

```json
{
 "message": "Mesh Studio isn't play-testing, so there's no game to play. debug_start_playtest starts one (if the person allowed it).",
 "mode": "live_studio",
 "ok": false,
 "reason": "not_playing"
}
```

Studio then is editing the same room, with the person's unsaved Sign still there. No file of the project changed
(every hash compared), and nothing was proposed.

## Limitations

- **Four actions, each a bounded run of key presses.** No pathfinding: the AI steers by `nearby` and the positions
  each action returns. No other keys (attack, menus, inventory) and no mouse.
- **Inputs are frames, not distances:** how far a move goes depends on the player's speed and what is in the way. The
  action reports where the player ended up.
- **Studio play-tests only:** a game running on its own has no session to ask.
- **Keys the person holds:** the AI won't press a key the person is holding. If the person presses one while the AI
  holds it, the AI's release lets it go too.
- **One action at a time:** no queue of actions.
