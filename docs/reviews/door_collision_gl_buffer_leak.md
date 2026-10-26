# Door collision GL-buffer leak

Found by Milestone 18A's performance QA. Fixed on branch `fix/door-spritelist-leak`. All measurements were taken in
hidden windows on an RTX 4070 (GL 4.6).

## Root cause

`SceneTransition.update` (`engine/behaviours/scene_transition.py`) is called on every frame. For a walk-in door that
uses its picture's box (`trigger_on_touch` with no `area_width`/`area_height`), it did this:

```python
sprite_list = arcade.SpriteList()      # GPU-backed: about 5 GL buffers and a geometry
for candidate in candidates:
    sprite_list.append(candidate)      # the player keeps a reference back: player.sprite_lists
hit_list = arcade.check_for_collision_with_list(self.entity, sprite_list)
```

- **Why it was made:** arcade 3's `check_for_collision_with_list` wants a `SpriteList`. An earlier compatibility
  change built one per check (pinned by the old test `tests/test_arcade_collision_sprite_list_compat.py`).
- **Why it stays alive:** appending a sprite to a list makes the sprite hold the list (`sprite.sprite_lists`).
  - The player is long-lived, so every list made for a check stayed referenced, and with it its GL buffers. That is
    one list, about 5 buffers, per update while such a door is in the room.
  - On a room change the old player and its lists form a reference cycle. Only Python's cyclic garbage collector
    frees it, whenever it happens to run, so in 2D the count kept climbing across room changes.
  - The player's growing `sprite_lists` also made every move of the player update every one of those lists.
- **The same pattern:** `Hitbox` and `Projectile` (`engine/behaviours/hitbox.py`, `projectile.py`) did the same per
  update for their targets, and are fixed the same way.
- **Not affected:** area doors (`area_width`/`area_height`, including the cottage interior's `area_at: "base"` door)
  never took this path.

## Fix

Each candidate is tested with `arcade.check_for_collision(entity, candidate)`: the same hit-box polygon test that the
list check ran per sprite. It runs on the CPU and makes no GPU objects. The order is unchanged: a door reports the
first candidate it touches.

Arcade's list check also skipped the sprite itself, so the door now skips itself too, as Hitbox and Projectile
already did. The global collision engine (`physics_runtime`, `gameplay_runtime`) is unchanged.

## Measurements

These are live GL buffers (after `ctx.gc()`) and the player's `sprite_lists`, on base `da87d9c` (before
#377, so the weather code is not involved) and on this branch.

### Before the fix

| Scene | 0 updates | 300 | 1,000 | 3,000 | `player.sprite_lists` at 3,000 |
|---|---|---|---|---|---|
| 2D, no door | 66 | 66 | 66 | 66 | 1 |
| 2D, inactive door (`trigger_on_touch` false) | 66 | 66 | 66 | 66 | 1 |
| 2D, active walk-in door | 66 | **1,566** | **5,066** | **15,066** | **3,001** |
| 2D, area door at its base | 66 | 66 | 66 | 66 | 1 |
| HD-2D village (cottage door, picture box) | 119 | **1,619** | **5,119** | **15,119** | **3,001** |
| HD-2D cottage interior (base-area door) | 15,075 (the village's, not yet collected) | 15,075 | 15,075 | 75 | 1 |

### After the fix

The buffers stay flat in every scene, and `player.sprite_lists` stays at 1:

| Scene | Buffers at every count (0–3,000 updates) |
|---|---|
| 2D, no door | 66 |
| 2D, inactive door | 66 |
| 2D, active walk-in door | 66 |
| 2D, area door at its base | 66 |
| HD-2D village (cottage door, picture box) | 119 |
| HD-2D cottage interior (base-area door) | 75 |

### Walking through doors for real (the player's own key events)

The walks covered a 2D room pair linked by `link_rooms` (picture-box doors), and the village cottage: in by its
picture-box door, out by its base-area door. There were five round trips each, and after every arrival the player
stood still for 300 frames.

| | Buffers after round trips 1–5 |
|---|---|
| 2D, before | 3,161 → 6,351 → 9,541 → 12,731 → 15,921 (the room changes free none of them) |
| 2D, after | 66 every trip |
| HD-2D, before | 1,619 → 3,174 → 4,729 → 6,284 → 1,619 (dropped only when the cyclic GC ran) |
| HD-2D, after | 119 every trip |

Every leg reached the right room, and no arrival re-entered a door during its 300 still frames.

## Issue #356

#356 reported +5 buffers per load of an ordinary 2D room, in a blank room with no doors. It is not this leak: its
growth was per room load, not per update, and it happened without doors.

Both of its reproductions now show no growth, on the base `da87d9c` and on this branch alike:

- **`tooling/gpu_lifetime_probe.py`** (4 reloads and 4 Play/Stop cycles):

  | Room | Buffers |
  |---|---|
  | 2D, no lights | 87 → 83 |
  | 2D, lights | 91 → 87 |
  | HD-2D | 79 → 80 (the first Play) |

- **A blank room reloaded 12 times** (after `gc.collect()` + `ctx.gc()`): 66 at every load. With 60 frames
  between loads: 86, then 81 at every later load.

It was fixed by earlier work, and its original reproduction is clean.

## Tests

- **`tests/test_behaviour_collision_checks.py`** replaces the old compatibility test:
  - doors, hitboxes and projectiles make no `SpriteList` for a check, and their candidates join no lists (over
    1,000 and 200 updates);
  - a door turned 45° (a diamond hit box inside a larger bounding box) agrees with arcade's list check at every
    position of a 21 × 21 grid, reporting the same actor;
  - a door never touches itself.
- The four tests that patched `check_for_collision_with_list` (combat, hitbox sound, projectile sound, shooter) now
  patch `check_for_collision`, which the code really calls.
