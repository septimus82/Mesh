# Milestone 7: consolidation plan

Branch `redesign/visual-editor`. The other two reports:
- [`milestone7_capability_inventory.md`](milestone7_capability_inventory.md): what exists and how sure we are.
- [`milestone7_capability_lab.md`](milestone7_capability_lab.md): what was run in the engine.

Aim: **make Mesh leaner without making it less capable.**
- This plan names the overlaps and says which implementation each capability should converge on.
- It says what must be protected first, and what changed in this milestone.
- Nothing was deleted. Every high-risk change below is a recommended migration, not something done here.

## 1. Overlapping architectures

| Area | Implementations today | Live in the game? | Converge on | Risk | Migration |
|---|---|---|---|---|---|
| **Timelines / cutscenes** | SequencePlayer (per object, moves with collision); CutsceneController (global, camera steps, `cutscenes.json`); CutsceneRunner (branching, deterministic, "commands" format) | SequencePlayer: yes (LAB-FIXED). CutsceneController: yes (CODE). CutsceneRunner: CLI/tests only | **One timeline runner** with SequencePlayer's step model, plus CutsceneController's camera and any-object steps and CutsceneRunner's branch/goto/label. Per-object or global is a property of where it's attached, not a separate engine. | Medium: 17 cutscenes in `cutscenes.json`; episode scenes use CutsceneRunner | 1. Add camera, any-object and branch steps to SequencePlayer. 2. A converter from `cutscenes.json` and CutsceneRunner commands to steps, with golden tests. 3. Point `CutsceneTrigger` at the new runner. 4. Archive the other two with the episode tooling. |
| **Event reactions** | ActionListRunner (inert: nothing calls `handle_event`); SetGameStateOnEvent; EmitEventOnEvent; ListenForEvent; IncrementCounterOnEvent; Studio's zones and dialogue choices | All but ActionListRunner | Studio's condition/effect model (M5) plus SetGameStateOnEvent as its runtime | Low–medium: 11 episode/puzzle scenes configure ActionListRunner but get nothing from it today | Either give ActionListRunner an `on_event` (one line, then lab-verify), or convert those scenes to SetGameStateOnEvent. Check SetGameStateOnEvent's possible double-fire first. |
| **Event buses** | MeshEventBus (live); GameplayEventBus (never assigned in the game) | MeshEventBus only | MeshEventBus | Low | Make `gameplay_event_bus` an alias of the live bus, so QuestHook and the HUD history start receiving events, then lab-verify a QuestHook. |
| **Quests** | canonical `engine/quests.py` QuestManager; legacy `engine/quest_manager.py` (constructed, then replaced); QuestRunner (CLI only); QuestHook (wrong bus) | Canonical only | Canonical QuestManager | Low | Task #128: stop constructing the legacy manager, move its 2 test files, delete it; QuestRunner goes with the episode tooling. Quests are also saved twice (`game_state` and `saved_quests`): keep one. |
| **Dialogue** | `Dialogue` (UI, graph, conditions); `DialogueRunner` (headless, no UI) | Dialogue; DialogueRunner only via ActionListRunner / cutscenes | Dialogue | Low | Route cutscene dialogue steps to Dialogue; archive DialogueRunner with ActionListRunner's users. |
| **Animation** | `Animator` (Studio writes it; top-left frame order); `AnimationFactory`/`AnimationPlayer` (templates and all shipped content; bottom-left order; blend, frame events, root motion) | Both | **One clip model**: Studio's authoring on top of AnimationPlayer's runtime features | **High.** Opposite frame orders: a naive switch silently plays the wrong frames. New Studio projects start on one and Studio writes the other. | 1. A shared slicing function with an explicit origin. 2. Teach Studio to read AnimationFactory clips. 3. Migrate content with a converter and visual checks. 4. Retire the loser. Lab-verify each step. |
| **Save formats** | SaveManager slots (F5/F9, pause menu); `SaveGameV1` (`save_1.json`, F6 reads it, nothing normally writes it); quick snapshot (`quick.json`, Ctrl+F6) | SaveManager (LAB) | SaveManager | Low–medium | Point F6 and Ctrl+F6 at slots; delete the other two writers with their duplicated diagnostics. Separately (new capability): per-room state that survives room changes. |
| **Prefabs** | `prefab_id` reference (resolved at load); Studio's deep copy | Both (LAB) | Both are valid. Name them: "linked" vs "copy". | Low | Studio: offer "place linked". A reference's `mesh_name` override should show in the dump and log. |
| **Parallax** | `background_layers` / `foreground_layers` (LAB); `background_planes` (schema rejects it from files) | layers only, from files | `background_layers` | Low | Convert planes to layers in the legacy editor's model, or add a converter; then archive `parallax_model`'s draw path. `tint` exists only in planes: add it to layers first. |
| **Movement pairs** | Patrol / PatrolPath; FollowTarget / FollowPath; Collectible / PickupCollectible; SceneExit / SceneTransition | All | PatrolPath, FollowPath (A*), PickupCollectible, SceneTransition | Low each | One pair at a time: caller check (JSON and prefabs), convert content, keep the old name as an alias. |
| **Combat damage** | `Health.apply_damage` (Hitbox, Projectile); `DamageOnTouch` (only logs) | apply_damage | apply_damage | Low | Make DamageOnTouch call `apply_damage`; add a lab check. |
| **Collision models** | Player: `components.collider` (box/circle); NPCs: arcade hit boxes, ignoring `components.collider`; nav grid: tiles only | All | One collider per object, used by players, NPCs and (as blocked cells) the nav grid | Medium | Study before changing: pathing around solid objects is a new capability. |
| **Ambient light** | config `lighting_ambient_color` × scene `ambient_light_rgba` tint; scene `lighting_ambient_color` and `lighting_enabled` (not read); `ambient_darkness_alpha` (legacy editor only); day/night (overrides when on) | First and last | One ambient per room with a project default, plus day/night as an optional driver | Low–medium | This milestone fixed two leaks. Next: read the scene keys the demos already use, or migrate them. |
| **MCP write surfaces** | `authoring` tools (M6) and ~23 older `AIOps` tools | Both | `authoring` | Medium (external AI clients) | Route the remaining AIOps writes through `authoring`, keeping their names as thin adapters, then deprecate. |
| **Input** | config bindings, `input_dispatch`, the capture router; two hotkey systems that shadow each other | All | One action map | Medium | Known collision pattern (5+ incidents). Not this milestone. |
| **Runtime → editor imports** | The render path imported the outline model from `engine/editor/` | — | Engine-neutral models | Low | **Done for the outline model** (below). The remaining runtime imports are editor features themselves (ghosting, cursor, overlays) and go with the legacy editor. |

## 2. Safe changes made in this milestone

Each one is evidence-backed and fixed at its source:
- the lab found it, or it shares the exact defect the lab found;
- it has a regression test;
- it is listed in [`../../MESH_SALVAGE.md`](../../MESH_SALVAGE.md) with how to restore the old behaviour.

| # | Change | Evidence | Test |
|---|---|---|---|
| 1 | Lights are drawn through the world camera (`LightManager._draw_layer_safe`) | Lab: glow drawn at world coordinates as screen coordinates | lighting suites; lab check 1 |
| 2 | A scene load drops the previous scene's object lights and resets the room ambient to the project's (`configure_scene_lighting`, `LightManager.clear_dynamic_lights`) | Lab: a frozen torch light and a dark tint carried into later rooms | `test_scene_lighting_reset.py` |
| 3 | `DayNightCycle` leaves the ambient alone while switched off | Lab: ambient [58,41,46] instead of the project's [255,255,255] | `test_day_night.py` |
| 4 | SequencePlayer `move_to` moves `speed × dt`, never past the target | Lab: overshoot oscillation; the sequence never finished | `test_sequence_player_move_to.py` |
| 5 | Patrol and FollowTarget, same defect | Identical call (audit) | `test_patrol_follow_speed.py` |
| 6 | Render batching merges only neighbouring draws | Lab: a sprite drawn behind one it should cover | `test_render_queue_batching_groups.py` |
| 7 | Sprite shadows anchor at the feet | Lab: no visible shadow under any opaque sprite | `test_sprite_shadow_model_contract.py` |
| 8 | Projectiles move `speed` px per second | Lab: shots 20,000 px off the map, no hits | `test_projectile_speed.py` |
| 9 | `sprite_outline_model` moved from `engine/editor/hd2d/` to `engine/` (both old paths are shims) | Audit: the render path's only `engine.editor` dependency; pure, stdlib only | outline and render suites |
| 10 | `engine/runtime_probe.py`, `AudioManager.recent_plays`, and runtime/angle/size in Studio's play dump | Needed to verify the above | lab |

Two ratchet baselines were updated by their documented procedure:
- the lighting module's exception-envelope line numbers (the same handlers, moved by 2 lines; silent `except: pass` blocks there went from 3 to 1);
- the fast-marking allowlist (one entry no longer needed).

## 3. Protect before retiring the legacy editor

These capabilities exist **only** in the legacy editor today. Each needs a Studio home, or a deliberate decision to drop it, before `engine/editor/` goes:
1. **Lights and occluders:** placing, moving and deleting static lights; the occluder polygon tool; lighting presets (`editor_lights_controller.py`, `editor_light_occluder_ops.py`).
2. **HD-2D look panel:** shadows, depth tint, outlines, look presets and per-object overrides (`engine/editor/hd2d/*`, ~390 tests).
3. **Safe asset rename/move with reference updates** (`engine/editor/asset_ops/`, ~2.2k lines).
4. **Background planes editing**, after converting them to `background_layers`.
5. **Item, quest and dialogue database editors** (`items.json`, `quests.json`, `dialogues.json`).
6. **Inspector fields for `render_layer` / `depth_z`.**
7. **The engine repo's own scenes**, which Studio doesn't open (it needs a project with a world).

## 4. Studio authoring gaps, prioritised

This is a priority list, not a redesign. Lighting and HD-2D come first, because they are the engine's identity and the lab now shows them working.

1. **Lighting per room.**
   - A lights tool: place a light, then set colour, radius and flicker.
   - Occluders: from walls automatically, plus rectangles.
   - Room settings: lighting on or off, and ambient colour.
   - The scene-level `lighting_enabled` switch has to be made to work first (it isn't read).
2. **Backgrounds:** a room's background and foreground parallax layers (`background_layers`, LAB-verified).
3. **HD-2D look:**
   - per room: shadows, depth tint, outlines;
   - per object: shadow size and opacity, `render_layer`, `depth_z`.
   - Port the legacy presets.
4. **Camera:** room bounds, initial zoom, and zoom areas drawn on the map (LAB-verified runtime).
5. **Behaviour fields Studio can't edit:**
   - ParticleEmitter declares no fields;
   - lists of objects (patrol waypoints, sequence steps) need a point/step editor.
   - A sequence editor is the natural next authoring feature: the runtime now works.
6. **Room music.**
7. **Save points and per-room persistence**, once per-room state exists.

## 5. Recommended next engine milestone

**"Runtime correctness, measured."** Extend the Capabilities Lab and fix what it finds, before building any new subsystem or Studio UI.

Why:
- this milestone's lab found **eight real engine bugs in seventeen checks**;
- each bug sat behind green unit tests;
- most are in the HD-2D and lighting features the engine is meant to be known for.

Scope:
1. **Lab checks for what is still UNVERIFIED** (one room each):
   - **Rendering:** depth tint; outlines; shadow polygons at camera zoom ≠ 1.
   - **Lighting:** cookies; light shafts; ToggleSceneLights; day/night over time; fog.
   - **Camera:** camera shake.
   - **Events:** CutsceneController with camera steps.
   - **AI:** EnemyAI movement; NpcSchedule.
   - **Gameplay:** Vendor; drops; DamageOnTouch.
   - **Events and quests:** QuestHook after the bus fix; ActionListRunner after an `on_event`.
2. **Low-risk consolidations from section 1:**
   - one event bus;
   - finish the quest consolidation (#128);
   - SaveManager-only;
   - background planes → layers.
3. **Make the lab a gate.** Run `tooling/capability_lab.py` alongside the acceptance tests, so a rendering or lighting regression shows up as a failed measurement, not a user report.
4. **Then** Studio gap 1 (lighting) on the verified runtime.

Height-based 2.5D (bridges, floors, height collision) should wait: it is a new subsystem, and it would rest on the parts this lab just had to fix.

## 6. The completion questions

1. **What can Mesh do today?**
   - All of the inventory's verified list:
     - rooms, doors and maps;
     - prefabs;
     - dialogue with conditions;
     - A* pathing and line-of-sight AI;
     - scripted sequences;
     - coloured, flickering, moving lights with hard shadows and per-room darkness;
     - y-sorted HD-2D draw order with feet shadows;
     - parallax;
     - camera follow and zoom areas;
     - particles;
     - positional sound;
     - projectile combat;
     - save/load;
     - plugin behaviours;
     - AI co-authoring.
   - Much more exists in code but is UNVERIFIED.
2. **What has been tested in the running engine?**
   - 16 capability checks in the real window, all passing after fixes; one headless check confirms `background_planes` is broken from files.
   - The M1–M6 acceptance suites.
3. **Valuable but hidden from Studio:**
   - static lights, occluders and ambient;
   - parallax layers;
   - the HD-2D look (shadows, tint, outlines, `render_layer`/`depth_z`);
   - camera zoom and areas;
   - particles' settings;
   - sequences;
   - music;
   - safe asset rename.
4. **Duplicated architectures:**
   - three timeline engines;
   - two event buses;
   - three quest systems;
   - two dialogue runners;
   - two animation systems;
   - three save formats;
   - two parallax systems;
   - two prefab models;
   - two MCP write surfaces;
   - overlapping behaviour pairs;
   - competing input paths.
5. **What can safely be simplified:**
   - the event bus;
   - the legacy quest manager;
   - the two non-slot save formats;
   - `background_planes` → `background_layers`;
   - ActionListRunner and DialogueRunner (after converting their content);
   - the movement pairs;
   - REMOVE CANDIDATES after a caller check: `RangedAttackAI`, `InventoryHolder`, the unused `Particle` class, the debug-only lighting plan modules.
   - Animation is **not** a safe simplification yet (opposite frame orders).
6. **Protect before retiring the legacy editor:** section 3.
7. **Next milestone:** section 5.
