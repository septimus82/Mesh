# Milestone 8: runtime reliability and persistent game state

Branch `redesign/visual-editor`, following Milestone 7 (`da2616b`). Status and summary: [`MESH_REBUILD.md`](../../MESH_REBUILD.md).

**Goal:** make the existing engine dependable before expanding it.

**Method:** every claim below was measured in the real window first.
- A defect is called **confirmed** only when a run showed it.
- **Suspected** means read in the code, not shown.
- Each fix is at the defect's source, has a unit test that fails without it, and was re-measured in the window.

Evidence:
- Reports and screenshots from the final runs are in [`milestone8_evidence/`](milestone8_evidence/).
- The harnesses are `tooling/runtime_gate.py`, `tooling/acceptance_persistence.py` and `tooling/capability_lab.py`.

## 1. A trustworthy baseline

**Full suite at `da2616b`** (`py -3.13 -m pytest -q -p no:cacheprovider`): **9 failed, 9,351 passed**, 8 skipped, 164 deselected.
- These are exactly the nine known baseline failures:
  - `test_editor_input_regression` (selection);
  - `test_monster_battle_sprites` (headless probe);
  - `test_rmmz_passability_import` ×2 (missing fixtures);
  - five `test_widget_overlay_*` (headless overlay rendering).
- Milestone 7's tenth failure, an exception-count ratchet tripped by the lab harness, is gone.

**Graphical suites at `da2616b`**, run through the new gate: 5 of 7 passed. Both failures were investigated:

| Suite | Result | Cause | Action |
|---|---|---|---|
| Milestone 1 first workflow | 2/3, stopped at "place a person" | **Input delivery, not the app.** The app's log shows the mouse *move* arriving but no *press*, 3 s after the window opened. The identical click passed 15/15 when the suite was rerun on its own. | The gate now reruns a failed suite once and marks a pass on the retry as FLAKY (never silently green). |
| Capability lab | 15/17 | (a) **Harness flaw.** The occluder check sampled 150 px out, while the light's flicker shrank its reach to about 145 px, so both points were dark. (b) `background_planes`: the known defect. | (a) It now samples just past the pillar and averages the 8 flicker frames. (b) It is now reported as KNOWN (below). |
| Milestones 2–6 | 23/23, 15/15, 20/20, 17/17, 14/14 | — | — |

### The runtime gate

```bash
py -3.13 tooling/runtime_gate.py
```

(`MESH_GUI_AT` and `MESH_GUI_POLITE` as for the GUI tests.)

- **What it runs:** every real-window suite, one after another:
  - Milestones 1–6;
  - the persistence suite (new);
  - the capability lab.
- **Time:** about 45 minutes, on the desktop. It is not part of the quick test cycle.
- **When to run it:** before a merge, after changes to rendering, lighting, movement, scene loading or saving, and at the end of a milestone.
- **Results:**
  - one reused folder, `artifacts/runtime_gate/`, with a log and the evidence per suite, plus `gate_summary.json`;
  - exit code 0 only if every suite passed.
- **Retries:** a failed suite is rerun once. Both attempts are kept, and a pass on the retry is reported as FLAKY.
- **Older projects:** the launcher suite's "older project" step uses `--old` paths, else `./mygame` (copied by the suite; the original is checked unchanged), else a generated project. The summary says which, and that the last is weaker.
- **KNOWN defects:** the lab reports a documented, deferred defect as KNOWN. It shows in every report but does not fail the gate. If it starts passing, the lab says PASS and the note should be removed.
- **Never** run the gate at the same time as the pytest suite: both are heavy, and the GUI tests time out.

## 2. Game state across rooms, saves and a restart

`tooling/acceptance_persistence.py` builds a disposable two-room project with Mesh's own authoring operations:
- **Hall:**
  - a coin (`PickupCollectible`);
  - a lamp zone that sets the flag `lamp_lit`;
  - a gate shown only while `lamp_lit` is set;
  - a dummy (`Health`) that a turret keeps hitting, so its HP is object state that changes over time.
- **Yard.**
- Doors between them.

The test plays it in Mesh Studio's real window with OS-level keys, through the brief's ten steps:
1. collect the coin;
2. light the lamp;
3. go to the Yard and back (coin still gone; flag and gate kept);
4. save;
5. change things;
6. load (player position, coin, flag, gate and the dummy's HP all as saved);
7. go out and back after loading;
8. **close Mesh Studio, start it again, start a new game and load the save**;
9. go out and back again.

The disposable project is deleted afterwards.

### Current behaviour, established first

| Run | Result | What it showed |
|---|---|---|
| 1 | 4/12 | Arriving in the Yard put the player **outside the map** (y = −48, then walking into the void). Collecting the coin and setting the flag worked. |
| 2 (arrival fixed) | 5/12 | **The collected coin came back** after leaving the room and returning, **and after loading a save made in that room**. Flags, the gated object and the player's position did survive. |
| 3 (room memory) | 7/12 | Room changes kept the coin gone, but saves didn't yet: doors don't go through the code path first hooked (see P2). |
| 4 | **12/12** | — |
| Check without fix P4 | 10/12 | **The dummy's HP after a load was 995, with the save made at 990**: the saved object state was lost. |

### Defects confirmed and fixed

| # | Defect | Fix | Test |
|---|---|---|---|
| P1 | **Door arrival spots off the map.** Every arrival was put 96 px below its door, so a door on a room's bottom rows put arriving players outside the map. | `project_ops._arrival_spot`: below the door if that is on the map, else above, else beside it. Already-authored arrivals are unchanged. | `test_project_ops.py` |
| P2 | **Collected or defeated objects came back** when the player returned to a room, or loaded a save made in it. A room is rebuilt from its authored file on every load, and nothing remembered what had gone. | **Room memory** (`engine/scene_runtime/room_memory.py`). When a room is left, the authored objects (those with an `id`) that were there when it loaded and are now gone are recorded per room in the game state's variables (`room_memory`), and left out when the room loads again. This happens in `load_scene`, the one path every room change takes. Doors use `request_scene_change`, which skips `perform_scene_change`, the first hook tried. Saves record the current room first. No new save format: the game state is already inside every save. | `test_room_memory.py` |
| P3 | **After loading a save, the game thought the save file was the room.** A save records the room it was made in (`meta.scene_path`). After a load, the current scene path *is* the save file, so the next save recorded the save as its own origin. The loader resolves the room's map from that path. | `SceneController.room_path` is the real room, also when loaded from a save (`SceneLoader.last_saved_from`). Saves and room memory use it. Suspected consequence, not run: a save, load, save, load chain losing its map. Fixed because room memory needs the real room anyway. | `test_room_memory.py` |
| P4 | **A loaded save's object states went to the wrong room.** `apply_loaded_payload` applied them to the room on screen, then the saved room loaded on the next frame, fresh. | SaveManager queues them, and `load_scene` applies them once the saved room exists. The immediate apply, whose diagnostics are tested, is unchanged. | `test_room_memory.py`; the window check above |

**What persists and what resets** (documented in `room_memory.py`):
- **Persists:**
  - flags, counters, variables and quests (game state);
  - authored objects removed during play (collected, destroyed, defeated), per room;
  - in a save: the player's position, the saved room's object positions, and behaviour state (HP, timers, patrol progress: the existing `saveable_state` protocol).
- **Resets:**
  - objects spawned at runtime (projectiles, effects), which have no `id` and are never recorded;
  - positions of moving NPCs in rooms the player left;
  - everything, when a new game starts. Mesh Studio's play-test starts a new game each time and now also resets when play stops, so the editor shows rooms as authored.
- **Defeated enemies stay defeated.** There is no respawn option yet.

## 3. Runtime correctness

New capability-lab rooms and checks:
- **Zoomed:** the Lights room's light and pillar under a 1.8× camera area.
- **Day:** a clock running an hour a second, and two scheduled shopkeepers.
- **Look:** outlines and depth tint.
- **Unlit:** a room that switches lighting off.
- **Enemy:** an EnemyAI chaser.
- **Round trips:** three Lights ↔ Paths round trips with a static light and a moving light.
- **Sequence and quest:** a sequence's last step, plus a QuestHook.

**The final lab: 27/27, plus 1 KNOWN.**

| Check | Before | After | Verdict |
|---|---|---|---|
| Hard shadows at camera zoom 1.8 | Behind the pillar 48 vs 52 in the open: the shadow was drawn unscaled, near the player, away from the pillar (screenshot) | 14 behind vs 52 in the open; 73 between light and pillar | **Confirmed, fixed.** `shadow_pipeline` subtracted the camera's corner and ignored zoom. Shadows are now drawn through the world camera, like the lights since Milestone 7. |
| Lights over 3 round trips | Static light, pillar and the moving light correct each visit | Same | **Works.** |
| The "12 px torch-light offset" (Milestone 7) | A moving light seemed to trail its object by 12–30 px | Light, owner and object match exactly within one frame | **Not a bug.** The lab read the object's position from a second, later dump than the light's. Fixed in the harness (`sprite(name, state)`). |
| Day/night over time | The clock stayed at 21:00 | 07:18 → 12:19 in 5 s; 8 different ambient colours | **Confirmed, fixed.** `apply_scene_settings` returned early when a room named its `background_color`, and Studio rooms do. That also skipped `initial_spawn`. A room that doesn't set day/night now gets the project's setting (it used to leak from the last room), and the project's ambient comes back when the clock stops. |
| NPC schedules (Patrol before or after NpcSchedule) | Neither moved after 08:00 | Both stood until 08:00, then walked about 256 px of their routes | **Confirmed, fixed.** An object's behaviours are attached together after all are built, so NpcSchedule's constructor never found the Patrol, in either order. It now finds it on its first update. |
| Outlines | Magenta 1–2 px outside the sprite | Same | **Works.** |
| Depth tint | Near and far sprites the same colour | Near (235,235,235), far (37,37,147) | **Works, harness error.** In y-sort rooms depth tint follows `render_layer`; `depth_z` counts only in explicit-z rooms. |
| A room switching lighting off | Lighting stayed on (the scene key was never read) | Off, floor at full brightness; back on in the next lit room | **Confirmed, fixed.** `settings.lighting_enabled` per room, else the project's setting. Demo scenes and the docstring already used it. |
| EnemyAI chase speed (100 px/s) | **9 px/s** | 85–95 px/s (measurement includes the start) | **Confirmed, fixed.** It moved only on the frames it re-steered (every 0.2 s). Its own parameter says the interval is for steering. |
| A sequence runs to its end and triggers what follows | Its last signal set a flag through SetGameStateOnEvent | Same | **Works.** |
| QuestHook counts a live event | Code: subscribed only to `gameplay_event_bus`, which the game never creates | The herald's last signal completed the hook's step and set a flag | **Fixed** (consolidation, section 4). |

**Confirmed, not fixed (minor):**
- The project templates give the player's CameraFollow an explicit `zoom: 1.0`. That overrides a room's own `camera.zoom.initial` in every new project. Zoom *areas* work. The line came from a monster-boot fix, so it was left for a decision rather than changed blind.

**Not covered** (UNVERIFIED in the engine):
- object collision with `components.collider` on NPCs (code says NPC movers ignore it);
- cookies, light shafts, fog, camera shake;
- CutsceneController, Timer, Vendor, drops;
- web export.

## 4. Consolidation

| Candidate | Decision | Evidence and why it is safe |
|---|---|---|
| **The second event bus** (`GameplayEventBus`) | **Converged for QuestHook.** QuestHook now also listens on the live event path (`on_event`) when no gameplay bus exists. The bus itself stays. | Only `mesh_cli/episode.py` creates the gameplay bus. Events go to it *instead of* the live bus (`event_emit`), so a hook never counts an event twice. Deleting the bus would break the episode harness, and its event-type validators are imported by eight behaviours. The HUD's event history panel still reads only the gameplay bus (a debug panel; left). |
| **Duplicate save entry points** | **F6 in play now loads the SaveManager quick save** (the one F5 writes and F9 loads). Before, it loaded `save_1.json`, which F5 writes only when there is no SaveManager: a stale or missing save. The old file stays the no-SaveManager fallback for both F5 and F6. | No test pinned F6's old behaviour. New test in `test_milestone8_runtime_fixes.py`. |
| The quick snapshot (`quick.json`, Ctrl+F6) | **Deferred.** | The monster companion's persistence is built on it (`test_companion_mind_quick_snapshot.py` and others). Merging it into slots needs a migration of that state. |
| `background_planes` → `background_layers` | **Deferred; reported as KNOWN by the lab.** | No scene or project in the repo uses planes. The two systems position images differently (planes: screen offsets; layers: anchored in the world), and layers have no alpha or offset. A faithful converter needs a measured visual-equivalence test. Adding planes to the schema would entrench the duplicate. Remaining risk: the legacy editor can still add planes, and a scene saved with them fails to load. Recommended: remove plane authoring with the legacy editor, or convert with that equivalence test. |

Nothing else was removed. Animation systems, cutscene engines and controllers were left alone, as the brief asked.

## Other findings (not fixed; not blocking)

| Severity | Finding | Evidence |
|---|---|---|
| Low | Lost OS-level mouse press about 3 s after Mesh Studio's window opens (GUI test flakiness) | Milestone 1 suite: the app's log shows the move without the press; rerun 15/15 |
| Low | EnemyAI rotates its sprite toward its target (`entity.angle`), odd for top-down RPG sprites | Lab `enemy.png` |
| Low | The scene validator warns "missing required params goal_x, goal_y" for a FollowPath configured in `behaviour_config` (Studio's form) | Lab log (Milestone 7) |

## Validation

| Check | Result |
|---|---|
| Full suite, final | **9 failed, 9,365 passed**, 8 skipped: exactly the 9 baseline failures. (A mid-milestone run had a tenth: the exception-count ratchet, tripped by the persistence harness's own broad `except`. It was narrowed, and the ratchet passes.) |
| Ruff gate, mypy island | Clean |
| Runtime gate, final | **8/8 suites, no retries:** M1 15/15, M2 23/23, M3 15/15, M4 20/20, M5 17/17, M6 14/14, persistence 12/12, capability lab 27/27 plus 1 KNOWN. Summary: `milestone8_evidence/gate_summary.json`. |
| New unit tests | `test_room_memory.py` (6), `test_milestone8_runtime_fixes.py` (7), `test_project_ops.py` (+1). Each fails without its fix. |

## How to try it

1. Open Mesh Studio (`Mesh Engine.bat`) and make a **Blank** project.
2. **Add a coin:**
   - add an Empty object; give it a picture;
   - under Behaviours, add **PickupCollectible**.
3. **Add a second room:** right-click an empty spot on the map near an edge and choose **Add door to a new room...**. A door appears both ways, each with an arrival spot on the map.
4. **Play (F4):**
   - pick the coin up (face it, press E);
   - walk through the door and back: the coin stays gone.
5. **Save and restart:**
   - press **F5** to save; walk somewhere; press **F9**: you're back where you saved;
   - stop, close Mesh Studio, open the project again, press F4 then F9: the save loads, coin still gone.
