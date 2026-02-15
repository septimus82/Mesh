# Puzzle Room 03

Puzzle Room 03 introduces multi-switch ordering with a timed action window.
Players must pull two levers in the correct order, then activate a rune
before an 8-second timer expires.

## Entities

- **Entry trigger** (`puzzle_room3_entry_trigger`) emits `room3_entered` on player enter.
- **Lever Left** (`puzzle3_lever_left`) emits `lever_left_pulled` via Interactable.
- **Lever Right** (`puzzle3_lever_right`) emits `lever_right_pulled` via Interactable.
- **Rune Center** (`puzzle3_rune_center`) emits `puzzle3_rune_step` on enter via TriggerVolume.
- **Exit Door** (`puzzle3_exit_door`) is Interactable, gated by `require_flags: ["puzzle3.solved"]`.
- **Timer** (`puzzle3_timer`) 8-second timer, fires `puzzle3_timeout`; started by ActionListRunner, not auto-start.

## Event Flow

| Trigger | Event | Effect |
|---------|-------|--------|
| Player enters room | `room3_entered` | Clears flags, sets `puzzle3.locked` |
| Pull left lever | `lever_left_pulled` | Sets `puzzle3.left_pulled` |
| Pull right lever (left already pulled) | `lever_right_pulled` | Sets `puzzle3.right_pulled`, `puzzle3.window_active`; starts timer; emits `puzzle3_window_started` |
| Pull right lever (left NOT pulled) | `lever_right_pulled` | Emits `puzzle3_failed` with `reason: "order"` |
| Step on rune (window active) | `puzzle3_rune_step` | Stops timer; sets `puzzle3.solved`; clears `puzzle3.locked`; emits `puzzle3_solved`, `door3_opened` |
| Timer expires | `puzzle3_timeout` | Emits `puzzle3_failed` with `reason: "timeout"` |
| Reset cutscene completes | `puzzle3_reset` | Clears all progress flags; re-sets `puzzle3.locked` |

## Flags

| Flag | Meaning |
|------|---------|
| `puzzle3.locked` | Room initialised; door locked |
| `puzzle3.left_pulled` | Left lever has been pulled |
| `puzzle3.right_pulled` | Right lever has been pulled |
| `puzzle3.window_active` | Timed action window is open |
| `puzzle3.solved` | Puzzle complete; enables exit door |

## ActionListRunner Controllers

| Controller | Listens | Guards | Actions |
|------------|---------|--------|---------|
| `puzzle_room_03_init` | `room3_entered` | — | Clear all puzzle3 flags, set `puzzle3.locked` |
| `puzzle_room_03_left_correct` | `lever_left_pulled` | — | Set `puzzle3.left_pulled` |
| `puzzle_room_03_right_correct` | `lever_right_pulled` | require `puzzle3.left_pulled` | Set `puzzle3.right_pulled`, `puzzle3.window_active`; start timer; emit `puzzle3_window_started` |
| `puzzle_room_03_wrong_order` | `lever_right_pulled` | forbid `puzzle3.left_pulled` | Emit `puzzle3_failed` reason=order |
| `puzzle_room_03_rune_success` | `puzzle3_rune_step` | require `puzzle3.window_active` | Stop timer; clear `puzzle3.window_active`; set `puzzle3.solved`; clear `puzzle3.locked`; emit `puzzle3_solved`, `door3_opened` |
| `puzzle_room_03_timeout` | `puzzle3_timeout` | — | Emit `puzzle3_failed` reason=timeout |
| `puzzle_room_03_reset_after_fail` | `puzzle3_reset` | — | Clear all progress flags; re-set `puzzle3.locked` |

## Cutscenes

| Script | Purpose |
|--------|---------|
| `puzzle_room_03_reset_order` | Wait 0.5s → emit `puzzle3_reset` reason=order |
| `puzzle_room_03_reset_timeout` | Wait 0.5s → emit `puzzle3_reset` reason=timeout |

Two separate cutscene scripts allow different VFX/SFX per failure mode
while sharing the same reset event.

## Quest

Quest `puzzle_room_03` has three stages:

| Stage | Complete On | Emits |
|-------|-------------|-------|
| `step0` | `room3_entered` | — |
| `step1` | `lever_left_pulled` | — |
| `step2` | `puzzle3_solved` | `quest_room3_complete` |

## Save / Restore

All components support `saveable_state()` / `restore_state()`:
- GameState flags (all `puzzle3.*` flags)
- GameplayEventBus pending events
- ActionListRunner per-controller state
- TimerBehaviour elapsed time
- CutsceneRunner progress (mid-wait determinism)

Saving mid-timer-window and restoring preserves remaining time.
Saving mid-reset-cutscene and restoring continues the cutscene
deterministically.
