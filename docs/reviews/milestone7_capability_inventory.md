# Milestone 7: capability inventory

Branch `redesign/visual-editor`. Companion reports:
- [`milestone7_capability_lab.md`](milestone7_capability_lab.md): what was run in the real engine, with measurements.
- [`milestone7_consolidation_plan.md`](milestone7_consolidation_plan.md): overlaps, migrations, Studio gaps and the next milestone.

Mesh is a general-purpose 2D engine with HD-2D ambitions. This inventory lists what it can do, how sure we are, and what should happen to each part. The rule throughout: **preserve capabilities, not necessarily code**.

## How to read this

**Evidence.** A capability is only called verified if it was seen working in the running engine.

| Label | Meaning |
|---|---|
| **LAB** | Seen working in the real Arcade window in this milestone's Capabilities Lab (measured; screenshot in `milestone7_lab/`). |
| **LAB-FIXED** | The lab found it broken. It was fixed at its source, with a regression test, and the lab then passed. |
| **M1–M6** | Verified in the real window by an earlier milestone's acceptance run. |
| **CODE** | Traced in the source by a read-only audit, not run. A finding here may be wrong. |
| **TESTS** | Covered by unit or contract tests only. Tests here are almost all headless; none opens a GL context. |
| **UNVERIFIED** | Not demonstrated in the running engine. |
| **BROKEN** | Shown not to work, in the lab or by direct reproduction. |

**Classes.** These are the brief's classes:
- **KEEP**: works and is the right shape.
- **REFACTOR**: keep the capability, rework the code.
- **CONSOLIDATE**: two or more implementations of one capability; converge on one.
- **EXTRACT**: move behind a plugin or optional module.
- **ARCHIVE**: keep in history and the archive tag, out of the active tree.
- **REMOVE CANDIDATE**: no runtime use found; needs a caller check before removal.
- **UNVERIFIED**: can't classify until it has been run.

Nothing was deleted in this milestone.

**Studio column.** How a person reaches the capability in Mesh Studio:
- **Full**: a dedicated control.
- **Behaviours tab**: the generic "+ Add behaviour" picker and its typed fields, which handle numbers, text, true/false and comma lists, but not lists of objects such as waypoints or sequence steps.
- **JSON**: edit the files by hand.
- **Legacy editor**: only the old editor (`MESH_LEGACY_EDITOR=1`).
- **Runtime-only**: no authoring at all.
- **Unreachable**: nothing can turn it on.

## A. Rendering and HD-2D

| Capability | Source | Runtime use | Studio | Tests | Evidence | Class | Recommendation |
|---|---|---|---|---|---|---|---|
| Y-sort by feet, `explicit_z` mode | `render_sort_model.py`; `scene_render_pipeline.py:149` | Every frame; `settings.render_sort_mode` (default y_sort) | Implicit (always y-sort); mode is JSON | ~65 | **LAB-FIXED** (check 9). The sort was right; batching then reordered it. | KEEP | — |
| Render batching | `render_queue.py`, `render_queue_arcade.py`; on by default (`game.py:639`) | Every frame | Runtime-only | 4 | **LAB-FIXED.** It grouped every use of a texture, so a sprite sharing a texture with one behind it was drawn behind a sprite it should cover. It now merges only neighbours. | KEEP | — |
| Culling | `culling.py`; only with batching | Every frame | Runtime-only | 3 | CODE | KEEP | — |
| `render_layer`, `depth_z` | entity keys; sort, shadow, tint, outline | When set (no shipped content sets them) | Legacy editor inspector | in sort/shadow tests | CODE | KEEP | Expose in Studio's Look tab (gap 3). |
| Sprite shadows (blob, contact, AO) | `sprite_shadow_model.py` | On by default for every sprite | Legacy editor HD-2D panel (enable flags only) | 89 | **LAB-FIXED.** Shadows were anchored 4 px below the sprite's *centre*, so any opaque sprite taller than that hid its own. They now sit at the feet, like y-sort: under-sprite brightness 69 vs floor 108. | KEEP | Expose scale, alpha and offset (gap 3). |
| Depth tint | `depth_tint_model.py` | Off by default; no content uses it | Legacy HD-2D panel | 50 | TESTS / UNVERIFIED | KEEP | Run in the lab next (needs `render_layer`/`depth_z` content). |
| Outlines ("rim light") | now `engine/sprite_outline_model.py` (moved this milestone) | Off by default | Legacy HD-2D panel | 5 + golden | TESTS / UNVERIFIED | KEEP | Moved out of `engine/editor/` (see consolidation plan). |
| Parallax: `background_layers` / `foreground_layers` | `background_layers.py`; `rendering.py:23,108` | Scene keys; `scenes/parallax_demo.json` | JSON; CLI `mesh scene backgrounds` | 35 | **LAB** (check 8): parallax 0.5 moved the stripe 220.5 px for a 441 px camera move (expected 220.4). | KEEP | Studio UI (gap 2). |
| Parallax: `background_planes` | `parallax_model.py`; drawn at `rendering.py:66` | Only planes added live in the legacy editor | Legacy editor | 64 | **BROKEN from files:** the scene schema rejects the key ("'background_planes' was unexpected"); reproduced in the lab. `tint` is parsed, never applied. | CONSOLIDATE | Into `background_layers`. |
| Camera follow, deadzone, bounds | `camera_controller.py`, `CameraFollow` behaviour | Every template's player | Behaviours tab (CameraFollow) | 16+ | **LAB** (all rooms; parallax and audio checks depend on it) | KEEP | — |
| Camera zoom and camera areas | `settings.camera.zoom` / `areas` | No shipped content uses them | JSON | partial | **LAB** (check 7): walking into a 200×128 area eased zoom from 1.0 to 1.8. | KEEP | Studio UI (gap 4). |
| Camera shake / trauma | `camera_controller.py:1039,1056` | Console only; no gameplay calls it | Runtime-only (console) | 4 | CODE / UNVERIFIED in play | REFACTOR | Expose it as a sequence step or an event action. |
| Tilemap batching | `tilemap_batch*.py` | On by default | Runtime-only | 6 | LAB (indirectly: every room's map) | KEEP | — |
| Post-processing (vignette, colour grading, fade, CRT) | `post_processing.py` | The pipeline is created empty; no code adds effects | Unreachable | 34 | TESTS only; **unreachable** | UNVERIFIED | Wire it to one scene setting and run it, or archive it. Don't delete it unexamined. |
| HD-2D look presets, overrides, previews | `engine/editor/hd2d/*`, `hd2d_settings_panel_overlay.py` | Legacy editor | Legacy editor | ~390 | TESTS | KEEP (with legacy) | **Protect** before retiring the legacy editor: port the presets to Studio. |
| Scene-change fade | `TransitionFadeOverlay`; `scene_fade_enabled` (default off) | Opt-in | JSON | some | CODE | KEEP | — |

## B. Lighting and atmosphere

| Capability | Source | Runtime use | Studio | Tests | Evidence | Class | Recommendation |
|---|---|---|---|---|---|---|---|
| Lighting on/off | config `lighting_enabled` (new projects: off) | Project-wide | Runtime-only (no switch) | many | LAB | KEEP | Per-room switch (gap 1). Scene `settings.lighting_enabled` is **not read** (CODE), although the docstring and demo scenes use it. |
| Static coloured point lights | top-level `lights` → `configure_scene_lights` | `lighting_showcase.json` | JSON; legacy editor | many | **LAB-FIXED** (check 1). The glow was drawn at its world coordinates *as screen coordinates*, ignoring the camera: in any room not at the screen's origin, lights lit the wrong place, while their shadows lined up correctly. Lights are now drawn through the world camera (scroll and zoom). | KEEP | Studio lights tool (gap 1). |
| Flicker (static and dynamic) | `flicker.py` | When set | JSON / Behaviours tab | yes | **LAB** (check 1): brightness near the light's edge varied between 28 and 50 over 1.2 s, while the centre held at 99. Flicker mostly changes reach, little at the centre. | KEEP | The documented nested `"flicker": {…}` form is not read (CODE). |
| Dynamic light on an object (`LightSource`) | `light_source.py` → `register_dynamic_light` | Demo scenes | Behaviours tab | yes | **LAB-FIXED** (check 3). Lights were never unregistered: every room load left the old one behind, frozen where its object was, shining into later rooms (screenshot evidence). The scene now drops them on load; the torch light tracked its NPC within 12 px. | KEEP | — |
| Ambient darkness and tint | config `lighting_ambient_color`, `ambient_light_rgba`; scene `settings.ambient_light_rgba` | Every lit room | JSON | yes | **LAB-FIXED, two bugs.** (1) `DayNightCycle` applied its 21:00 colour at start-up even when switched off, so a project's `lighting_ambient_color` was never seen (the lab measured ambient [58,41,46] instead of [255,255,255]). (2) A room's tint stayed on in the next room. Both fixed with tests. | REFACTOR | A room can only darken the project's base. Scene `lighting_ambient_color` and `ambient_darkness_alpha` aren't read at load (CODE). One clear ambient model is needed (consolidation plan). |
| Hard shadows from occluders | `shadow_pipeline.py`; scene `occluders` (rect/poly), auto-built from collision tiles | When lighting is on (default mode "hard") | JSON; legacy editor | many | **LAB** (check 2): behind a pillar 10–13 vs 33–43 at the same distance in the open. | KEEP | Only **one** light casts shadows (CODE). Shadow polygons ignore camera zoom (CODE): at zoom ≠ 1 they may not line up with the (now zoom-aware) light glow. UNVERIFIED; lab next. |
| Soft shadows | `end_hard_shadows_composite` | Nothing calls it | Unreachable | 7 | CODE: **unreachable** | UNVERIFIED | Decide: wire it as a shadow mode, or archive it. |
| Light cookies | `cookies.py` | `cookie_id` goes straight to `load_texture` | Legacy editor presets | yes | CODE: preset ids (`torch`, `window`) aren't paths and wouldn't load. The cookie offset uses the camera's *centre*, the shadows its corner. UNVERIFIED. | REFACTOR | Fix the presets and offset; run it in the lab. |
| Light shafts (god rays) | `shafts.py`, `light_shafts.py` | When `shafts_enabled` | Behaviours tab (LightSource) | yes | CODE / UNVERIFIED | KEEP | Lab next. |
| `ToggleSceneLights` | behaviour | Event-driven | Behaviours tab | yes | CODE / UNVERIFIED | KEEP | — |
| `occluder_poly` on an entity | `occluders.py:235` | Converted once at load | JSON | yes | CODE: doesn't follow a moving object | KEEP | — |
| Shadow-mask polygon lights | `MESH_SHADOWCAST_MASK=1` | Debug only | Runtime-only | yes | CODE | KEEP (debug) | — |
| `lighting_plan` / `lighting_render` / `lighting_cache` | exported | Only the debug bundle | — | yes | CODE | REMOVE CANDIDATE | Check debug-bundle callers first. |
| Legacy `Particle` class | `particles.py:63` | Never instantiated | — | — | CODE | REMOVE CANDIDATE | — |
| Day/night cycle | `day_night.py`; config and scene keys | Off by default | JSON | ~8 | **LAB-FIXED** (start-up override above). Otherwise CODE. | REFACTOR | `apply_scene_settings` returns early on a named `background_color`, skipping the day/night keys and `initial_spawn` (CODE). |
| Fog | `fog_overlay.py` (flat tinted overlay with noise) | Toggled from the pause menu | Runtime-only | 5 | CODE: scene `fog_enabled` is always overridden by runtime settings | REFACTOR | Let the scene's value win when it is set. |
| Particles | `particles.py`, `ParticleEmitter`, `fx_presets.py` | Hit, collect and death bursts; emitters | Behaviours tab, but **no fields shown** (no `config_fields`) | ~25 | **LAB** (check 10): an emitter kept 13–15 live particles. | KEEP | Declare its fields so Studio can edit it (gap 5). |
| Positional sound | `audio.play_sound_at` / `play_world_sfx` (listener = camera centre) | Combat, Hitbox, Projectile | Runtime-only | ~77 | **LAB** (check 11): the same hit at 900 px played at volume 0.0, at 284 px at 0.41 with pan 0.32. | KEEP | Shooter's own fire sound is flat (`play_sound`). The occlusion ("muffled") path is never triggered: no scene controller method exists (CODE). |
| Music, crossfade | `settings.music`, `transition_music` | Scenes | JSON | yes | CODE | KEEP | Studio room setting (gap 6). |

## C. Navigation and AI

| Capability | Source | Runtime use | Studio | Tests | Evidence | Class | Recommendation |
|---|---|---|---|---|---|---|---|
| A* pathfinding over a nav grid | `engine/pathfinding/*`, `scene_navigation_controller.py` | Behaviours via `get_nav_grid()` | — | ~40 | **LAB** (check 4): FollowPath walked around a 9-tile wall to its goal, never inside the wall. | KEEP | The grid comes only from tilemap collision tiles: **solid objects are invisible to pathfinding** (CODE). No map, no grid: FollowPath, ChaseTarget, Wander and Flee then do nothing. |
| Line of sight | `los.py` (Bresenham over the grid) | ChaseTarget, PatrolChase | Behaviours tab (`los_required`) | yes | **LAB** (check 5): the chaser with sight moved; the identical one behind the wall stayed. | KEEP | Checked only when acquiring a target (CODE). Interactable's `require_line_of_sight` is stored, never read (CODE). |
| FollowPath, ChaseTarget, PatrolChase | behaviours | Demo scenes | Behaviours tab | yes | LAB (FollowPath, ChaseTarget) | KEEP | The validator warns "missing required params: goal_x, goal_y" for FollowPath whose settings are in `behaviour_config` (Studio's own form) even though it works: a false warning (lab log). |
| PatrolPath | behaviour | Sentry prefabs | Behaviours tab (waypoints not editable) | yes | **LAB** (check 3's torchbearer walked its ping-pong route) | KEEP | — |
| Patrol, FollowTarget | `patrol.py`, `follow.py` | `cellar.json`, `showcase_dungeon.json` | Behaviours tab | new | **FIXED (tests), not lab-run.** Both handed the mover a speed plus `dt`; the mover adds what it's given and ignores `dt`, so they moved `speed` px per frame. This is the same defect the lab caught in SequencePlayer. | CONSOLIDATE | Patrol vs PatrolPath and FollowTarget vs FollowPath overlap. |
| Wander, FleeFromTarget | behaviours (A*) | — | Behaviours tab | mocks only | CODE / UNVERIFIED | KEEP | — |
| NpcSchedule | drives a sibling Patrol | town prefabs | Behaviours tab | 4 | CODE: may miss its Patrol depending on build order | UNVERIFIED | — |
| EnemyAI | `enemy_ai.py` | 15 enemy prefabs | Behaviours tab | 4 | CODE: moves only once per repath interval (~1/12 speed) | UNVERIFIED | Run in the lab next; likely the same class of bug. |
| RangedEnemyAI + Shooter + Projectile | behaviours | Sentry prefabs | Behaviours tab | yes | **LAB-FIXED** (check 11). Projectiles moved `speed` px *per frame* (300 px/s became 18,000 px/s): they were measured 20,000 px off the map and never hit. Now 300 px/s; hits land. | KEEP | — |
| RangedAttackAI | `ranged_attack_ai.py` | No scene | Behaviours tab | 3 | CODE: reads `window.current_scene.entities`, set nowhere: **inert** | REMOVE CANDIDATE | Or fix it if RangedEnemyAI doesn't cover it. |
| Player movement and collision | `PlayerController` + `physics_runtime` | Every player | Collider handles (M5) | ~54 | M5 | KEEP | — |
| NPC collision | `move_entity_with_collision` | All NPC movers | — | yes | CODE: ignores `components.collider` (players honour it) | REFACTOR | One collider model for players and NPCs. |

## D. Events and scripting

| Capability | Source | Runtime use | Studio | Tests | Evidence | Class | Recommendation |
|---|---|---|---|---|---|---|---|
| Event bus → `on_event` | `MeshEventBus`, `emit_signal` | The live path for every event | — | many | **LAB** (check 6: a sequence's `signal` started a Dialogue) and M5/M6 | KEEP | — |
| `GameplayEventBus` | `gameplay_event_bus.py` | **Never assigned in the game** (only `mesh_cli/episode.py`) | — | yes | CODE: subscribers get nothing live (QuestHook, HUD history) | CONSOLIDATE | One bus (consolidation plan). |
| Flags, counters, variables | `GameState`, `state_runtime/*` | Everywhere | Full (Conditions, zones, choices; M5) | many | M5/M6, LAB (save/load) | KEEP | — |
| Trigger zones, show-when, conditional objects | Studio zones; `SetGameStateOnEvent`, `ConditionalActivator` | Studio projects | Full (M5) | 42+ | M5 (17/17), M6 | KEEP | — |
| Dialogue (lines, graph, choices, conditions) | `dialogue.py` | 8+ scenes, every Studio NPC | Full (M5) | ~31 files | M5, M6, LAB | KEEP | `_has_played` is not saved (CODE). |
| SequencePlayer (move, wait, signal, dialogue, wait_for_event) | `sequence_player.py` | **No shipped content** | Behaviours tab (steps not editable) | new + 2 | **LAB-FIXED** (check 6). `move_to` moved `speed` px per frame, overshot, swung round its target forever and never reached the next step. Now: moved 96 px, waited, then the dialogue opened. | KEEP | Its progress is not saved (CODE). This is the per-object timeline to build on. |
| CutsceneController (global; camera focus/pan) | `cutscene_controller.py`, `cutscenes.json` | Live; `CutsceneTrigger` | JSON | 4 | CODE / UNVERIFIED | CONSOLIDATE | Merge with SequencePlayer (plan). |
| CutsceneRunner (branching, deterministic) | `cutscene_runtime/` | CLI and tests only | — | 14 | CODE | CONSOLIDATE | Different format ("commands" vs "steps"). |
| ActionListRunner | `action_list_runner.py` | Configured in 11 episode/puzzle scenes | — | 27 | CODE: no `on_event`, nothing calls `handle_event` in the game: **appears inert** | CONSOLIDATE | Overlaps SetGameStateOnEvent / EmitEventOnEvent. |
| EmitEventOnEvent, ListenForEvent, IncrementCounterOnEvent | behaviours | Some scenes | Behaviours tab | yes | CODE | KEEP | `SetGameStateOnEvent` also subscribes directly: possible double-fire (CODE, unclear). |
| Timer | `timer.py` | Puzzle prefabs | Behaviours tab | 5 | CODE | KEEP | — |
| TimeOfDayGate | behaviour | Town prefabs | Behaviours tab | 4 | CODE | KEEP | — |
| DialogueRunner (headless node machine) | `dialogue_runner.py` | Started by ActionListRunner / cutscenes; **no UI** | — | 17 | CODE | CONSOLIDATE | Into Dialogue. |
| Persistent event state across save/load | `saveable` protocol (12 behaviours) | F5/F9, slots | — | ~400 save tests | LAB (positions, NPC state) | REFACTOR | Not saved: SequencePlayer progress, the active cutscene, Dialogue `_has_played`, `once`/`_consumed` flags (CODE). |

## E. Gameplay foundations

| Capability | Source | Runtime use | Studio | Tests | Evidence | Class | Recommendation |
|---|---|---|---|---|---|---|---|
| Inventory, items | `inventory.py`, `assets/data/items.json` | Game state | Runtime-only (legacy item editor) | ~77 | CODE | KEEP | `InventoryHolder` behaviour: used nowhere (REMOVE CANDIDATE after caller check). |
| Shops | `Vendor` (gold counter) | 5 scenes | Behaviours tab | shared | CODE | KEEP | — |
| Drops, collectibles, chests | `DropTable`, `PickupCollectible`, `Collectible`, `RewardChest` | Many scenes | Behaviours tab | ~28 | CODE | CONSOLIDATE | Collectible vs PickupCollectible. `RewardChest.looted` is not saved. |
| Health, damage, death | `Health`, `combat_model` | Combat | Behaviours tab | ~26 | LAB (dummy took projectile hits) | KEEP | No invulnerability timer. |
| Melee (`Combat` → `Hitbox`) | behaviours | Combat demos | Behaviours tab | yes | CODE | KEEP | — |
| DamageOnTouch | behaviour | No scene | Behaviours tab | 0 | CODE: **doesn't reduce HP** (only logs and emits) | REFACTOR | Route it through `apply_damage`. |
| Knockback | — | — | — | — | None exists | — | — |
| Experience, drop tables | `GrantExperience`, `DropTable` | legacy `died` event | Behaviours tab | yes | CODE | KEEP | — |
| Quests and journal | canonical `engine/quests.py` QuestManager; HUD journal | `assets/data/quests.json` (139) | Legacy quest editor | ~15 files | CODE | CONSOLIDATE | Legacy `quest_manager.py` is still constructed and replaced; QuestRunner is CLI-only; QuestHook is inert (wrong bus). Task #128. |
| Save / load | `SaveManager` slots (F5/F9, pause menu) | Live | Runtime-only | ~400 | **LAB** (check 12): after F5, walking away and F9, the player (128,128) and the chasing NPC (159.5,112) were both back exactly | CONSOLIDATE | `SaveGameV1` (F6, stale) and the quick snapshot still exist. **No per-object state survives a room change** (CODE): only flags and counters do. |
| Prefabs | `prefabs.py` (`prefab_id` reference); Studio copies | Everywhere | Full (place prefab; a copy) | ~93 | **LAB**: a `prefab_id` reference and a Studio copy both spawned | CONSOLIDATE | Two models: a linked reference vs a deep copy. A reference's `mesh_name` doesn't show in the dump/spawn log (minor). |
| Rooms, doors, transitions | `SceneTransition`, `WorldController` | 122 files | Full (M2–M4) | many | **LAB** (door between rooms) and M2–M4 | KEEP | `SceneExit` overlaps (CONSOLIDATE). |

## F. Tools and extensibility

| Capability | Source | Studio | Tests | Evidence | Class | Recommendation |
|---|---|---|---|---|---|---|
| Plugins / mods | `plugin_system.py`; loads `<project>/mods/<id>/mod.json` | — | 3 | **LAB**: a plugin in the *project's* `mods/` registered a custom behaviour (`LabSpinner`) that ran in play. Correction: the salvage audit said mods load only from the engine repo. They load from the folder the game runs in (`find_repo_root` stops at the project's `config.json`). | KEEP | Document it. Whether Studio's behaviour picker lists a plugin's behaviours is UNVERIFIED (plugins load when the window starts, so probably). |
| Custom behaviours | registry + `@register_behaviour` | Behaviours tab | many | LAB (via plugin) | KEEP | `mesh new-behaviour` writes into `engine/behaviours/`, not the project (CODE). |
| Asset index / browser | `content_index.py`, `asset_index.py`, `tooling/asset_manifest.py` | Studio has its own picker | some | CODE | CONSOLIDATE | — |
| Hot reload | `asset_hot_reload_watcher.py` (`MESH_HOT_RELOAD=1`) | — | some | CODE | KEEP | — |
| Safe asset rename/move with reference updates | `engine/editor/asset_ops/` (~2.2k lines) | Legacy editor only | 7 | CODE | **PROTECT** | Port before retiring the legacy editor. |
| Animation | (1) `Animator` (Studio, top-left frames); (2) `AnimationFactory` (templates, content, bottom-left frames, blend, events, root motion) | (1) Full (M5/M6); (2) runtime | ~130 | M5/M6 for (1); CODE for (2) | CONSOLIDATE | Highest-risk overlap (consolidation plan). |
| Validation | `schema_validation.py`, `schemas/*.json`, CLI validators | Studio validates every edit (M6) | 18 | M6 | KEEP | Fix the FollowPath false warning. |
| RPG Maker import | `rmmz_passability.py` (passability only) | — | 1 file | CODE; its 2 tests are baseline failures (missing fixtures) | KEEP | — |
| Input and gamepad | bindings, `input_controller.py`, capture router | — | 35 | M1–M6 (keyboard) | REFACTOR | Two hotkey systems shadow each other (known collision pattern). |
| Diagnostics, profiling | `perf.py`, F10 inspector, `mesh dump-state`, `diagnostics.py` | — | yes | CODE | KEEP | — |
| Runtime probe (new) | `engine/runtime_probe.py`; in Studio's play dump | — | via lab | LAB | KEEP | Read-only snapshot of lighting, particles, camera and recent positional sounds, for verification harnesses. |
| AI authoring | `authoring.py` + MCP + `mesh author` | Full (AI panel, M6) | many | M6 (14/14) | KEEP | ~23 older `AIOps` MCP tools are a second write surface (CONSOLIDATE). |

## Other subsystems

| Subsystem | Evidence | Class | Note |
|---|---|---|---|
| Monster game (`engine/monster/`, ~5.7k lines) | M0–M2 era runs; CODE | EXTRACT | Plugin later. Generic combat and AI do not depend on it (CODE: neither imports the other). |
| Legacy editor (`engine/editor/`, ~58.7k lines) and Creator Mode | CODE | ARCHIVE after porting what's listed under "protect" | — |
| Localization (`i18n.py`, `locales/en.json`) | CODE | KEEP | Mostly editor strings. |
| Replay and determinism (`rng_service.py`, replays) | CODE | KEEP | Behaviours don't use `rng_service` (DropTable has its own RNG). |
| Web export (pygbag), packaging (`MeshGame.spec`, `build_game.py`) | CODE | UNVERIFIED | Not run this milestone. |
| Episode/campaign runners, golden-slice worlds | CODE | ARCHIVE | Demo content; the only live users of CutsceneRunner, QuestRunner and GameplayEventBus. |
| Accessibility | CODE: only scattered hits | UNVERIFIED | Nothing found that could be called a feature. |

## 2.5D: height

**Not implemented.** This is from a code search (CODE), not a missing lab check: there is nothing to run.
- No elevation or height coordinate on entities.
- No height-aware collision.
- No bridges, stairs, ramps or multiple floors.
- Every `z` key is a draw-order layer. `depth_z` changes only sort order and visuals (shadow offset, tint, outline alpha). RPG Maker passability import has no star/bridge flags.
- The only documentation is one line in `docs/mesh_scene_spec.md:119` calling `explicit_z` "for HD-2D / 2.5D games with manual depth control".

**What exists that a height system would build on:** feet-based y-sort, `render_layer`/`depth_z`, feet-anchored shadows (this milestone), per-tile collision layers and the nav grid.

**What it would need:**
- an entity height and a ground-height map;
- collision and pathfinding per floor;
- draw-order rules for bridges (over and under).

That is a new subsystem, deliberately not started here.

## What can Mesh do today (short answer)

**Verified in the running engine** (lab plus M1–M6):
- **Building rooms:** rooms joined by doors; painted maps with collision.
- **Objects and conversation:** prefabs, both linked and copied; dialogue with choices and conditions; flags, trigger zones and show-when rules.
- **Pictures:** animation with Studio's Animator.
- **Movement and AI:** A* pathing around walls; line-of-sight-gated chasing; patrols.
- **Scripted sequences:** move, wait, then talk.
- **Lighting:**
  - coloured flickering static lights;
  - lights carried by moving objects;
  - hard shadows behind occluders;
  - ambient darkness per room.
- **Rendering:**
  - y-sorted draw order, correct with shared textures;
  - feet shadows;
  - parallax backgrounds.
- **Camera:** follow, plus zoom areas.
- **Effects and sound:** particles; positional sound by distance and pan.
- **Combat:** projectiles that hit and damage.
- **Saving:** save and load that restores positions.
- **Extending:** plugins that add behaviours from a project's `mods/`.
- **AI co-authoring:** reviewed proposals in Studio.

Several of these work only since this milestone: the lab found eight engine bugs on these paths, fixed at their source with regression tests (rows marked LAB-FIXED; the list is in the lab report).
