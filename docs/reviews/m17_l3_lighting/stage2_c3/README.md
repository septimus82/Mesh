# M17-L3 Stage 2, C3: Studio's lighting controls in HD-2D rooms (validation evidence; never merged)

**Implementation:** branch `feature/m17-l3-c3`, commit `865e594`, on `redesign/visual-editor` `6f9f4c8` (C1 and C2
merged).

**Base for comparison:** `D:\Games\Mesh-l3c` at `089cbfe`, whose tree is identical to `6f9f4c8`.

**Scenes:** template projects in scratch folders. The HD-2D template's village is set to the night sun. It has:
- the sky light (the room light's colour) and the two lamp posts' lamps (shadow maps);
- three added lamps: Light 4 past the two maps; Light 5 past the maps, with a 2D torch flicker; Light 6 switched
  off;
- three 2D room settings HD-2D never reads (`lighting_enabled: false`, a Cave room light, shadow quality high).

A 2D room ("Cellar") is created in the same project for the 2D checks. Lakeside Village, its backup and the dirty
checkout are untouched.

## How the audit was measured (`scripts/audit.py`, `data/audit_base.json`, `data/audit_branch.json`)

Studio runs in a hidden window, driven by window input events. With each light chosen in turn (a shadow-map lamp,
a lamp past the maps, the flickering lamp past the maps, the room light colour) and each expander open, the script
clicks every button the panel shows and types into every box. For each edit it records:
- the scene keys written;
- whether the HD-2D renderer's inputs changed: its settings (shadows, softness, strength, lamps, ambient colour),
  and its lighting (shadows enabled, filter, lamp shadow slots);
- whether C2's shadow allocation changed;
- that Ctrl+Z restores both.

A click that writes nothing is recorded as the highlighted current choice (or not).

The same script runs on the base and on the branch (`data/audit_summary.txt`).

| | Base `6f9f4c8` | Branch |
|---|---|---|
| HD-2D lighting controls shown (buttons and boxes, over the four lights) | 51 | 26 |
| Edits that change nothing the renderer draws (inert) | **33** | **0** |
| Edits that change only C2's allocation (who gets the next free map) | 2 | 1 (documented below) |
| 2D room: panel (buttons, labels, boxes) and every edit's written keys and message | — | **identical to base** |

## Before / after, control by control

"Reads" means the HD-2D renderer reads it: `engine/hd2d/settings.py` `parse_hd2d` / `parse_scene_lights`, and
`engine/hd2d/lighting.py`.

| # | Studio control | Writes | HD-2D reads? | Base, in an HD-2D room | Decision | Branch, in an HD-2D room |
|---|---|---|---|---|---|---|
| 1 | Lighting On / Off / As project | `lighting_enabled` | No: its lamps are always lit | **Inert** | Hide. A room-wide lamp switch would be a new renderer feature. | Gone. The panel says the lights are always lit and each light has its own On. Named under "Not in HD-2D rooms"; the room's value is kept. |
| 2 | Status line ("On: dark away from lights" / "Off: everything is fully lit") | reads the 2D lighting's state | — | **Wrong** for HD-2D | Adapt | HD-2D wording: lights always lit; daylight and ambient are Environment > Sun and sky's. |
| 3 | Room light presets (Day…Black), Darker, Brighter, Project's | `lighting_ambient_color` | No. Ambient is Sun and sky's Ambient light, tinted by the room-light entry's colour. | **Inert** | Hide; point to the existing control | Gone. Points to Environment > Sun and sky. The value is kept. |
| 4 | Shadows on / off / Project's | `lighting_shadows_mode` | No. HD-2D reads `settings.hd2d.shadows`. | **Inert** | **Adapt**: the renderer already has this switch | "Shadows on" / "Shadows off" write `settings.hd2d.shadows` (`project_ops.set_hd2d_shadows`): off draws no sun or lamp shadows. No "Project's": HD-2D has no project default. |
| 5 | Shadow edges Sharp / Soft / Softer | `lighting_shadow_softness` | Yes: PCF 0 / 1 / 2 (lamps cap at 3×3) | Works. Its highlight followed the project's default, while HD-2D reads "sharp" when unset. | Keep | The highlight is what the renderer uses. "Softer: the sun's shadows broader still; lamps' as Soft." |
| 6 | Fine-tune: Edge width | `lighting_shadow_edge` | No | **Inert** | Hide. A variable filter width would be a new feature. | Gone, named, value kept. |
| 7 | Fine-tune: Strength | `lighting_shadow_strength` | Yes | Works | Keep | Shown directly under the edges: Fine-tune would hold only this. |
| 8 | Fine-tune: Quality | `lighting_shadow_quality` | No: HD-2D's filter is fixed | **Inert** | Hide | Gone, named, value kept. |
| 9 | Fine-tune: Characters cast shadows | `lighting_character_shadows` | No. Characters always cast sun shadows and never lamp shadows. | **Inert** | Hide. Mapping it to sun shadows would change its meaning and the renderer. | Gone, named ("characters' lamp shadows"), value kept. The panel says characters cast the sun's shadows only. |
| 10 | Per light: colour, size, X, Y, Height, On, Colour (R, G, B) | light fields | Yes | Works for lamps | Keep | Unchanged. |
| 11 | Per light: Casts shadows | `shadows` | The first two lamps that ask (C2) | Works for the first two; past them it changes only the allocation, with C2's note | Keep. Add: room shadows off. | As before. With the room's shadows off, the summary reads "Shadows are off in this room: every light shines through walls." The note says why, and no row says "- shadows". Its message no longer claims "Walls block it." |
| 12 | Per light: Flicker presets, Calmer / Livelier, custom flicker boxes | `flicker_*` | No: HD-2D room lamps shine steadily (only campfires flicker) | **Inert** (10 controls) | Hide. Animated lamps would be a new renderer feature. | Gone. "Flicker: none in HD-2D rooms, lamps shine steadily." A flickering light: "This light keeps its torch flicker for 2D." |
| 13 | Lights list: the room light's colour entry | — | Colour only (ambient tint) | "Light 1: custom, size 0". Its inspector offered size, X, Y, height, shadows, flicker and duplicate: **inert** | Adapt | "Light 1: room light colour (custom)". Its inspector: colour, On, Delete, Colour (R, G, B), and what it does. |
| 14 | Panel text "Walls on the map block each light…" | — | — | 2D occluder wording | Adapt | "The room's structures block the sun and each lamp that has a shadow map; characters cast the sun's shadows only." |
| 15 | *(missing)* lamp intensity | `intensity` | Yes (`u_light_col` = colour × intensity) | No control | **Expose** | Dimmer / "brightness 1.6x" / Brighter (×0.8 / ×1.25, from 0.05 to 10; Brighter disabled at 10). "Brightness (0-10)" box under More settings, validated by `project_ops.set_light` (a number from 0 to 10, else refused with a message). At 0, a warning, saying when it still holds a shadow map. |
| 16 | + Add light (placing one) | | | In an HD-2D room it also wrote `lighting_enabled: true` (and a Night room light when there was none) and said "lighting turned on" | Fix | It places the light only. |

**Deliberately unsupported in HD-2D:** rows 1, 3, 6, 8, 9 and 12. Each would need a new rendering feature:
- a room-wide lamp switch;
- a 2D-style ambient colour separate from Sun and sky;
- a variable shadow-filter width;
- quality levels;
- character lamp shadows, or a character sun-shadow switch;
- animated lamp flicker.

They are hidden in HD-2D rooms, named in one line ("Not in HD-2D rooms: …"), and the values a room already has are
listed there as kept for 2D, and never removed (`engine.hd2d.settings.IGNORED_ROOM_SETTINGS`).

**The one edit that draws nothing new:** "Casts shadows" on a lamp already past the two maps. Its note (C2) says it
shines through walls. Switching it changes which lamp gets the next free map, so it stays, as approved in C2.

**A switched-off light's settings** (including brightness) are kept for when it is on. Its row says "- off", and
nothing is drawn. That is unchanged and tested.

## AI tools (MCP `list_lights`)

In an HD-2D room:
- each row has `intensity` and `hd2d_ignored` (`["flicker"]` for a flickering light);
- `hd2d_shadow` uses the same `scene_shadow_allocation` as Studio, so it reads `room_shadows_off` when the room's
  shadows are off;
- the result has `hd2d_room_shadows` and `hd2d_ignored_settings` (the room's kept 2D keys).

A 2D room's listing is unchanged (tested). The `update_light` summary says HD-2D reads intensity and elevation, not
flicker.

## Real GPU frames (`sheet_c3_brightness.png`, `sheet_c3_shadows.png`, `frames/`)

**Light 4 (past the two maps)** at night, the 3D view from Studio's hidden window:

| Light 4 | Pool region mean | Whole view mean |
|---|---|---|
| switched off | 25.661 | 30.006 |
| brightness 0 | 25.661 (byte-identical to switched off) | 30.006 |
| brightness 1 (default) | 25.840 | 30.031 |
| brightness 3 | 26.237 | 30.086 |

**Light 2 (a shadow map's lamp, 1.6 in the template):** Brighter → 2.0, Dimmer → 1.28. Each brightens or dims the
frame (`tests/test_hd2d_lighting_controls_gpu.py`).

**Shadows off:** the frame changes over the whole lit area. Ctrl+Z gives a byte-identical frame to before, and
Ctrl+Y gives the shadowless frame again.

## Tests (Windows, RTX 4070, Python 3.13, scratch APPDATA, XDG and Mesh folders)

- **Full default suite** (`-W error`, no `MESH_GL_SMOKE`): **11,067 passed**, 374 skipped, 2 failed. Both are
  `test_ci_shards_plugin`: this machine's pytest 8.4.2 lacks `subtests` (environmental; the same on the C1/C2 and L2
  baselines). `data/full_suite_tail.log`.
- **GPU** (`MESH_GL_SMOKE=1`, per file): **233 passed in 35 files** (`data/gpu_suite.log`). The C1/C2 set, plus
  this slice's test, `test_studio_ai_write_set_gpu` and `test_room_file_ownership_gpu`.
  - Three files failed in that loop only because of its long temp-folder names (`g_test_<file name>`):
    `test_studio_room_undo_save_gpu` (2), `test_studio_ai_write_set_gpu` (1), `test_room_file_ownership_gpu` (6).
    Their projects' paths passed Windows' 260-character limit, so the saves failed.
  - With short temp folders all three pass: 2/2 four times; 1/1; 8/8.
  - The base `6f9f4c8` fails `test_studio_room_undo_save_gpu` the same way with the long name, so it isn't this
    change.
- **New tests:**
  - `tests/test_hd2d_lighting_controls.py`: 25, fast. Every room lighting key `set_room_lighting` writes is
    classified as read or listed-unused; each listed one changes nothing drawn; each read one, and each lamp control
    Studio shows, changes it. Also: brightness validation, `set_hd2d_shadows`, the allocation with shadows off, and
    MCP, HD-2D and 2D.
  - `tests/test_hd2d_lighting_controls_gpu.py`: 9. The generic sweep, real-frame brightness, a switched-off lamp,
    shadows on/off with undo/redo, flicker named, placing a light, a 2D room's panel, and save/reopen with the 2D
    values kept.
- **Related CPU suites:** 283 passed (project_ops lighting, Creator Mode, MCP, Studio fast tests, HD-2D lighting,
  lamp fixtures and allocation).
- **Lint and types:**
  - ruff is clean.
  - mypy (`engine`, `tooling`) shows 73 errors, the same set as the base. The two this branch first added were
    fixed in `865e594`.
  - No `# type: ignore`.

**Mutation checks** (each change reverted after):
- Fast tier:
  - dropping a key from `IGNORED_ROOM_SETTINGS`: 2 fail;
  - marking softness ignored: 3 fail;
  - ignoring room shadows off in the allocation: 1 fails;
  - `set_hd2d_shadows(True)` writing `true` instead of removing the key: 1 fails;
  - MCP using the lights-only allocation: 1 fails.
- GPU: the generic sweep, run on the base panel, flags all 33 inert controls itself (the audit above uses the same
  method).
  - GPU: placing a light switching the 2D lighting on again fails `test_placing_a_light_switches_on_no_2d_lighting`.
    HD-2D's Shadows on/off writing the 2D key instead of `settings.hd2d.shadows` fails the sweep, the shadows test
    and save/reopen (`data/gpu_mutations.log`).

**Performance:** no renderer code changed. `engine/hd2d/lighting.py` and `renderer.py` are untouched, and
`parse_hd2d` / `parse_scene_lights` read exactly as before; the new helpers are only for Studio and the AI tools.
Draws are unchanged, so no timing pass was needed.

**Screenshots:** `studio/base_*.png` and `studio/branch_*.png`: the HD-2D panel, Light 2's inspector and More
settings, the room with shadows off, and the 2D room's panel.
