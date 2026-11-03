# Interaction debugger (D3A): why can't the player use this?

`debug_interaction(entity_id)` explains whether the player can use one object in the game running in a Mesh Studio
play-test, and why not. It reads the running game, through the engine's own interaction rules, and the project as
written. It is read-only: no frame advances, no key is pressed, and nothing is set, saved or proposed. It needs no
permission, like `debug_runtime_snapshot`.

The code is in `engine/runtime_diagnose.py`. It is reached through `StudioAIHost.debug_interaction` and the bridge's
`GET /live/debug/interaction?entity=...`, on the same authenticated loopback bridge, main-thread queue, timeout and
refusals as the D1 tools.

## What it reports

| Field | Meaning |
| --- | --- |
| `how` | `interact` (the interact key) or `touch` (a door with `trigger_on_touch`: walk into it). |
| `available` | Whether the player can use it **now** that way. For a touch door: the player is in its doorway now (the next frame takes them through); `touch.on_contact` says whether walking into it would. |
| `blocking` | The first condition that fails: `code` and `message`. |
| `observed` | Every condition checked, in the engine's order: `code`, `ok` (`true` met, `false` fails, `null` not analysed), `message`, and `detail` with the actual values. |
| `flags` | The current value of every flag involved. |
| `flag_sources` | Where the project sets each of those flags, from what is `searched`: dialogue choices' `set_flags` / `clear_flags` and `SetGameStateOnEvent` in every room, and quest rewards. |
| `dialogue` | For a conversation: `conversation_open`, the node showing (`current_node`), and each choice with `conditions_met` (its flags and `once`, as `Dialogue` checks them) apart from `selectable_now` (also needs its node showing in the open conversation, as the game requires to take it), and the flags it needs. |
| `touch` | For a touch door: its rules, including `shown` (a door hidden by "Show when" isn't set off by walking into it), `triggered_by` (only something tagged its `target_tag` sets it off, `player` unless authored otherwise) and `overlapping` (the player is in its doorway now), and `on_contact` (every rule but overlapping is met: walking into it would use it). |
| `not_analysed` | Behaviours that take an interaction by a rule of their own, not explained. |
| `possible_causes` | Hypotheses, kept apart from what was observed. |

## Conditions, in the order the engine checks them (`engine/interaction.py`)

| `code` | Fails when |
| --- | --- |
| `in_room` | It isn't in the running room. The reason is reported from facts: no such object in the project; it's in another room; it was collected or defeated earlier (room memory); or its `require_flags` / `forbid_flags` kept it out when the room loaded. If its flags are met now, the cause given is a *possible* one: the room loaded before they were met, and a room doesn't add an object later. |
| `flag_gate` | Its own `require_flags` / `forbid_flags` aren't met (`scene_entity_gating`, checked again on use). |
| `shown` | It is hidden. "Show when" (`ConditionalActivator`) is explained flag by flag. |
| `behaviours` | No behaviour takes the interaction now. `SceneTransition` is explained rule by rule: `interact_allowed`, `has_target`, `not_used_up`, `flags`. `Dialogue` is too: `conversation_open`, `has_lines`, `flags`, `not_used_up`. Any other behaviour is `not_analysed`. |
| `distance` | The player is farther than its interaction radius (its `interact_radius`, a behaviour's, or 72 px). |
| `facing` | It is behind the player, and the player isn't touching it. |
| `selection` | Another object is chosen instead. Candidates are ranked by priority, then how directly the player faces them, then distance; `candidates` lists them in that order. This is the engine's own `select_interaction_candidate`, called as the game calls it. |

## A debugging session, as it ran

`tooling/d3a_interaction_scenario.py` uses D1's disposable project and adds three things:

- **A Cellar Door,** used with the interact key, kept out of the room by `require_flags: ["has_key"]`.
- **A Notice** just left of it.
- **Changes to the Guide:** her "I'll light it." also gives `has_key`, and a new choice, "Where is the cellar?",
  needs `agreed_to_help`.

The scenario opens the project in Mesh Studio in a hidden window. Each call is the real MCP tool, run on another
thread while Studio keeps running. The responses are verbatim from that run
(`docs/reviews/d3a_interaction_transcript.json`). `tests/test_interaction_debugger_gpu.py` runs the same scenario in
the GPU lane.

**Without the key,** the door isn't in the room. The response shows which flag keeps it out, its value, and where the
project sets it:

`debug_interaction {"entity_id": "cellar_door"}`

```json
{
 "available": false,
 "blocking": {
  "code": "in_room",
  "message": "It isn't in the running room: its flags keep it out (a room leaves out objects whose flags aren't met when it loads)."
 },
 "entity_id": "cellar_door",
 "flag_sources": {
  "has_key": [
   {
    "choice": "I'll light it.",
    "entity": "Guide",
    "entity_id": "start_guide_320_128_0_0",
    "node": "root",
    "room": "start",
    "room_label": "Start",
    "sets_to": true,
    "via": "dialogue choice"
   }
  ]
 },
 "flags": {
  "has_key": false
 },
 "how": "interact",
 "mode": "live_studio",
 "not_analysed": [],
 "observed": [
  {
   "code": "in_room",
   "detail": {
    "forbid_flags": [],
    "require_flags": [
     "has_key"
    ],
    "running_room": "start",
    "unmet": [
     "has_key"
    ],
    "values": {
     "has_key": false
    }
   },
   "message": "It isn't in the running room: its flags keep it out (a room leaves out objects whose flags aren't met when it loads).",
   "ok": false
  }
 ],
 "ok": true,
 "playtest": {
  "id": "1f58d246e664",
  "number": 1,
  "started_at": 1793654474.794,
  "started_by": "person",
  "stopped_at": null
 },
 "possible_causes": [],
 "searched": [
  "dialogue choices' set_flags / clear_flags (every room)",
  "SetGameStateOnEvent set_flags / clear_flags (every room)",
  "quest rewards' set_flags"
 ],
 "status": "playing"
}
```

**The Guide's conversation.** "Where is the cellar?" can't be picked yet:

`debug_interaction {"entity_id": "start_guide_320_128_0_0"}` (excerpt: `dialogue`, `flags`)

```json
{
 "dialogue": {
  "choices": [
   {
    "choice": "I'll light it.",
    "conditions_met": true,
    "id": "help",
    "node": "root",
    "selectable_now": false,
    "used_up": false
   },
   {
    "choice": "Not now.",
    "conditions_met": true,
    "id": "later",
    "node": "root",
    "selectable_now": false,
    "used_up": false
   },
   {
    "choice": "Where is the cellar?",
    "conditions_met": false,
    "forbid_flags": [],
    "id": "where",
    "node": "root",
    "require_flags": [
     "agreed_to_help"
    ],
    "selectable_now": false,
    "unmet": [
     "agreed_to_help"
    ],
    "used_up": false
   }
  ],
  "conversation_open": false,
  "current_node": null
 },
 "flags": {
  "agreed_to_help": false
 }
}
```

**After agreeing,** `has_key` is set, but the door is still not in the room. Why is given as a *possible* cause: the
room loaded before the flag was set.

`debug_interaction {"entity_id": "cellar_door"}` (excerpt: `available`, `blocking`, `flags`, `possible_causes`)

```json
{
 "available": false,
 "blocking": {
  "code": "in_room",
  "message": "It isn't in the running room, though its flags are met now."
 },
 "flags": {
  "has_key": true
 },
 "possible_causes": [
  {
   "code": "loaded_before_flags_were_met",
   "message": "The room may have loaded before its flags were met: a room leaves an object out when it loads, and doesn't add it later. It would appear when the room is next loaded."
  }
 ]
}
```

**Back in the room after a trip to the Cellar,** the door is there. From far away it is too far:

`debug_interaction {"entity_id": "cellar_door"}` (excerpt: `available`, `blocking` and the `distance` condition)

```json
{
 "available": false,
 "blocking": {
  "code": "distance",
  "message": "The player is too far: 360 px away, and it can be used within 72 px."
 },
 "observed": [
  {
   "code": "distance",
   "detail": {
    "distance": 360.0,
    "radius": 72.0
   },
   "message": "The player is too far: 360 px away, and it can be used within 72 px.",
   "ok": false
  }
 ]
}
```

**Left of the Notice, facing right,** the Notice is chosen instead. It is nearer, the same way:

`debug_interaction {"entity_id": "cellar_door"}` (excerpt: `available`, `blocking` and the `selection` condition)

```json
{
 "available": false,
 "blocking": {
  "code": "selection",
  "message": "Pressing interact now uses 'Notice' instead: candidates are ranked by priority, then how directly the player faces them, then distance."
 },
 "observed": [
  {
   "code": "selection",
   "detail": {
    "candidates": [
     {
      "distance": 20.0,
      "entity_id": "notice",
      "facing_alignment": 1.0,
      "name": "Notice",
      "priority": 0
     },
     {
      "distance": 60.0,
      "entity_id": "cellar_door",
      "facing_alignment": 1.0,
      "name": "Cellar Door",
      "priority": 0
     }
    ],
    "chosen": "notice",
    "this": "cellar_door"
   },
   "message": "Pressing interact now uses 'Notice' instead: candidates are ranked by priority, then how directly the player faces them, then distance.",
   "ok": false
  }
 ]
}
```

**Right of the door, facing left,** it is available. Pressing interact then took the player to the Cellar, as the
diagnosis said it would.

`debug_interaction {"entity_id": "cellar_door"}` (excerpt: `available`, `blocking`, `how` and the `selection` condition)

```json
{
 "available": true,
 "blocking": null,
 "how": "interact",
 "observed": [
  {
   "code": "selection",
   "detail": {
    "candidates": [
     {
      "distance": 40.0,
      "entity_id": "cellar_door",
      "facing_alignment": 1.0,
      "name": "Cellar Door",
      "priority": 0
     }
    ],
    "chosen": "cellar_door",
    "this": "cellar_door"
   },
   "message": "Pressing interact now uses it.",
   "ok": true
  }
 ]
}
```

Reading changed nothing: flags, counters, room, event count, the event queue and the player's position were the same
before and after.

## Limitations

- **Two behaviours are explained:** `SceneTransition` and `Dialogue`. Any other behaviour that takes an interaction
  (`Interactable`, `ToggleSwitch`, puzzle behaviours and so on) is reported `not_analysed`: whether it allows the
  interaction is reported, but not why.
- **Flag sources are what was `searched`.** A flag set any other way (another behaviour, a cutscene, a script, the
  console) isn't found. An empty list means "not found among these", not "nothing sets it".
- **Events are never used as proof.** The diagnosis never says something didn't happen because the bounded event
  history lacks it.
- **Interaction priority isn't authorable in scenes:** the schema rejects it on entities, and no behaviour sets it. In
  practice selection is decided by facing and distance.
- **A choice's `conditions_met` isn't "can be picked now".** Only `selectable_now` is: the game takes a choice only from
  the node showing in an open conversation. Which later node a conversation reaches isn't predicted.
- **One object at a time, during a play-test only.** While editing, the answer is `not_playing`, with the rooms the
  object is written in.
