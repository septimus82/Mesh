# Milestone 10: Studio lighting, animation verification and targeted cleanup

Branch `redesign/visual-editor` (draft PR #344, not merged). Five parts:
1. disk space;
2. a lighting workflow in Mesh Studio;
3. a real-window check of both animation systems;
4. the GUI driver's cursor flake;
5. the Studio inspector's type debt.

## 1. Disk space: 15.26 GB reclaimed

`build/web/` held a broken web build from 2026-03-06. Its `mesh.apk` (15,209,641,129 bytes) had swept up the repository's `artifacts/` test output, `.venv` and `tests`. It was deleted with the owner's authorisation, along with the rest of that folder (`mesh.tar.gz`, `index.html`, `favicon.png`, all from the same build).

**Checked before deleting:**
- the folder is git-ignored (`build/`) and nothing under it is tracked;
- every file in the bundle is either a repository file (in git history), test output or the virtual environment;
- `tooling/build_web.py` (pygbag, installed) rebuilds it from a clean staging copy.

**Measured:** free space on D: rose by **15,262,732,288 bytes**.

**Left alone:** `build/lib`, `build/bdist.win-amd64`, `build/version.txt`, `build/web-cache`, `mygame/`, every owner file, git history and the archive tag. No new web build was made.

## 2. Lighting in Mesh Studio

### How to use it

1. Open a room and press **Lighting** (top bar). The panel works on the current room and stays open when you switch rooms.
2. **On / Off / As project**: this room's lighting. New projects start unlit.
3. **Room light**: how light the room is away from lamps.
   - **Day**, **Dusk**, **Night**, **Cave** or **Black**.
   - **Darker** and **Brighter** step from the current light.
   - **Project's** follows the project again.
4. **Shadows on / off / Project's.** Walls painted on the map cast shadows from the first light.
5. **+ Add light**, then click the map. A light starts warm. Placing the first light in an unlit room turns its lighting on, at night light.
6. Select a light from the list or by clicking it on the map, then:
   - **Colour**: Warm, White, Cold, Red, Green or Purple.
   - **Size**: Smaller or Bigger, or drag the handle on its ring.
   - **Flicker** on or off; turning it on gives it a torch-like flicker.
   - **Duplicate** or **Delete** (the Delete key works too).
7. **Move a light** by dragging its middle. While the panel is open, map clicks work on lights only, so objects can't be dragged by mistake. **Done** closes the panel.
8. **More settings** gives exact values: X, Y, size, colour as R, G, B, and flicker amount (0–1) and speed.
9. **Undo/Redo** (Ctrl+Z / Ctrl+Y) cover every lighting change; a whole drag is one step.
10. **What you see while editing is the game's own lighting**, flicker included. F4 plays it.

### How it is built (no second lighting system)

- **Data:** the room's existing scene keys.
  - `lights`: the same point lights the engine always drew.
  - Settings: `lighting_enabled`, `lighting_shadows_mode`, and `lighting_ambient_color`.
  - A room that doesn't set one of these follows the project. Nothing is written to the project's config.
- **Edits:** validated operations in `engine/project_ops.py`:
  - `set_room_lighting`, `add_light`, `set_light`, `duplicate_light`, `remove_light`.
  - They are also listed by the authoring API, so AI clients can light rooms through the same path.
- **Studio:**
  - The panel lives in `engine/studio.py`, in the existing Studio UI patterns.
  - Light handles reuse the collider and zone drag-handle mechanism.
  - The edit view draws the room through the game's own `LightManager`.
- **Old projects:**
  - Lights keep any keys from older editors (cookies, seeds, ids).
  - Changing a light's colour drops an older `color_rgba` override that would otherwise hide the new colour.
  - Polygon occluders drawn in the legacy editor are kept and used. The panel says when a room uses them instead of its walls.

### Engine defects found and fixed on the way

| Defect | Effect | Fix |
|---|---|---|
| A room could only *tint* the project's ambient light | New projects' ambient is near-black (10, 10, 10), so no room could be made lighter | The loader honours a room's `lighting_ambient_color`, else the project's (never the last room's); the day/night clock keeps charge where it runs |
| Walls painted in Studio never cast shadows | The automatic wall occluders read only Tiled-format map files; Studio keeps a map's layers in the scene | The builder reads the scene's own collision layer |
| A wall reaching past the light's radius shaded the floor in front of it | Corners beyond the radius were projected *back* onto it, folding the shadow over the lit side; a room's border walls darkened its middle | Shadows extend past the radius and the corners, with a far middle point; one helper for both occluder kinds |
| The Studio edit view ignored lighting | No preview at all | It draws through the lighting layer and ticks flicker |
| Dragging a light crashed Studio | The collider/zone overlay assumed every drag was an object drag | Fixed |

### Limitations

- **One shadow-casting light per room:** the player's carried light, otherwise the first light. The shadow overlay darkens other lights' areas behind walls too.
- **Wall shadows also darken the wall itself** (its face towards the light), as the engine's shadows always did.
- **Occluders:**
  - Rectangle occluders are **not** in Studio. The engine treats a room's own `occluders` list as replacing its wall shadows, so a placed block would silently switch the walls off. Walls painted on the map are the occluders.
  - Polygon occluders stay in the legacy editor.
- **Not in Studio:** light cookies, light shafts, soft-shadow settings, day/night settings and colour pickers beyond the presets and the R, G, B field. These are set in JSON as before.
- **Flicker varies the light's reach, not its colour.** arcade's `Light` has no public colour to change.
- **Objects that carry a light** (the `LightSource` behaviour) are edited as behaviours in the inspector, as before. They are not in the light list.
- **Behaviour change for older Studio projects:** rooms with lighting and shadows on (the project default is hard shadows) now get shadows from their painted walls. That is the documented intent the engine never delivered.

### Evidence

Real window, `tooling/acceptance_lighting.py`, now part of the runtime gate. **15/15**, through Studio's own controls with OS mouse and keys:
- lighting on;
- Cave room light;
- a red and a cold light;
- move and resize (handles);
- flicker;
- shadows: behind the pillar measured darker than the same distance in the open, from the window's pixels in the editor and while playing;
- undo/redo;
- a second room at dusk with a green light;
- three round trips through the doors (each room keeps exactly its own lights, ambient and shadow mode; counts identical every visit);
- a drag at zoom 1.56 (40 screen px moved the light 26 world px; the glow sits on the light);
- save, close, reopen;
- Play/Stop twice leaving files and the authored lighting unchanged.

Headless tests: `tests/test_project_ops_lighting.py` (13). `tests/test_shadow_polygon_build_deterministic.py` has a regression test that fails on the old projection.

## 3. Animation playback (both systems)

**What the lab checks.** The capability lab's new **Animate** room:
- A generated sheet in which every frame is a different solid colour, so the frame on screen can be read from the window's pixels about 20 times a second.
- The player walks with **Mesh Studio's Animator**: four-direction clips authored with Studio's `character_clips`, one row per direction, top-left frame order.
- A clock plays an **AnimationFactory/AnimationPlayer** clip: the older system, with frames counted from the bottom-left.

**Results (real window, 9/9):**

| Check | Result |
|---|---|
| Animator starts idle, facing down | frame (col 0, row 0) |
| Walking right, up, left, down | each on its own row, frames 0→1→2→3→0 in order, 4.0 changes/s (clip: 4 fps), then the idle frame of that facing |
| AnimationFactory clip | bottom row, left to right, looping, 3.95 changes/s (clip: 4 fps) |
| After leaving the room and coming back | factory clip unchanged; walking left and up still correct |

**No defect found, so neither system was changed.** The opposite frame-order conventions are each implemented consistently. They remain a trap for anyone moving a clip from one system to the other (see the Milestone 7 consolidation plan); this milestone does not merge them.

## 4. GUI driver: the recurring Milestone 1 FLAKY

**Root cause:** about 3 s after a window opens, something outside Mesh recentres the cursor on the primary monitor.
- Polite mode noticed the move and waited for the mouse to be still.
- But nothing put the cursor back, so the next press landed wherever it was: (512, 384) in Milestone 9, (1280, 720) here.
- The driver only checked the target before moving.

**Fix** (`tooling/gui_driver.py`):
- **After every move**, the driver reads the real cursor position and places it directly if it landed elsewhere. It makes at most three attempts, each logged, then fails with a clear message ("could not place the cursor ... not clicking elsewhere").
- **Right before every press** it checks focus again, re-places the cursor at the last target and requires that point to be over the game window.

The run that exposed the cause failed cleanly ("point (1280,720) is not over the game window; refusing to click") instead of clicking the wrong place. With the fix, Milestone 1 passed 15/15. Runtime-gate retries are still reported as FLAKY.

## 5. Type debt: the Studio inspector

`InspectorMixin` used about 24 members of its host, Mesh Studio, that mypy could not see.

**What was done:**
- **The host interface:** declared once on the mixin under `TYPE_CHECKING`, with Studio's exact signatures. No runtime change, no ignores, no restructuring.
- **Callback types:** that exposed callbacks whose results are ignored typed as returning `None`. They are now typed as returning `object`.
- **Lambdas:** twelve single-call lambdas with default-argument capture became `functools.partial`.

| | Before | After |
|---|---|---|
| `engine/studio_inspector.py` | ~263 | **16** |
| `engine/studio.py` | 48 | 44 (the new lighting code adds none) |
| Project-wide, beyond the baseline (`tooling.mypy_gate`) | 516 | **272** |

**What remains:**
- The baseline file is unchanged.
- The remaining errors are spread out: `studio.py` 44, `monster/data_load.py` 41, `monster/battle_mode.py` 22, Creator Mode 16, the acceptance tooling and others.
- The 16 left in the inspector are lambdas that do several things, and genuine `Any` returns.

## Validation

- **Runtime gate** (`tooling/runtime_gate.py`, real window, OS input): **9/9 suites**.
  - Milestones 1–6: 15, 23, 15, 20 (`./mygame` copied, original checked unchanged), 17 and 14 steps.
  - Persistence 12/12; **lighting 15/15**; capability lab **36/36** plus 1 KNOWN (`background_planes`). The lab includes the 9 animation checks, and its other rooms passed unchanged with walls now casting shadows.
  - **Milestone 1 was FLAKY:** its first attempt stopped when something outside Mesh confined the cursor to the primary monitor. The driver refused to click and the retry passed. The driver now waits out such a confinement for up to 3 s, and Milestone 1 passed 15/15 again afterwards.
  - Evidence: [`milestone10_evidence/`](milestone10_evidence/).
- **Full default suite:** 9,373 passed, 1 failed, 8 skipped, 163 deselected.
  - The failure was `test_cli_release_bundle_command.py::TestDeterminism::test_same_seed_identical_zips`. The bundle embeds the live `git rev-parse HEAD` with a 5 s timeout, so under load one of its two builds can lack the hash.
  - It passed 8/8 alone. The test now pins that input, and the file passes 34/34.
  - Not rerun in full afterwards, per the brief.
- **Slow/e2e** (`-o addopts= -m "slow or e2e"`): 31 failed, 132 passed. Exactly the Milestone 9 known list: the `verify-all` chain, blocked by the type gate (272 errors beyond the baseline, down from 516), and the wheel test.
- **Fast gate** (`-m fast`): 4,256 passed, 1 failed: the unmarked-test ratchet caught a new regression test I hadn't marked `fast`. Marked; the ratchet and that file pass.
- **Lint and types:** the ruff gate and the mypy island are clean. Project-wide type gate: 272 beyond the unchanged baseline.
- **Owner files untouched** (newest modification July): `MESH_HANDOFF.md`, `MESH_NOW.md`, `door_field*` backups and patch, `scenes/parallax_demo.json`, `assets/parallaxes/`, `mygame/`. `user_settings.json` is unchanged.
