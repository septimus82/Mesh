# Mini Campaign 01

A stitched campaign connecting three vertical slices into one cohesive
playable sequence: **Town Schedule → Puzzle Room 03 → Combat Vignette**.

## Flow

```
town_schedule_01          puzzle_room_03           combat_vignette_01
┌──────────────┐         ┌──────────────┐         ┌──────────────────┐
│ Enter town   │         │ Enter room   │         │ Enter arena      │
│ Meet vendor  │         │ Left lever   │         │ Kill sentry      │
│ Find secret  │──exit──▶│ Right lever  │──exit──▶│ Collect reward   │
│              │         │ Step on rune │         │                  │
└──────────────┘         └──────────────┘         └──────────────────┘
 quest_town_complete      quest_room3_complete     quest_combat_vignette_complete
 → campaign.town_complete → campaign.puzzle_complete → campaign.combat_complete
 → go_to_puzzle_room_03   → go_to_combat_vignette_01 → campaign_complete
```

## Campaign Quest

Quest `mini_campaign_01` (type: main) with 3 stages:

| Stage | Title | Complete On | Emits |
|-------|-------|-------------|-------|
| `town` | Complete the Town | `quest_town_complete` | — |
| `puzzle` | Complete the Puzzle | `quest_room3_complete` | — |
| `combat` | Complete the Combat | `quest_combat_vignette_complete` | `campaign_complete` |

## Events

| Event | Description | Source |
|-------|-------------|--------|
| `campaign_started` | Campaign begins | Manual / game init |
| `go_to_puzzle_room_03` | Requests transition to puzzle room | ActionListRunner on `quest_town_complete` |
| `go_to_combat_vignette_01` | Requests transition to combat | ActionListRunner on `quest_room3_complete` |
| `campaign_complete` | Entire campaign finished | Quest `mini_campaign_01` final stage |

## Global Flags

| Flag | Set When | Persists Across Scenes |
|------|----------|------------------------|
| `campaign.started` | Campaign begins | Yes |
| `campaign.town_complete` | Town quest done | Yes |
| `campaign.puzzle_complete` | Puzzle quest done | Yes |
| `campaign.combat_complete` | Combat quest done | Yes |

Per-scene flags (`town.entered`, `puzzle3.solved`, `cv.completed`, etc.)
also persist across transitions.

## Scene Modifications

### town_schedule_01.json
Added:
- `campaign_town_done_ctrl` — ActionListRunner listening for `quest_town_complete`
  → sets `campaign.town_complete`, emits `go_to_puzzle_room_03`
- `town_exit_to_puzzle` — SceneExit portal listening for `go_to_puzzle_room_03`
  → transitions to `scenes/puzzle_room_03.json`

### puzzle_room_03.json
Added:
- `campaign_puzzle_done_ctrl` — ActionListRunner listening for `quest_room3_complete`
  → sets `campaign.puzzle_complete`, emits `go_to_combat_vignette_01`
- `puzzle_exit_to_combat` — SceneExit portal listening for `go_to_combat_vignette_01`
  → transitions to `scenes/combat_vignette_01.json`

### combat_vignette_01.json
Added:
- `campaign_combat_done_ctrl` — ActionListRunner listening for `quest_combat_vignette_complete`
  → sets `campaign.combat_complete`

## Prefabs

| Prefab | Tags | Behaviours | Purpose |
|--------|------|------------|---------|
| `campaign_portal` | campaign, portal | SceneExit | Scene transition portal |
| `campaign_controller` | campaign, controller | ActionListRunner | Campaign event wiring |

## Persistence

| Component | Save/Restore |
|-----------|-------------|
| GameState flags | `snapshot()` / `restore()` |
| GameplayEventBus | `saveable_state()` / `restore_state()` |
| ActionListRunner | `saveable_state()` / `restore_state()` |
| Health | `saveable_state()` / `restore_state()` |
| DayNight clock | `saveable_state()` / `restore_state()` |

Scene transitions carry global state. NpcSchedule and TimeOfDayGate
re-derive from clock time on next `update()`.

## Integration Tests

`tests/test_mini_campaign_01_integration.py` — 11 tests:

1. Happy path (full campaign)
2. Global flags persist across scenes
3. Save/restore after town completion
4. Save/restore mid-puzzle
5. Save/restore mid-combat
6. Determinism (identical runs → identical results)
7. Quest chain stage progression
8. Scene exit prefab wiring
9. Player HP persists across scenes
10. Campaign events registered in events.json
11. Campaign quest registered and loadable
