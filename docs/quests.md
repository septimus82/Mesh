# Quest & Journal System

Mesh keeps storyline data in `assets/data/quests.json` and renders progress through the in-game Quest Log overlay. Each quest entry describes a list of ordered stages, optional triggers, and any rewards that should be applied once everything finishes.

## Quest data file

```json
{
  "quests": [
    {
      "id": "field_supplies",
      "title": "Field Supplies",
      "description": "Help the warden restock the outpost.",
      "auto_start": false,
      "stages": [ ... ],
      "reward": { ... }
    }
  ]
}
```

Top-level keys:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | Unique identifier referenced by behaviours/UI. |
| `title` | string | Quest name shown in the Quest Log overlay. |
| `description` | string | Fallback text when no stage is active yet. |
| `auto_start` | bool | When true, the first stage activates on load without requiring a trigger. |
| `stages` | array | Ordered list of dictionaries (see below). |
| `reward` | object | Optional payload applied when the quest completes. |

### Stage definitions

Each stage object accepts:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | Stable identifier used when behaviours want to jump to a specific stage. |
| `title` | string | Short heading rendered underneath the quest title. |
| `text` | string | Objective text displayed inside the log. Falls back to `description`/`log_text`. |
| `start_on_event` | string or object | Optional trigger that must fire before this stage activates. |
| `complete_on` | string or object | Optional trigger that must fire before the stage is marked done. |

Trigger objects share the following shape:

```json
"complete_on": {
  "type": "dialogue_choice",
  "payload_field": "choice_id",
  "payload_value": "warden_turnin",
  "payload": { "entity": "FieldWarden" }
}
```

- `type` (required) is matched against `MeshEvent.type`.
- `payload_field` + `payload_value` enforce a single equality check.
- `payload` lets you provide multiple fixed key/value matches.
- Any additional keys on the object are merged into the payload filter.

When the trigger is just a string (e.g., `"collectible_picked"`), the quest listens for that event name without payload constraints.

### Rewards & runtime state

`reward.set_flags` flips entries inside `GameWindow.game_state.flags` and `reward.inc_counters` increments numeric counters. Helper events fire during quest progression so other behaviours can listen without coupling to the quest JSON:

- `quest_stage_started` (`quest_id`, `stage_id`, `quest_title`, `stage_title`)
- `quest_stage_completed` (same payload)
- `quest_completed` (`quest_id`, `quest_title`)

Pair these with `SetGameStateOnEvent`, `ConditionalActivator`, or custom behaviours to react when objectives begin/finish.

## QuestManager runtime helpers

`GameWindow.quest_manager` exposes a few utility methods for scripts and behaviours:

| Method | Description |
| --- | --- |
| `start_quest(quest_id, stage_id=None)` | Force the quest (or a specific stage) to become active immediately. |
| `set_stage(quest_id, stage_id)` | Skip straight to a stage, marking preceding stages as completed. |
| `complete_stage(quest_id, stage_id=None)` | Mark the active (or provided) stage as finished. |
| `complete_quest(quest_id)` | Finish the quest and apply its rewards. |
| `is_quest_active(quest_id)` / `is_quest_completed(quest_id)` | Quick state checks for gating UI or content. |
| `is_stage_completed(quest_id, stage_id)` | Returns True if the named stage is already logged as done. |
| `get_current_stage(quest_id)` / `get_pending_stage(quest_id)` | Returns the active or waiting stage dictionaries (or `None`). |
| `get_state_snapshot(quest_id=None)` | Returns a copy of the quest state (single quest or the entire map) for debugging and UI overlays. |

These helpers all normalize their inputs and fall back to `False`/`None` when the quest ID is unknown, so calling code can stay compact.

## Quest Log overlay & input

Press the `show_quests` action (bound to `Q` by default) to toggle the Quest Log. The panel renders every known quest, its active stage text, and a completion counter in the `X/Y objectives complete` format. Dialogue boxes automatically block the log to keep input focus predictable, and the overlay itself blocks player input while visible.

Use the companion `show_inventory` action (`TAB` by default) to open the Inventory overlay whenever you need to confirm quest rewards or pickup grants. It mirrors `game_state.values.inventory` using the centralized `assets/data/items.json` definitions so designers can sanity check reward tuning without leaving the scene.

## Demo quest: Field Supplies

`scenes/door_field.json` + `assets/data/quests.json` ship with a minimal quest that exercises the entire pipeline:

1. Talk to `FieldWarden` and accept the errand. The dialogue emits a `dialogue_choice` event that unlocks the first stage.
2. `QuestHookStageStart` listens for `quest_stage_started` and flips the `field_supplies_active` flag so the crate appears.
3. Grab `SupplyCrate`. The `collectible_picked` event completes the first stage and `QuestHookCrateReady` updates the `field_supplies_has_crate` flag.
4. Turn the crate in through the dialogue. The final choice fires `quest_stage_completed`, `quest_completed`, and rewards configured under `reward`.

The Quest Log updates automatically throughout the flow, and the reward payload showcases how quests can set flags and increment counters without authoring new behaviours.
