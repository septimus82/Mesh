# Runtime debugger (D1): an AI looks at a running play-test

When Mesh Studio play-tests a game, the real game runs in Studio's window. With three MCP tools, an AI connected to
the project can see what that game is doing. It can tell which room is running, where the player is, which flags,
counters and quests are set, which events just happened, and which errors the engine caught. It can also start and
stop a play-test, but only after the person allows it.

Everything comes from the running game's own objects, never from the project files or a simulation of them. What the
person is writing in Studio is reported separately and is never mixed with what the game is doing.

| Tool | What it does |
| --- | --- |
| `debug_runtime_snapshot(events=20, root=".")` | Reads the running game. `status` is `"playing"` or `"not_playing"`. Needs no permission and changes nothing. |
| `debug_start_playtest(root=".")` | Starts a play-test, as Studio's **Play (F4)** does. Needs the person's permission. |
| `debug_stop_playtest(root=".")` | Stops it, as **Stop** does, and returns to editing. Needs the same permission. |

The code is in `engine/runtime_debug.py`. Studio's side is `StudioAIHost.debug_*` in `engine/studio_ai.py` and
`Studio.ai_start_playtest` / `ai_stop_playtest` in `engine/studio.py`.

## How a request reaches the game

The tools use the same verified live session as `propose_changes`: the project's `.mesh/live_session.json` record,
which is checked against the editor's own `/health` answer. They talk to the same authenticated loopback bridge
(`127.0.0.1`, bearer token) and use its main-thread queue. D1 adds three endpoints to that bridge
(`GET /live/debug/snapshot`, `POST /live/debug/play`, `POST /live/debug/stop`). It adds no second server and no
network listener.

The bridge's HTTP threads never touch the game. They queue the request. Studio runs it at the start of its next
frame, in `Studio.on_update` on the main thread, between two frames of the game, and the answer goes back. A read
therefore sees a consistent frame, and it never draws or advances one.

When there is no Studio to ask, the tools refuse the same way the other Studio tools do:

| `reason` | When |
| --- | --- |
| `studio_not_open` | No Mesh Studio has the project open. That includes one that has closed, because closing removes its record. |
| `studio_session_uncertain` | A session record exists but can't be trusted. `problem` says why: `unverified_live_session` (no answer, or a record left behind by a crash), `session_mismatch`, `workspace_mismatch`, `invalid_live_session` or `unreadable_live_session`. |
| `timeout` | Studio's main thread didn't take the request within 5 s, for example because Studio is frozen. |
| `studio_unreachable` | The bridge answered with an HTTP error. A request without the session's token gets 401. |

## What a snapshot says

| Part | From the running game |
| --- | --- |
| `scene` | `path` (relative to the project) and `room` (`key`, `label`) of the room that is running. `room` is `null` for a scene that isn't one of the project's rooms. |
| `player` | `id`, `name` and `tag`, and `x`, `y` in pixels: the actual sprite, found the way the game finds its player. |
| `game_state` | `flags`, `counters`, `values` (the game's variables; `GameState` keeps `values` and `variables` as one mapping), `chapter` and `playtime_seconds`. |
| `quests` | Each defined quest (`defined`; the first 100 are `listed`): `status`, `current_stage`, `awaiting_stage`, `completed_stages` (the first 50) with `completed_stages_total` (all of them), `total_stages` and `auto_start`. These come from the quest records the game keeps. A quest the game hasn't touched reads `inactive`, which is what the quest manager would create. Reading never creates the record. |
| `events` | This play-test's events, oldest first: `seq`, `type`, `entity`, `scene`, `time` and `payload`. `seq` numbers every event the game has emitted, in order. `made_this_playtest`, `no_longer_kept` (the game keeps its last 50) and `last_seq` let you see what happened between two snapshots. `events` (0–50) caps how many are listed. |
| `diagnostics` | Errors the engine caught and carried on from since the play-test started, newest first: `site`, `count` and `last_seen`. They come from `engine/swallowed_exceptions`, which every catch site counts. The log has the details. |
| `studio` | What Studio has open, not what the game is doing: `mode` (`editing` or `playing`), `edited_room`, `unsaved_changes`, `revision` and `ai_playtest_control`. Play-testing never changes it. |
| `playtest` | `id`, `number`, `started_at`, `started_by` (`person` or `ai`) and `stopped_at`. |
| `sequence`, `time` | The snapshot's own number (each read is counted) and when it was taken. |

- **Missing systems:** a part the game doesn't have reads `{"available": false, "reason": "..."}`, for example
  `"the running room has no player"`. It never reads as an empty success.
- **Plain JSON only:** values are bounded in depth (4), text (200 characters) and entries (100 per list or object,
  200 flags or counters). A list or object cut short ends with `"... N more"`. An object in an event, such as a
  sprite, is named by its entity (`"actor": "Player"`) and never written out.
- **200 KB at most, enforced** (`BYTES_MAX`, measured as the bridge sends it, truncation details included).
  - **When a snapshot is bigger:** parts are left out in a fixed order until it fits:
    1. event payloads;
    2. `game_state.values`;
    3. quests' completed stages;
    4. diagnostics;
    5. the oldest events, down to the newest 10;
    6. the quest list;
    7. flags;
    8. counters;
    9. the last events, oldest first.
  - **What a left-out part reads:** each becomes `{"omitted": "size_limit", "count": N}`, with the part's real total.
    It never becomes an empty value, so "left out" can't be mistaken for "there is none"; an empty part stays empty.
    `truncated` lists the parts left out, and `events.items_left_out` counts the events left out.
  - **The events that stay** are always the newest, in order.
  - **If even that can't fit,** the answer is a refusal, `{"ok": false, "reason": "snapshot_too_large",
    "limit_bytes": ...}`, never a bigger snapshot. The same snapshot is always cut the same way.
- **No filesystem paths:** an absolute path inside any text (a value, an event payload, an object key, at any
  depth) is never passed on.
  - **Which paths:** Windows drive and UNC paths (spaces included), POSIX paths of two or more parts, and `file://`
    URLs.
  - **Inside the project:** the path becomes project-relative (`packs/core_regions/scenes/start.json`).
  - **Anywhere else:** it becomes `<path>/` and its file name (`<path>/save1.json`).
  - **Left as they are:** dialogue, entity ids, flags, relative paths, web URLs, `and/or`, `3/5` and `/help`.
- **No secrets:** the bridge's token and file contents never appear in a snapshot.

**Reading changes nothing.** It advances no frame and takes no event off the game's queue. It creates nothing (not
even a quest record), saves nothing, and leaves Studio's selection and mode alone. The tests compare the whole game
state, the event history and queue, the player, Studio's selection, mode and revision before and after a read.

## Starting and stopping: the person decides

Control is **off** until the person turns it on in Studio. They open **AI** in the top bar and click **Let an AI
start and stop play-tests: Off** to turn it On. It lasts only for that Studio session: a new Studio starts with it
off. While it is on, the play-test's own bar shows **AI may stop this**; clicking that turns it off again.

- **Start** refuses with `playtest_control_off` until the person allows it. It refuses with `studio_busy` while the
  person is in the middle of something:
  - answering a question (for example, unsaved changes when closing);
  - typing in a box and not finished (the text is neither committed for them nor lost);
  - dragging, painting or sculpting.
- **Start never saves.** It installs the open documents (unsaved edits included) into the game, exactly as Play
  (F4) does. The window title says *started by an AI*.
- **Repeats are stable:** Start while playing returns `already_playing` with the same play-test. Stop while editing
  returns `not_playing` with the last play-test.
- **Stop** goes back through Studio's own Stop. It returns to the edited rooms as they were, and nothing from the
  play-test is saved into them.
- **No other control:** neither tool can change the project. Proposals still wait for the person, and Accept is
  still theirs alone (F1, F6).

## A debugging session, as it ran

`tooling/d1_debug_scenario.py` builds a disposable project:

- Mesh's starter room, with its Guide. The Guide asks the player to light the cellar lantern, and the choice "I'll
  light it." sets the flag `agreed_to_help`.
- A Cellar, reached through a door north of the player.
- A quest, *Light the cellar lantern* (`auto_start`), whose first stage needs that flag.

The scenario opens the project in Mesh Studio in a hidden window, with the live session on as it is for a person.
Every MCP call below is the real tool function, called on another thread as the MCP server would call it, while the
window keeps running. The responses below are verbatim from a run on the engine as it is now, after #446
(`docs/reviews/d1_runtime_debugger_transcript_after_446.json`). D1's own run, before #446, is kept as evidence in
`docs/reviews/d1_runtime_debugger_transcript.json`; see [What the scenario found](#what-the-scenario-found).
`tests/test_runtime_debugger_gpu.py` runs the same scenario in the GPU lane.

**1. Studio is editing.** Nothing is running, so the snapshot says so. The person then adds a Sign and doesn't save.

`debug_runtime_snapshot {}`

```json
{
 "last_playtest": null,
 "message": "Mesh Studio is editing, not play-testing: no game is running to inspect. debug_start_playtest starts one (if the person allowed it), or ask the person to press Play (F4).",
 "mode": "live_studio",
 "ok": true,
 "sequence": 1,
 "status": "not_playing",
 "studio": {
  "ai_playtest_control": false,
  "edited_room": "start",
  "mode": "editing",
  "revision": 0,
  "unsaved_changes": false
 },
 "time": 1793615047.599
}
```

**2. The AI asks to play.** The person hasn't allowed it:

`debug_start_playtest {}`

```json
{
 "message": "Mesh Studio hasn't allowed an AI to start play-tests, so nothing was done. The person can allow it in Studio (top bar: AI, then \"Let an AI start and stop play-tests\"), for this session; or ask them to press Play (F4) or Stop. debug_runtime_snapshot needs no permission.",
 "mode": "live_studio",
 "ok": false,
 "reason": "playtest_control_off"
}
```

**3. The person allows it, but is typing.** They turn it on in the AI panel, then start renaming the Guide and stop
before Enter. The request is refused and the box keeps "Guide the Elder". The person then finishes without
changing anything.

`debug_start_playtest {}`

```json
{
 "message": "The person is typing in a box and hasn't finished. Nothing was started; try again once the person has finished.",
 "ok": false,
 "reason": "studio_busy"
}
```

**4. Play starts.** A second request finds the same play-test:

`debug_start_playtest {}`

```json
{
 "ok": true,
 "playtest": {
  "id": "b4bfc0d8cdf5",
  "number": 1,
  "started_at": 1793615048.966,
  "started_by": "ai",
  "stopped_at": null
 },
 "room": "start",
 "status": "playing"
}
```

`debug_start_playtest {}`

```json
{
 "ok": true,
 "playtest": {
  "id": "b4bfc0d8cdf5",
  "number": 1,
  "started_at": 1793615048.966,
  "started_by": "ai",
  "stopped_at": null
 },
 "status": "already_playing"
}
```

The running game's room and player. The quest started with the play-test: it is `active` in stage `agree`, and its
`quest_stage_started` event is the only one so far. `hint_shown_quest_log` is the game's own flag: the HUD sets it
when it shows "Press Q to open Quest Log" for an active quest. `studio.unsaved_changes` is the person's Sign: it
belongs to Studio's document, not to the game.

`debug_runtime_snapshot {}`

```json
{
 "diagnostics": {
  "available": true,
  "items": [],
  "note": "Errors the engine caught and carried on from (each place that catches one counts it), since the play-test started; the log has their details.",
  "sites": 0
 },
 "events": {
  "available": true,
  "items": [
   {
    "entity": null,
    "payload": {
     "quest_id": "light_the_lantern",
     "quest_title": "Light the cellar lantern",
     "source": "auto",
     "stage_id": "agree",
     "stage_title": "Talk to the Guide",
     "text": "Talk to the Guide"
    },
    "scene": null,
    "seq": 2,
    "time": 1793615048.966,
    "type": "quest_stage_started"
   }
  ],
  "last_seq": 2,
  "limit": 20,
  "made_this_playtest": 1,
  "no_longer_kept": 0
 },
 "game_state": {
  "available": true,
  "chapter": 1,
  "counters": {},
  "flags": {
   "hint_shown_quest_log": true
  },
  "playtime_seconds": 0.567,
  "values": {
   "hud_last_quest_progress": {
    "light_the_lantern": {
     "completed": false,
     "stage_id": "agree"
    }
   },
   "time_of_day_hours": 21.0
  }
 },
 "mode": "live_studio",
 "ok": true,
 "player": {
  "available": true,
  "id": "start_player_128_128_0_0",
  "name": "Player",
  "tag": "player",
  "units": "pixels",
  "x": 128.0,
  "y": 128.0
 },
 "playtest": {
  "id": "b4bfc0d8cdf5",
  "number": 1,
  "started_at": 1793615048.966,
  "started_by": "ai",
  "stopped_at": null
 },
 "quests": {
  "available": true,
  "defined": 1,
  "listed": 1,
  "quests": [
   {
    "auto_start": true,
    "awaiting_stage": null,
    "completed_stages": [],
    "completed_stages_total": 0,
    "current_stage": "agree",
    "id": "light_the_lantern",
    "status": "active",
    "title": "Light the cellar lantern",
    "total_stages": 2
   }
  ]
 },
 "scene": {
  "available": true,
  "path": "packs/core_regions/scenes/start.json",
  "room": {
   "key": "start",
   "label": "Start"
  }
 },
 "sequence": 2,
 "status": "playing",
 "studio": {
  "ai_playtest_control": true,
  "edited_room": "start",
  "mode": "playing",
  "revision": 1,
  "unsaved_changes": true
 },
 "time": 1793615050.334
}
```

**5–6. The player talks to the Guide.** The scenario drives the game's own keys: the arrow keys to walk up, E to
talk, Down and E to choose "I'll light it." The next snapshot shows the flag and the events that set it, in order:

`debug_runtime_snapshot {"events": 12}`

```json
{
 "diagnostics": {
  "available": true,
  "items": [],
  "note": "Errors the engine caught and carried on from (each place that catches one counts it), since the play-test started; the log has their details.",
  "sites": 0
 },
 "events": {
  "available": true,
  "items": [
   {
    "entity": null,
    "payload": {
     "quest_id": "light_the_lantern",
     "quest_title": "Light the cellar lantern",
     "source": "auto",
     "stage_id": "agree",
     "stage_title": "Talk to the Guide",
     "text": "Talk to the Guide"
    },
    "scene": null,
    "seq": 2,
    "time": 1793615048.966,
    "type": "quest_stage_started"
   },
   {
    "entity": "Guide",
    "payload": {
     "actor": "Player",
     "entity": "Guide",
     "owner": "dialogue::Guide",
     "trigger": "interact"
    },
    "scene": null,
    "seq": 3,
    "time": 1793615050.998,
    "type": "dialogue_started"
   },
   {
    "entity": "Guide",
    "payload": {
     "actor": "Player",
     "entity": "Guide",
     "has_choices": true,
     "node": "root",
     "owner": "dialogue::Guide",
     "speaker": "Guide",
     "stage": "start",
     "text": "The cellar lantern has gone out. Will you light it?"
    },
    "scene": null,
    "seq": 4,
    "time": 1793615050.998,
    "type": "dialogue_line"
   },
   {
    "entity": "Guide",
    "payload": {
     "actor": "Player",
     "choice_id": "help",
     "choice_text": "I'll light it.",
     "entity": "Guide",
     "next": "thanks",
     "node": "root",
     "owner": "dialogue::Guide"
    },
    "scene": null,
    "seq": 5,
    "time": 1793615051.158,
    "type": "dialogue_choice"
   },
   {
    "entity": "Guide",
    "payload": {
     "actor": "Player",
     "entity": "Guide",
     "has_choices": false,
     "node": "thanks",
     "owner": "dialogue::Guide",
     "speaker": "Guide",
     "stage": "choice",
     "text": "Thank you! The cellar door is just north of here."
    },
    "scene": null,
    "seq": 6,
    "time": 1793615051.158,
    "type": "dialogue_line"
   },
   {
    "entity": null,
    "payload": {
     "quest_id": "light_the_lantern",
     "quest_title": "Light the cellar lantern",
     "source": "requirements",
     "stage_id": "agree",
     "stage_title": "Talk to the Guide",
     "text": "Talk to the Guide"
    },
    "scene": null,
    "seq": 7,
    "time": 1793615051.158,
    "type": "quest_stage_completed"
   },
   {
    "entity": null,
    "payload": {
     "quest_id": "light_the_lantern",
     "quest_title": "Light the cellar lantern",
     "source": "auto",
     "stage_id": "cellar",
     "stage_title": "Go down to the cellar",
     "text": "Go down to the cellar"
    },
    "scene": null,
    "seq": 8,
    "time": 1793615051.158,
    "type": "quest_stage_started"
   },
   {
    "entity": "Guide",
    "payload": {
     "actor": "Player",
     "entity": "Guide",
     "owner": "dialogue::Guide",
     "reason": "advance_complete"
    },
    "scene": null,
    "seq": 9,
    "time": 1793615051.238,
    "type": "dialogue_finished"
   }
  ],
  "last_seq": 9,
  "limit": 12,
  "made_this_playtest": 8,
  "no_longer_kept": 0
 },
 "game_state": {
  "available": true,
  "chapter": 1,
  "counters": {},
  "flags": {
   "agreed_to_help": true,
   "hint_shown_quest_log": true
  },
  "playtime_seconds": 2.133,
  "values": {
   "hud_last_quest_progress": {
    "light_the_lantern": {
     "completed": false,
     "stage_id": "cellar"
    }
   },
   "monster_egg_walk_accumulator": 1.0,
   "time_of_day_hours": 21.0
  }
 },
 "mode": "live_studio",
 "ok": true,
 "player": {
  "available": true,
  "id": "start_player_128_128_0_0",
  "name": "Player",
  "tag": "player",
  "units": "pixels",
  "x": 273.0,
  "y": 128.0
 },
 "playtest": {
  "id": "b4bfc0d8cdf5",
  "number": 1,
  "started_at": 1793615048.966,
  "started_by": "ai",
  "stopped_at": null
 },
 "quests": {
  "available": true,
  "defined": 1,
  "listed": 1,
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
 },
 "scene": {
  "available": true,
  "path": "packs/core_regions/scenes/start.json",
  "room": {
   "key": "start",
   "label": "Start"
  }
 },
 "sequence": 4,
 "status": "playing",
 "studio": {
  "ai_playtest_control": true,
  "edited_room": "start",
  "mode": "playing",
  "revision": 1,
  "unsaved_changes": true
 },
 "time": 1793615051.407
}
```

**What the AI can conclude from this:**

- `agreed_to_help` is set, and `dialogue_choice` (`choice_id: "help"`) is what set it.
- The quest's `agree` stage completed (`quest_stage_completed`) right after the choice, and the quest moved on to
  `cellar` (`quest_stage_started`).
- The quest record agrees: `completed_stages: ["agree"]`, `current_stage: "cellar"`.

**7. The player walks through the door.** The snapshot follows the running game into the Cellar. The latest event
is the `scene_transition` that took it there, and `studio.edited_room` is still the room the person is editing.

`debug_runtime_snapshot {"events": 6}`

```json
{
 "diagnostics": {
  "available": true,
  "items": [],
  "note": "Errors the engine caught and carried on from (each place that catches one counts it), since the play-test started; the log has their details.",
  "sites": 0
 },
 "events": {
  "available": true,
  "items": [
   {
    "entity": "Guide",
    "payload": {
     "actor": "Player",
     "choice_id": "help",
     "choice_text": "I'll light it.",
     "entity": "Guide",
     "next": "thanks",
     "node": "root",
     "owner": "dialogue::Guide"
    },
    "scene": null,
    "seq": 5,
    "time": 1793615051.158,
    "type": "dialogue_choice"
   },
   {
    "entity": "Guide",
    "payload": {
     "actor": "Player",
     "entity": "Guide",
     "has_choices": false,
     "node": "thanks",
     "owner": "dialogue::Guide",
     "speaker": "Guide",
     "stage": "choice",
     "text": "Thank you! The cellar door is just north of here."
    },
    "scene": null,
    "seq": 6,
    "time": 1793615051.158,
    "type": "dialogue_line"
   },
   {
    "entity": null,
    "payload": {
     "quest_id": "light_the_lantern",
     "quest_title": "Light the cellar lantern",
     "source": "requirements",
     "stage_id": "agree",
     "stage_title": "Talk to the Guide",
     "text": "Talk to the Guide"
    },
    "scene": null,
    "seq": 7,
    "time": 1793615051.158,
    "type": "quest_stage_completed"
   },
   {
    "entity": null,
    "payload": {
     "quest_id": "light_the_lantern",
     "quest_title": "Light the cellar lantern",
     "source": "auto",
     "stage_id": "cellar",
     "stage_title": "Go down to the cellar",
     "text": "Go down to the cellar"
    },
    "scene": null,
    "seq": 8,
    "time": 1793615051.158,
    "type": "quest_stage_started"
   },
   {
    "entity": "Guide",
    "payload": {
     "actor": "Player",
     "entity": "Guide",
     "owner": "dialogue::Guide",
     "reason": "advance_complete"
    },
    "scene": null,
    "seq": 9,
    "time": 1793615051.238,
    "type": "dialogue_finished"
   },
   {
    "entity": "Door to Cellar",
    "payload": {
     "actor": "Player",
     "entity": "Door to Cellar",
     "reason": "collision",
     "spawn_id": "from_start",
     "target_scene": "cellar"
    },
    "scene": null,
    "seq": 10,
    "time": 1793615051.48,
    "type": "scene_transition"
   }
  ],
  "last_seq": 10,
  "limit": 6,
  "made_this_playtest": 9,
  "no_longer_kept": 0
 },
 "game_state": {
  "available": true,
  "chapter": 1,
  "counters": {},
  "flags": {
   "agreed_to_help": true,
   "hint_shown_quest_log": true
  },
  "playtime_seconds": 2.65,
  "values": {
   "hud_last_quest_progress": {
    "light_the_lantern": {
     "completed": false,
     "stage_id": "cellar"
    }
   },
   "monster_egg_walk_accumulator": 16.0,
   "time_of_day_hours": 21.0
  }
 },
 "mode": "live_studio",
 "ok": true,
 "player": {
  "available": true,
  "id": "cellar_player_128_128_0_0",
  "name": "Player",
  "tag": "player",
  "units": "pixels",
  "x": 256.0,
  "y": 128.0
 },
 "playtest": {
  "id": "b4bfc0d8cdf5",
  "number": 1,
  "started_at": 1793615048.966,
  "started_by": "ai",
  "stopped_at": null
 },
 "quests": {
  "available": true,
  "defined": 1,
  "listed": 1,
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
 },
 "scene": {
  "available": true,
  "path": "packs/core_regions/scenes/cellar.json",
  "room": {
   "key": "cellar",
   "label": "Cellar"
  }
 },
 "sequence": 5,
 "status": "playing",
 "studio": {
  "ai_playtest_control": true,
  "edited_room": "start",
  "mode": "playing",
  "revision": 1,
  "unsaved_changes": true
 },
 "time": 1793615051.711
}
```

**8. Stop, and Stop again.**

`debug_stop_playtest {}`

```json
{
 "editing": {
  "revision": 1,
  "room": "start",
  "unsaved_changes": true
 },
 "ok": true,
 "playtest": {
  "id": "b4bfc0d8cdf5",
  "number": 1,
  "started_at": 1793615048.966,
  "started_by": "ai",
  "stopped_at": 1793615051.729
 },
 "status": "stopped"
}
```

`debug_stop_playtest {}`

```json
{
 "last_playtest": {
  "id": "b4bfc0d8cdf5",
  "number": 1,
  "started_at": 1793615048.966,
  "started_by": "ai",
  "stopped_at": 1793615051.729
 },
 "ok": true,
 "status": "not_playing"
}
```

`debug_runtime_snapshot {}`

```json
{
 "last_playtest": {
  "id": "b4bfc0d8cdf5",
  "number": 1,
  "started_at": 1793615048.966,
  "started_by": "ai",
  "stopped_at": 1793615051.729
 },
 "message": "Mesh Studio is editing, not play-testing: no game is running to inspect. debug_start_playtest starts one (if the person allowed it), or ask the person to press Play (F4).",
 "mode": "live_studio",
 "ok": true,
 "sequence": 6,
 "status": "not_playing",
 "studio": {
  "ai_playtest_control": true,
  "edited_room": "start",
  "mode": "editing",
  "revision": 1,
  "unsaved_changes": true
 },
 "time": 1793615052.016
}
```

**9. Back to editing.** Studio is in the same room, with the Sign still unsaved, and no file of the project changed
(the scenario compares every file's hash). Once Studio closes, there is no session to ask:

`debug_runtime_snapshot {}`

```json
{
 "message": "Mesh Studio doesn't have this project open.",
 "ok": false,
 "reason": "studio_not_open"
}
```

## What the scenario found

**History: D1's first run found an engine bug, fixed in #446.** The walkthrough above is the corrected behaviour.

In D1's own run (before #446), the snapshot after the conversation showed the flag set and the quest never started:

```json
{
 "game_state": {
  "flags": {
   "agreed_to_help": true
  }
 },
 "quests": {
  "available": true,
  "defined": 1,
  "listed": 1,
  "quests": [
   {
    "auto_start": true,
    "awaiting_stage": null,
    "completed_stages": [],
    "completed_stages_total": 0,
    "current_stage": null,
    "id": "light_the_lantern",
    "status": "inactive",
    "title": "Light the cellar lantern",
    "total_stages": 2
   }
  ]
 }
}
```

That report was accurate. It was a real engine bug:

- **The cause (then):** a play-test starts from `GameStateController.replace_state({})`, a fresh `GameState`. That
  didn't re-sync the quest manager: `import_state` calls `load_from_dict` (and so `reload_from_state`) only when the
  data has a `quests` block. So an `auto_start` quest never started, no stage was awaiting, and a flag its stage
  needed moved nothing.
- **Shown directly** in a plain game window (no Studio):
  - At launch, the quest was `active` in stage `agree`, and setting the flag completed `agree`.
  - After `replace_state({})`, it was `inactive` and stayed that way when the flag was set again.
- **Who it affected:** Studio's Play and Stop, and `behaviours/main_menu.py`'s New Game. The main-menu overlay's New
  Game already re-synced quests itself, and loading a save was unaffected.
- **The fix (#446):** `replace_state` now runs `reload_from_state` after importing the new state, for every caller
  (the overlay's own re-sync went with it).
  - The GPU scenario checks that the quest starts with the play-test and moves from `agree` to `cellar` on the flag.
  - It also checks that the debugger's report matches the running game's quest record.

## Limitations

- **Studio play-tests only:** a game launched on its own (`main.py`, an export) has no live session to ask.
- **Events from one bus:** they come from the game's `MeshEventBus` history, the bus Studio's game runs on
  (`window.event_bus`, 50 kept).
  - `GameplayEventBus` (`engine/gameplay_event_bus.py`) isn't attached to the game window, so there is nothing of
    its to read.
  - An event's `scene` is whatever its payload names, often `null`.
- **Errors are counts, not messages:** diagnostics count the errors the engine caught, by catch site. The messages
  and tracebacks are in the log, which D1 doesn't read. Errors that end the game aren't caught, so they aren't
  listed.
- **Pixels, not metres:** the player's position is the sprite's centre in pixels. An HD-2D room reports the same 2D
  ground position.
- **Watching means polling:** a snapshot is one moment. To follow a change, compare `events.last_seq` and
  `sequence` between snapshots. There is no subscription.
- **Path hiding works on text patterns:** it can't recognise a path written without a leading drive, `\\` or `/`,
  such as a bare `Users\ann\x`. It errs on the side of hiding: in text that also contains a later `/`, a Windows
  path's match can run on to it and hide the words between.
- **Reading only:** no breakpoints, stepping or time travel, no changing state, and no keyboard or mouse input
  through MCP.

## Running it

```text
py -3.13 tooling/d1_debug_scenario.py OUT           # transcript.json and report.json in OUT (--keep keeps the project)
py -m pytest tests/test_runtime_debug.py            # headless: projection, bounds, permission, refusals
MESH_GL_SMOKE=1 py -m pytest tests/test_runtime_debugger_gpu.py   # the scenario in a real window (GPU lane)
```
