# Golden Slice Variants (Developer Guide)

This doc standardizes how to add a new **Golden Slice** variant in a way that matches the repo's current content + test contracts.

## Quickstart Checklist

1) **World file**
- Add `worlds/golden_slice_variant_<letter>.json`
- Mirror an existing world (e.g. `worlds/golden_slice_variant_g.json`)
- Point `Ridge Outpost_dungeon` to your new scene file.

2) **Scene file**
- Add `packs/core_regions/scenes/Ridge Outpost_dungeon_variant_<letter>.json`
- Use existing behaviours only (e.g. `TriggerZone`, `SwitchInteract`, `DoorLock`).
- Zones must be unique entity names (exactly once).

3) **Quest entries**
- Edit `assets/data/quests.json` and add `ridge_variant_<letter>_*` quests.
- Ensure `start_toast` / `complete_toast` follow the naming rule below and are `<= 120` chars.
- Rewards: `inc_counters.gold` + exactly one `set_flags` entry (see rules below).
- If you use custom event types (e.g. a switch event), add it to `assets/data/events.json` so `validate-all` stays green.

4) **Preset**
- Edit `config.json` and add preset `golden_slice_variant_<letter>` targeting your world file.
- Mirror the existing `pipeline` steps (dry-run strict + demo).

5) **Register in contract suite**
- Edit `tests/_variant_contracts.py`:
  - Add a new entry to `GOLDEN_SLICE_VARIANT_CASES`
  - Set `kind` and fill required fields for your variant kind
- The main coverage lives in `tests/test_golden_slice_variants_contract.py`.

## Naming Conventions

### World / Preset
- World id: `golden_slice_variant_<letter>`
- World path: `worlds/golden_slice_variant_<letter>.json`
- Preset: `golden_slice_variant_<letter>`

### Scene
- Scene path: `packs/core_regions/scenes/Ridge Outpost_dungeon_variant_<letter>.json`

### Quests
- Quest ids: `ridge_variant_<letter>_<slug>`
- Flags: keep deterministic, per-variant (e.g. `ridge_variant_k_route_complete`)

### Zones (TriggerZone entity names)
- Prefer `Variant<Letter><Name>Zone`, e.g. `VariantGStartZone`, `VariantJChoiceAZone`.
- Each zone must exist **exactly once** in the scene file.

## Toast Convention (Enforced)

If a quest provides `start_toast` or `complete_toast`, it must:
- Be a non-empty string
- Be `<= 120` characters
- Match the format: `"<Prefix>: <message>"`
- For Golden Slice quests (`ridge_variant_*`), prefix must be one of:
  - `Beacon`, `Relay`, `Cache`, `Choice`, `Switch`, `Intro`

Examples:
```json
{
  "start_toast": "Cache: Secure the Cache",
  "complete_toast": "Cache: Complete"
}
```

## Reward Rules (Golden Slice)

Golden Slice quests should use the standardized reward shape:
```json
"reward": {
  "set_flags": { "<one_flag>": true },
  "inc_counters": { "gold": 25 }
}
```

Rules:
- **Exactly one** flag in `set_flags`
- `inc_counters` must include **exactly** `gold` (no extra counters) for the completion quest
- Use integers (tests compare numeric values deterministically)

## Gating Fields (Conditional Starts)

Quests can be conditionally startable via:
```json
"requires_flags": ["flag_a", "flag_b"],
"blocks_flags": ["flag_c"]
```

Semantics:
- `requires_flags`: quest may start only if **all** required flags are true
- `blocks_flags`: quest may start only if **none** of the blocked flags are true

## Variant Kinds (Templates)

### 1) `linear`
Single quest, zone -> zone.

Scene zones:
- `Variant<Letter>StartZone`
- `Variant<Letter>GoalZone`

Quest template:
```json
{
  "id": "ridge_variant_x_example",
  "title": "Example",
  "start_toast": "Cache: Secure the Cache",
  "complete_toast": "Cache: Complete",
  "stages": [
    {
      "id": "do_it",
      "title": "Do It",
      "start_on_event": { "type": "entered_zone", "payload": { "zone": "VariantXStartZone" } },
      "complete_on": { "type": "entered_zone", "payload": { "zone": "VariantXGoalZone" } }
    }
  ],
  "reward": { "set_flags": { "ridge_variant_x_example_complete": true }, "inc_counters": { "gold": 25 } }
}
```

Contract registration (`tests/_variant_contracts.py`):
- `kind="linear"` with `quest_id`, `start_zone`, `goal_zone`, `start_toast`, `complete_toast`, `gold`, `complete_flag`.

### 2) `branching_choice`
Two mutually exclusive quests gated by flags.

Common pattern:
- Intro quest sets an `intro_complete` flag when the player reaches the fork.
- Choice A and B each require `intro_complete` and block the other's completion flag.

Quest templates (sketch):
```json
{
  "id": "ridge_variant_j_intro",
  "start_toast": "Intro: Reach the Fork",
  "complete_toast": "Intro: Complete",
  "reward": { "set_flags": { "ridge_variant_j_intro_complete": true }, "inc_counters": {} }
}
```
```json
{
  "id": "ridge_variant_j_choice_a",
  "requires_flags": ["ridge_variant_j_intro_complete"],
  "blocks_flags": ["ridge_variant_j_choice_b_complete"],
  "start_toast": "Choice: Path A - Secure the Cache",
  "complete_toast": "Choice: Path A - Complete",
  "reward": { "set_flags": { "ridge_variant_j_choice_a_complete": true }, "inc_counters": { "gold": 35 } }
}
```

Contract registration:
- `kind="branching_choice"` with intro + choice A/B ids/zones/flags/toasts + `choice_gold`.

### 3) `puzzle_lite`
The player must trigger an **unlock** before the goal quest can start/complete.

Pattern:
- Puzzle quest starts on start zone and completes on an unlock event.
- Puzzle quest rewards set a flag (e.g. `ridge_variant_k_unlocked`).
- Goal quest has `requires_flags: ["ridge_variant_k_unlocked"]` and then completes at the goal zone.

Quest templates (sketch):
```json
{
  "id": "ridge_variant_k_switch",
  "start_toast": "Switch: Flip the Switch",
  "complete_toast": "Switch: Gate Unlocked",
  "stages": [
    {
      "id": "flip_switch",
      "start_on_event": { "type": "entered_zone", "payload": { "zone": "VariantKStartZone" } },
      "complete_on": { "type": "ridge_variant_k_unlock" }
    }
  ],
  "reward": { "set_flags": { "ridge_variant_k_unlocked": true }, "inc_counters": {} }
}
```
```json
{
  "id": "ridge_variant_k_route",
  "requires_flags": ["ridge_variant_k_unlocked"],
  "start_toast": "Switch: Reach the Exit",
  "complete_toast": "Switch: Complete",
  "reward": { "set_flags": { "ridge_variant_k_route_complete": true }, "inc_counters": { "gold": 40 } }
}
```

If you introduce a new event type, add it to `assets/data/events.json`:
```json
{ "name": "ridge_variant_k_unlock", "description": "...", "payload": { "source": "object" } }
```

Contract registration:
- `kind="puzzle_lite"` with unlock event name, unlocked flag, puzzle quest id/toasts, goal quest id/toasts/flag/gold, plus zones.

## Running the Showcase + Tests

Showcase preset:
```bash
python mesh_cli.py run-preset golden_slice_showcase
```

Contract suite (covers all registered variants):
```bash
python -m pytest -q -W error tests/test_golden_slice_variants_contract.py
```

Full suite:
```bash
python -m pytest -q -W error
```

