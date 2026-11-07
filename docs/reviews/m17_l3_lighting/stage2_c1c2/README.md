# M17-L3 Stage 2, slice 1: C1 fixture reach and C2 shadow-allocation visibility (validation evidence; never merged)

**Implementation:** branch `feature/m17-l3-c1c2`, commit `089cbfe`, on `redesign/visual-editor` `18520c3`.

**Scenes:** the Stage 1 scratch copy of the installed L1b Lakeside Village (the installed project and its backup
are untouched), plus template projects in scratch folders.

## C1: a lamp's own fixture within 0.15 m

**Rule:** a structure is a lamp's own fixture when one of its drawn part boxes is within 0.15 m of the light and
the model is at most 1 m across. Before, the light had to be inside a part box.

This is the Stage 1 prototype rule exactly (`lighting.lamp_fixtures`), and the same skip set feeds the CPU twin.

**Correctly placed lamps are unchanged.** All 36 Stage 1 baseline frames are byte-identical with the
implementation: Lakeside's two scenes, the village and the cottage; noon, evening and night; lamps as authored,
lamp shadows off, room shadows off (`data/stage1_baselines_vs_impl.json`).

**Offset lamps** (the village's west lamp, `data/offsets_summary.json`, the scene's own shaders against CPU rays):

| Light | Before: fixture / pool energy | After: fixture / pool energy | False shadow / leak |
|---|---|---|---|
| centre … 21 cm off | lamp post / 1.000 | lamp post / 1.000 | 0 / 0 |
| **25 cm off** | none / **0.625** | lamp post / **1.000** | 0 / 0 |
| **30 cm off** | none / **0.716** | lamp post / **1.000** | 0 / 0 |
| 40 cm off (outside the lamp head) | none / 0.856 | none / 0.856 (its lantern really is in the way) | 0 / 0 |
| 60 cm off | none / 0.955 | none / 0.955 | 0 / 0 |
| 3.0 m high (15 cm over the cap) | none / 0.008 | none / 0.008 (beyond the reach: the cap roofs it) | 0 / 0 |

**Frames** (`sheet_c1_offset_lamp.png`): the 25 cm lamp at noon, evening and night is identical to the Stage 1 F1
prototype frame (0 px), and its pool is 128.5 / 90.7 / 77.5 (before: 116.0 / 78.2 / 65.0).

**Independent occluders still block** (`tests/test_hd2d_lamp_fixture_gpu.py`):
- #458's panel 0.23 m from the light, and its walls.
- A wall 1.5 m and a crate 1 m from the offset lamps.

GPU and CPU agree on both rooms with 0 disagreements.

**Mutation checks:**
- Putting back the old containment (reach 0.01 m) fails the 9 new tests.
- A too-wide reach (0.30 m) fails the panel tests on both the CPU and the GPU, among 14 failures.

## C2: which lights get the two shadow maps

**`settings.shadow_allocation(lights)`** gives each scene light a status: `shadow_map`, `no_shadows`,
`over_shadow_limit` (set to cast shadows but the two maps are taken, so it shines through walls),
`over_light_limit` (past the 8 lamps, so not lit), `off`, `ambient` or `unusable`.

`parse_scene_lights` reads the lights through the same function, so the renderer's lamps, their order and their
shadow flags are exactly as before (the limit stays 2).

**Studio, HD-2D rooms only** (`studio/`):
- **Panel summary:** "Shadow maps: 2 of 2 in use. 1 more light set to cast shadows gets none and shines through
  walls."
- **List tags:** "- shadows", "- no shadow map", "- not lit" and "- off" on each light's row.
- **Inspector note:** under "Casts shadows", what that light actually gets.

**MCP `list_lights`:** each row has `hd2d_shadow` in HD-2D rooms, plus `hd2d_shadow_maps: 2`. A 2D room's listing
is unchanged.

**It matches the renderer** (`tests/test_hd2d_shadow_allocation_gpu.py`, Studio in a hidden window driven by input
events):
- The statuses match the renderer's `lamp_slots`.
- After switching light 2's shadows off in Studio, the map passes to light 4 in both Studio and the renderer.
- Ctrl+Z restores both.

**Unchanged:** Lakeside's fourth lamp. L1b ships its lamps off, so they read "off".

## Tests and performance (Windows, RTX 4070, Python 3.13, scratch APPDATA, XDG and Mesh folders)

- **Full default suite** (`-W error`, no `MESH_GL_SMOKE`): **11,042 passed**, 365 skipped, 2 failed. Both failures
  are `test_ci_shards_plugin`: this machine's pytest 8.4.2 lacks `subtests`. They are environmental and failed on
  the baseline in M17-L2 too. The export test passed with a short base path.
- **GPU** (`MESH_GL_SMOKE=1`, per file): **215 passed in 32 files**. The files cover:
  - lighting, lamp fixtures, allocation;
  - Studio, room Studio, 3D selection, undo/save, workflow, workspace, label wrap, DoF Studio;
  - runtime, starter, floors, cutaway, lab, visual standard, fire, campfire;
  - character shadows and the shadow suites, lighting-layer release;
  - viewport/HUD, new-game isolation, saved world, the runtime and interaction debuggers, AI playtest, room
    expand, asset pipeline.
- **New tests:**
  - `test_hd2d_lamp_fixtures.py`: 12 new or changed cases.
  - `test_hd2d_shadow_allocation.py`: 8, fast.
  - `test_hd2d_lamp_fixture_gpu.py`: 4 new, over the offset room.
  - `test_hd2d_shadow_allocation_gpu.py`: 3.
- **Lint and types:** ruff is clean. mypy shows the 73 pre-existing errors, none in changed files. No
  `# type: ignore`.
- **GPU timing** (`data/perf_summary.json`; base `18520c3` and the implementation alternating for 3 rounds; the
  same settled frame; framing identical): every range overlaps.

  | p10 ms | Village | Lakeside 1 | Lakeside 2 | Cottage |
  |---|---|---|---|---|
  | base | 0.235–0.265 | 1.666–1.760 | 0.516–0.550 | 0.133–0.150 |
  | implementation | 0.239–0.268 | 1.637–1.713 | 0.514–0.583 | 0.125–0.131 |

  That is expected: the draws are byte-identical, and the fixture rule runs once per room load.
