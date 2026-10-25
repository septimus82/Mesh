# Milestone 16 Stage 6A: the HD-2D starter kit and template candidate

**Verdict: PASS** (pending owner review; draft PR [#362](https://github.com/septimus82/Mesh/pull/362), not merged).

A developer-mode HD-2D project opens as a complete, playable and editable starter experience. `create_project(...,
"hd2d_rpg")` builds it in about 2 s. It has original assets ready to bundle, and nothing in it points outside the
project. A hidden-window run took it through the brief's ten steps using only Studio's and the game's own window
events, with no JSON and no Blender ([evidence](milestone16_stage6a_evidence/starter_check.json)).

The template stays **developer-only** (`launcher=False`). Stage 6B makes it public only after the clean-install gate
below passes.

## Part A: Stage 5B accepted

- **Imported sources are never modified.** An import writes the source's bytes in place only when the file is
  already the project's managed model and nothing would change. A sharpened or otherwise transformed import becomes a
  separate managed copy (`stairs_2`), so the creator's file is untouched. This is tested for external and
  project-local sources, both sharp and as exported.
- **Staging files are exclusive and unique.** They are made with `mkstemp` beside the target and given the target's
  mode.
  - An unrelated `.mesh-staged` file is never touched.
  - Failures at the staging, validation and replacement stages each roll back to the exact previous bytes.
  - Every write checks containment, links followed, before and after `mkdir`, so a symlink or junction at `assets/` or
    `assets/models/previews` can't redirect a write outside the project.
- **#361 merged** into `redesign/visual-editor` as **`d804e31`** (head `93af802`; the hardening is in `5577aee` and
  `93af802`).
  - Post-merge CI: the push run `40210456968` is **green on Linux and Windows**.
  - #344's pull_request run on the same commit (`40210460482`) failed one step on Windows: verify-all's `pytest-fast`
    budget, 125.4 s against a 121.8 s limit (93.7 s × 1.3). The push run on identical code passed, so this is runner
    variance. The Windows fast-tier headroom is now thin; see Risks.
- The merged 5B worktree has been removed.

## What a new HD-2D project contains

| | |
|---|---|
| **Village** (start room, 40 × 32 m) | Two 2 m plateaus (6 cliff sections) joined by a 6 m bridge you can cross or walk under; a staircase up each; a cottage whose door leads inside; a shop with an awning and a shopkeeper; two lamp posts with lamps 2.5 m up; fences, crates, barrels and earth paths; an Elder on the east plateau; a welcome sign. Sun, soft shadows, a sky-tinted ambient. A 4 m grass margin keeps the camera off the world's edge. |
| **Cottage** (second room, 16 × 12 m) | The furnished interior (table, bed), a warm lamp, Tomas to talk to, and a door back out. Dark surroundings (the new `sky` setting) instead of daylight. |
| **Characters** | The player (`starter_hero`), the Elder and Tomas (`starter_villager`), Mara (new `starter_merchant`). All walk in four directions. Each NPC has its own dialogue. |
| **Model catalogue** | The whole starter kit (14 models with previews), so the creator can place more from Models.... |
| **Objects** | Person and Sign, as in the 2D templates. |
| **Save / load** | The engine's own quick save (F5) and quick load (F9), plus the menu (Esc). |

Built with the same validated operations Studio uses (`project_ops.place_structure`, `add_light` / `set_light`,
`new_room`, `link_rooms`, `add_map`), in `engine/hd2d/starter_village.py`. Every path is project-relative. A fast test
checks every scene and catalogue file for machine paths and `tooling/` references.

## The starter kit (original, with provenance)

`assets/hd2d_starter/`: 14 models (340 KB) with previews, two ground textures, and a kit catalogue.

| Category | Models (collision) |
|---|---|
| Buildings | Cottage (walk-in doorway), Shop (counter and awning) |
| Building parts | Wall 2 m, Roof 4 × 4 m, Cottage interior |
| Terrain | Platform 4 × 4 m and 2 × 4 m (2 m cliff sections), Staircase (climbs 2 m), Bridge 6 m (deck 2 m up, walk under it), Path tile |
| Props | Fence 2 m, Crate, Barrel, Lamp post |

- **Made by Mesh's own scripts.** `tooling/hd2d_assets/build_starter_kit.py` builds every model in one headless
  Blender run, with `mesh_collision` objects. `make_starter_kit.py` writes the models, CPU previews, textures and
  catalogue.
  - Rebuilding writes the same bytes.
  - `build_cottage.py` and `build_stairs.py` became importable; their output is unchanged.
- **Textures.** `pixel_textures.py` draws every texture in code, 32 × 32 px, from fixed seeds. Eight are new: grass,
  dirt, rock, crate, barrel, iron, awning, lantern. The five existing ones are byte-identical.
- **New character art.** `tooling/make_starter_art.py` adds `starter_merchant.png` (a new palette on the starter
  body).
- **Provenance.** `assets/hd2d_starter/PROVENANCE.md` covers the kit and every other file the template uses.
  `tooling/hd2d_assets/PROVENANCE.md` and `docs/starter_art.md` are updated.
- **No unverified art.** The template doesn't ship `animated_player.png`, `sproutling.png` or `shelltide.png`.
  `ensure_starter_files` no longer adds `animated_player.png` to a project that doesn't name it; an older project that
  does still gets it, and that is tested. The 2D templates are unchanged.
- **Installing the kit.** `catalog.install_kit` adds a kit to a project's catalogue through the same staged,
  containment-checked commit as imports. Its source is recorded as `{"kit": "Mesh HD-2D starter kit 1", "sha256"}`,
  never a machine path. It refuses, writing nothing, if any of the kit's ids is already taken.

## Placing characters in 3D (the gap carried over from 5A)

In an HD-2D room, choose **Person** (or Sign, or any prefab) and click in the 3D view.

- **Finding the floor.** `World.walkable_hit` casts the mouse ray against every walkable surface and takes the nearest
  floor (ground, a platform top, the bridge deck, a stair tread). Clicking the bridge from above puts the person on
  the deck; from under it, on the ground. It is tested headlessly.
- **Feet on the spot.** A character's feet, not its sprite centre, go on the spot: the offset is read from the
  prefab's Animator frame height and the engine's `footprint`.
  - The entity gets that floor's `elevation`.
  - It is snapped to the 16 px grid if it can still stand there.
- **Refused with a reason.** A spot nobody could stand on, such as inside a fence or a wall, or under a too-low deck,
  is refused with the reason: "Nobody could stand there on the ground: something is in the way, or a floor is too low
  overhead."
- **A marker.** While an object is armed, a green box shows where it would stand.
- **One undo step.** It goes through Studio's own `place_at` and `project_ops.place_prefab`.
  - `place_prefab` gains a validated `elevation` (0–4000 px), so an AI proposal places on a floor through the same op.
  - The run used Ctrl+Z / Ctrl+Y.
- **Lamp height.** `set_light` gains `elevation` (Height) and `intensity` (Brightness), both validated. Lighting →
  More settings shows **Height (m)** in HD-2D rooms.
- **Sky colour.** HD-2D settings gain an optional `sky` colour (default: the existing blue, so existing rooms and
  goldens are unchanged).

## The ten-step workflow (hidden window, events only)

`tooling/hd2d_starter_demo.py check OUT` (pictures in [the evidence folder](milestone16_stage6a_evidence/)):

| # | Step | Result |
|---|---|---|
| 1 | Create from `hd2d_rpg` | 1,959 ms |
| 2 | Open in Studio | Village, HD-2D, 45 structures, no error ([01](milestone16_stage6a_evidence/01_studio_opened.png)) |
| 3 | Select the shop (click its roof) and drag it 1 m east | `shop` picked, x 896 → 928 px ([02](milestone16_stage6a_evidence/02_shop_moved.png)) |
| 4 | Person; click into the fence; click the west plateau | Fence click refused with the reason; the marker at (10, 24, 2.0) m; placed "on 'plateau_west_1/col_platform', 2.0 m up", standing there per `World.stand`; gone after Ctrl+Z, back after Ctrl+Y ([03](milestone16_stage6a_evidence/03_placing_person_on_plateau.png), [04](milestone16_stage6a_evidence/04_person_placed.png)) |
| 5 | Lighting → Light 2 → Cold → More settings → Height 3 | `#88bbff`, elevation 96 px; the renderer shows 2 lamps ([05](milestone16_stage6a_evidence/05_lamp_changed.png)) |
| — | An AI proposes a sign on the east plateau (`place_prefab`, `elevation: 64`); Accept | `start_sign_992_796_0_0` at elevation 64 ([06](milestone16_stage6a_evidence/06_ai_proposal.png)) |
| 6 | Ctrl+S, close, reopen | "Saved 1 file(s)."; shop, person and lamp identical after reopening |
| 7 | Play (F4) | |
| 8 | Explore | West stairs to the plateau (2.0 m, `plateau_west_3`); talked to the new person ("Hello!"); across the bridge to the east plateau; talked to the Elder; down the east stairs (0 m); **under** the bridge (ground, y 24 m); read the sign ("Mesh Village") ([07](milestone16_stage6a_evidence/07_play_on_the_west_plateau.png)–[09](milestone16_stage6a_evidence/09_play_under_the_bridge.png), [talk_elder](milestone16_stage6a_evidence/talk_elder.png)) |
| 9 | Change rooms; save / load | Through the cottage door into `cottage.json`, on `room/col_floor`; F5 at (6.4, 5.05) m, walked to 7.96, F9 back at (6.4, 5.05) ([11](milestone16_stage6a_evidence/11_play_inside_the_cottage.png)) |
| 10 | Stop (F4) | Back in Edit ([12](milestone16_stage6a_evidence/12_back_in_edit.png)); a second Play / Stop |

Each conversation recorded the interaction prompt ("E: Interact: Elder"), that the dialogue opened, the speaker, the
first line, and that it closed.

## Performance and lifecycle

Measured in the evidence run, hidden 1280 × 720 window, local Windows machine:

| What | Measured |
|---|---|
| Project creation (template, kit install, copies) | 1.96 s |
| Studio frame, Village, Edit (median of 40) | 14.0 ms |
| Game frame, Village, Play (median of 30) | 21.3 ms |
| Village render | 29 draw calls (24 static), 1,372 triangles, 2 shadow-casting lamps, sun shadows (36.7 MB shadow maps) |
| Opening Models... with the 14-model kit | 403 ms |
| Import check / import of a 15th model | 390 / 452 ms |
| Python peak (tracemalloc) during Play, room change and load | 35 MB |
| GL objects (textures / framebuffers / programs) | Edit 41 / 7 / 28. After the first Play / Stop 42 / 8 / 29, unchanged after a second Play / Stop: one-time objects, not a leak. |

## Distribution preparation (for Stage 6B)

**What a new HD-2D project copies from the engine** (measured: every file of a new project whose bytes match an
engine file):

| Engine files | Size | In #345's allow-list? |
|---|---|---|
| `assets/hd2d_starter/models/*.glb`, `previews/*.png`, `catalog.json`, `textures/{grass,dirt}.png` | 344 KB | no (new) |
| `assets/sprites/starter_hero.png`, `starter_villager.png`, `starter_sign.png`, `starter_merchant.png`, `door.png` | 7 KB | no (#345 notes the redesign's starter sprites must be added) |
| `assets/tilesets/starter.png`, `starter.json` | 5 KB | no (same note) |
| `assets/sounds/ui_open.wav`, `ui_close.wav`, `ui_click.wav`, `ui_hover.wav` | 48 KB | yes |

**Code it needs:** `engine/hd2d/*` (incl. `starter_village.py`) and `engine/studio_hd2d.py`, all inside the `engine`
package, so a wheel already carries them. No new dependency: the 3D code uses Pillow and Arcade's GL context.
Nothing in the template or `engine/hd2d` imports the repository's `tooling/` folder (#357).

**Why it is not public yet.** The template reads its files from `project_scaffold._engine_root()`, the source tree.
In a wheel install that is `site-packages`, which has no `assets/`, so the HD-2D template would fail there.
`create_project` from a source checkout works, and is what this stage tests. #345 (not merged; its tests are not
suppressed) introduces `bundled_file()` / `share/mesh-engine` for exactly this.

**The Stage 6B clean-install gate (proposed):**

1. On top of #345, add the files above to its allow-list (its wheel test then checks the allow-list exactly). Resolve
   #345's three unverified sprites, which the HD-2D template doesn't need.
2. Make `starter_village.build` and `install_kit` resolve engine files through `bundled_file()` rather than
   `_engine_root()`.
3. Extend `tests/test_wheel_bundles_engine_data.py`. In the clean venv, with `MESH_REPO_ROOT` and `PYTHONPATH`
   cleared:
   - create an `hd2d_rpg` project;
   - assert the same file inventory and the absence of machine paths;
   - load both rooms headlessly: `parse_hd2d`, `load_glb` of every model, and `World.stand` for every entity.
4. Run `tests/test_hd2d_starter_gpu.py` against that installed engine (GL-gated, hidden window).
5. Only then set `launcher=True`.

## Tests and results

| Suite | Result |
|---|---|
| `tests/test_hd2d_starter_template.py` (new, fast) | 10 passed. Developer-only; kit and Mesh-only art (no `animated_player.png`); no machine or `tooling/` paths; every character, door and arrival can stand; village contents (over and under the bridge, NPCs with their own lines, doors both ways, lamps 2.5 m up, daylight outside, dark inside, `sky` validated); 2D templates unchanged; the legacy-sheet rule; a kit never overwrites; lamp height; the click ray finds the nearest floor |
| `tests/test_hd2d_starter_gpu.py` (new, GL-gated) | 9 passed: the whole workflow's facts |
| `tests/test_one_editing_path.py` | updated for `set_light`'s new `elevation` and `intensity` (an intended API change); 5 passed |
| All GPU suites (`tests/*_gpu.py` + background layers), hidden windows | 111 passed, 1 skipped (the Stage 1 lab test, which needs NumPy). After the `sky` setting, the HD-2D GPU suites again: 46 passed, 1 skipped |
| Fast tier | 4,543 passed, 0 failed |
| Ruff gate, mypy gate, type-ignore ratchet | ok (no new `type: ignore`) |
| #359's replay goldens | untouched |

**Defects found and fixed on the way:**

- **Every NPC said Tomas's lines.** The template's Person entity shared one `behaviour_config` dict; each talker now
  gets a deep copy, and a test checks that nobody shares another's lines.
- **Dialogue never opened in the driven run.** The key was pressed and released within one update. The demo now holds
  the key across frames, as a person does.
- **The village sat on the world's edge,** so the camera showed sky past the ground. Added a 4 m grass margin.
- **The west staircase was hidden behind the cottage, with a fence in its way.** Moved it.
- **The interior showed daylight around the room.** It now has a dark `sky`.
- **Lighting's More settings, and the Height field, sat below the fold.** The Studio driver now scrolls the right
  panel to a button or field, as a person would.

## Known limitations

- **Developer-only.** It isn't in the launcher; see the 6B gate.
- **Quick load reports the save file as the current scene path** (`saves\quicksave.json`). This is the engine's
  existing quick-load behaviour; 6A doesn't touch saves, and the room, position and floor are restored correctly.
- **Studio's default 3D framing crops the village's edges** (carried over from 5A). Frame it / Reset view and WASD
  help.
- **The interior camera is close** (pitch 55°, 10 m). It follows the player, so part of the room is off-screen at
  times.
- **The kit's wall and roof modules aren't used in the village.** They are in the catalogue for creators. The cottage
  and shop are whole models, so moving one moves it as a unit.
- **Placing in 3D puts objects on floors only.** It doesn't place them on a wall or a roof (nobody can stand there).
  A structure is placed from the Models browser as in 5B.
- **No weather, particles, automatic Blender sync or cinematic effects,** per the brief.

## Risks

- **Windows `pytest-fast` budget.** The post-merge pull_request run exceeded it by 3.6 s while the push run passed.
  6A adds about 3 s of fast tests (the module creates one project). If #362's CI trips it, it will need re-baselining, an owner decision under the
  per-platform budget policy. I haven't changed the budgets.
- **Distribution** (above): the template must not reach the launcher before the 6B gate.

## Stopping point

Stage 6A is complete for review on `feature/m16-stage6a-hd2d-starter` (draft #362, not merged). Stage 6B is not
started. #356, #357 and #345 are tracked separately and untouched. `main` is untouched and #344 stays a draft.
