# The saved world (#390)

**Principle:** the game's authored world is authoritative. A save restores the player's progress and the runtime
state of the world, not a copy of how the world was authored on the day of the save.

## What was wrong

A save slot is a room snapshot plus the game state. The snapshot (`build_scene_snapshot`) started from a deep copy
of the room as authored when it loaded. Loading the save replayed that copy:

- an HD-2D room's sculpted ground, scattered decoration, wind and animation;
- its lights and map.

So two things went wrong:

- **Stale worlds:** a room re-sculpted, re-scattered, re-lit or re-mapped after the save never reached it.
- **Size:** a decorated room's save weighed 106 KB, against 26 KB for the 2D starter; about 1 MB at the scatter
  limit.

**What play changes, investigated before changing the format:**

| Part of the room | Changed by play? | Evidence |
|---|---|---|
| `settings` (terrain, scatter, lights, weather, wind, motion, music...) | **only the camera's zoom** | the snapshot copies them from the authored room and updates only `settings.camera.zoom`; the console's encounter tweaks change the runtime `scene_settings`, never saved |
| `tilemap` | **no** | `set_tile` is called only by the legacy in-engine editor, which saves the room file itself |
| `lights`, `occluders`, backgrounds, `layers` | **no** | copied from the authored room, never updated |
| `entities` | **yes**: positions, behaviour settings | updated from the running sprites |
| entities' inner states (health, timers, quest hooks...) | **yes** | `saved_entities` (each behaviour's `saveable_state`), by id |
| game state: flags, variables, quests, **room memory** (authored objects collected, destroyed, defeated) | **yes** | `state` / `game_state` |

## The design

### Loading a save
The room it was made in (`meta.scene_path`) is read as it is now. Everything authored comes from that room. From the
save come:

- the camera's zoom;
- the objects;
- the game state.

The objects are reconciled with the room by `id`:

| Case | Result |
|---|---|
| An object in the room and in the save | **the room's, as authored now** (dialogue, picture, behaviours), standing where play left it (`x`, `y`, `elevation`); its inner state (health, a quest hook's, a dialogue's progress) from `saved_entities` |
| In the room, not in the save (added since) | appears, unless room memory says play removed it |
| In the save, from the room at save time (`meta.room_entity_ids`), no longer in the room (deleted since) | left out |
| In the save, not from the room (spawned during play) | kept |
| Without an `id` | kept as saved |
| A save from before #390 (no `room_entity_ids`) | every saved object kept (as before), plus objects added since |

**A save whose room can't be read** (renamed, deleted):

- an older save loads from its own copy of the room, as it always did;
- a new save has no copy: **loading it is refused** before anything is applied (`LOAD_ROOM_MISSING`: a clear error and
  a toast). Mid-game the player stays where they are; with no game running, the start scene opens. The save file is
  never changed, so it loads again once the room is back (tested).

### Saving
New saves leave out what play doesn't change: the room's settings (only the camera's zoom is kept), its map, lights,
occluders and backgrounds. They record `meta.room_entity_ids`. Only when the room can be read at save time: a scene
built in memory (no room file) keeps its whole snapshot, a complete save as before #390. The decorated room's save goes from 106 KB to about
26 KB.

## Compatibility

| Requirement | How it is met | Test (real saves, hidden-window games) |
|---|---|---|
| Existing saves still load | composed the same way; their copy of the room is ignored | `pre390_hd2d.json`, `pre390_2d.json`: saves written by the engine before the change |
| Existing progress is not lost | player place, flags, variables, room memory, objects' states all come from the save | player position, `met_the_elder`, `coins`, the removed object |
| New saves avoid terrain and scatter copies | `slim` | the new save's settings are `{}`; under half the old size |
| A terrain edit appears in an older save | the room is authoritative | the old save loaded after a re-sculpt, a cleared scatter and a new wind shows the new ground, no scatter, 12 m/s |
| Missing and renamed objects | the reconciliation table above | Mara deleted after a new save: gone; a Newcomer added: present |
| Doors, containers, quest objects | their inner states are `saved_entities`, restored by id, unchanged by this design | a barrel's damage (Health) kept while its picture changes; `test_save_entity_quest_state.py`; all 618 save-related tests pass |
| Authored dialogue, appearance, behaviour edited after a save | the room's object as authored now, where play left it | the Elder's new dialogue, a repainted barrel, Mara's added behaviour all reach an older save |
| A new save whose room is missing | refused clearly, recoverable, file untouched | the room renamed away: refused, game unchanged, save byte-identical; renamed back: loads |

## Trade-offs and what is not done (bounded)

- **An object the creator moves after a save** stays, in that save, where the save found it: a save can't tell a
  creator's move from play's. Its dialogue, picture and behaviours do follow the room.
- **A new save needs its room.** Without it, loading is refused (above), never half-built; an older save still has its
  own copy.
- **`DoorLock` has no saved state** (no `saveable_state`). A door unlocked in play is restored only through the flags
  or events that unlocked it. This predates #390 and is unchanged.
- **Gameplay that changes the world's shape** (terrain dug, tiles changed in play) doesn't exist today. If it is
  added, it belongs in the save as a recorded change, not as a copy of the room.
