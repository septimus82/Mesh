# Kit cottage integration: independent technical and visual QA

Branch `feature/hd2d-cottage-b` in `D:\Games\Mesh-cottage`. Commits `06dcd6e` (cottage) and `11d0b1d` (safeguards), on top of `origin/redesign/visual-editor` (`4e8ea36`).

- **Old cottage:** `7b4c20ff…`, 35,568 B. This is `git show 4e8ea36:…/cottage.glb`, the same file as `scratchpad\cottage\cottage_old.glb`.
- **New cottage:** `24399f46…`, 72,148 B.

**How this review ran:**
- The repo was only read. `git status` stays clean before and after.
- Windows were hidden: `HiddenGame`, a hidden `StudioDriver`, and probe cameras through `renderer.draw(camera=…)`. Blender ran headless only.
- No PixelLab calls were made and nothing was uploaded.
- Every number below was re-measured by the scripts in this folder. None was copied from the implementer.

**Scripts and evidence (all in `qa\`):**
- `glb_check.py` / `.json`
- `game_check.py` / `.json`, with renders in `game\`
- `mask_diff.py` / `zfight_diff.json`
- `window_probe.py` / `.json`
- `sweep_probe.py` / `.json`
- `views.py`, with renders in `views\`
- `studio_check.py` / `.json`
- `catalog_check.py`
- `tmpl_check.py`
- `existing_check.py` / `.json`
- `perf_check.py` / `perf.json`
- `budget_probe.py` / `.json`
- `hygiene_probe.py` / `.json`
- `suite_*.log`, `mypy_gate.log`, `ruff_gate.log`

## Overall verdict: **ready for owner review**

- No blocker and no major defect was found.
- The cottage is a valid, reproducible drop-in:
  - collision is byte-identical;
  - floors, walls and navigation are identical in the engine;
  - there are 0 coplanar faces of different materials (60 before);
  - nothing drawn sits inside the walls, the slab or the room;
  - the window joints are closed;
  - the roof's shingles run up the slope at 32 px/m, the same way up as the original.
- Studio reimport, export, save/load and new-project creation behave correctly. Existing projects are never touched.
- What remains:
  - two cosmetic or documentation nits on the cottage (D1, D2);
  - robustness gaps in the advisory budget and hygiene tooling (D3–D6). None of them blocks shipping the cottage.

## Defects

| # | Sev | Area | Defect | Evidence | Fix |
|---|---|---|---|---|---|
| D1 | minor (visual) | windows | **The outer stiles show a dark line.** The timber texture is sampled at arbitrary phase, so its dark board-gap row (rows 7, 15, 23 and 31, luminance 50 against 91–113) lands in the west window's **left** stile (texel rows 23.6–25.6, a 0.4-texel sliver) and in the east window's **right** stile (rows 6.4–8.4, a full texel). No other frame piece gets it. The frames read as having a dark outer edge, mirror-symmetric about the door. It is noticeable at 2× and 4×, and is a 1–2 px line at 1×. | `views\cmp_window_w_x4.png`, `game\sweep_new_window_example.png`. The rows are computed from the frame extents in `glb_check.json` (`window_extents`) and `timber.png`'s row luminance. | Give each frame piece a v offset so its 2-px band falls inside a board, for example local art-grid px from `FRAME`, or v = 2/32 + local. Alternatively, accept it as grain. It is the owner's visual call. |
| D2 | minor (docs) | build_cottage | **Dangling reference.** The module docstring cites `docs/reviews/milestone17_stage1b_refinement.md`, which doesn't exist on this branch: there is no M17 review doc in `docs/reviews/` at all. This is the same dangling link that Stage 1B tech QA's D7 found in `NOTICE.md`. | `ls docs/reviews \| grep 17` gives nothing. | Point to PR #371 / `tooling/hd2d_assets/pilot_m17` on its branch, or add the doc. |
| D3 | minor | budget | **`init` accepts a non-finite approved budget**, and the CLI's `float()` parses `nan` and `inf`. With `approved = nan`, the "caps ≤ approved" check and the stage-wide check are both disabled: `init(nan, {"a": 1000})` is accepted, and so is a reservation of 500. `inf`, and `inf` caps, are also accepted. | `budget_probe.json`: `init approved=nan with caps 1000` → ACCEPTED; `reserve 500` → ACCEPTED. | `math.isfinite(approved) and approved > 0`, and finite caps. |
| D4 | minor | budget | **`settle(used=inf)` is accepted.** `committed` becomes `inf`, and every later reservation is refused ("-inf of 20 remain"). It fails closed, but one bad usage value bricks the stage's ledger for good, and `init` refuses to recreate it. | `budget_probe.json` | Require `math.isfinite(used)`. |
| D5 | minor | budget | **`sanitize()` still keeps some account data and credentials.** It keeps: a bare id under keys outside its list (`id`, `creator`, …); UUIDs or URLs used as **dict keys**; storage paths that are `%2F`-encoded or use backslashes; and a `"Authorization: Bearer …"` string under a non-secret key when `PIXELLAB_API_TOKEN` is unset. The docstring promises "no account or user fields … no credentials". It is mitigated in the repo, because the hygiene test recognises the real token and account id by digest. | `budget_probe.json` `sanitize`: all 8 cases are `true` (kept). | Sanitize keys as well as values. Redact every UUID, not only after `/`. Redact `Bearer \S+`. URL-decode before matching. |
| D6 | minor | hygiene | **The fast test catches what it promises, with gaps.** Not caught: a `raw/` folder outside `tooling/hd2d_assets/`, which is neither ignored nor detected; `.log`, `.html` and `.js` files (and, by construction, GLB JSON chunks and PNG text chunks); and a token written without hyphens. `docs/asset_licensing.md` says it fails on "a raw record" without that qualification. | `hygiene_probe.json`: a scratch git repo per case, running the test's own functions. | Match `/raw/` in any tracked path, or ignore `**/raw/` under generator folders. Scan every tracked file under 4 MB as bytes. Also hash 32-hex runs. Qualify the doc. |
| D7 | info | budget | `release()` frees any reservation id, whoever calls it: one agent can free another agent's hold. The agent's name is self-declared. The module documents that it is "a discipline for cooperating agents, not a security boundary". | `budget_probe.json` | None needed, or record the releasing agent. |
| D8 | info | windows | **Almost no depth ambiguity at the frame joints.** The rail ends meet the stiles mid-edge, a T-junction. At gameplay depth precision it gives 14 ambiguous px over 40 camera positions (about 0.35 px per frame), changing between (36,26,20) and (41,30,23). At one of the 11 walk spots (`behind_e`), 53 px along the windows' tops were ambiguous in the new model only. At 8× magnification with the same depth precision, a joint shows 1 px. This is invisible in play. | `sweep_probe.json`, `zfight_diff.json`, `window_probe.json`, `game\crop_behind_e_newonly_x3.png` | None. |
| D9 | info | cutaway | **The room's lower walls show cobbles inside.** The plinth material covers both sides of the `wall_*_low` boxes. Through the cutaway, the room's lower walls are cobbles instead of timber. Beside the west wall, at a grazing angle, the cobbles minify into streaky vertical lines; the old timber did the same, as dots. | `game\cmp_behind_c_old_new_x2.png`, `game\cmp_beside_w_cut_x4.png` | Owner's call. For example, timber on the inner faces only. |
| D10 | info (pre-existing) | slab | Stage 1B's D10 ground band is unchanged: the slab's bottom face is coplanar with the ground. The near-plane z-fight masks at the front, window and inside spots are pixel-identical between old and new. | `zfight_diff.json`: `front`, `window_w`, `window_e` and `inside` have 0 new-only and 0 old-only pixels. | As in Stage 1B. |
| D11 | info (pre-existing) | other roofs | **The other kit roofs were left unchanged, as instructed.** The shop's roof is 28.3 px/m along the slope, roof_4m's is 27.0, and both north slopes' images are upside down. The cottage's roof (32 px/m) now differs from the shop's beside it. | `glb_check.analyse` on `shop.glb` and `roof_4m.glb`, which rebuild byte-identically. | A follow-up, if the owner wants consistency. |
| D12 | info (pre-existing) | Studio | Reimport keeps the kit's licence line and the "with windows" note when another file is reimported (Stage 1 D6 / 1B D9). It is true for both cottages here, since both are Mesh's own. | `studio_check.json` `entry` | As documented in `docs/asset_licensing.md`. |

## Verdict per area

| Area | Verdict |
|---|---|
| 1 Reproducibility | **PASS.** All 14 kit GLBs and both Stage 5B demo cottages rebuild byte-identically. The catalog, all 14 previews and the template card regenerate byte- or pixel-identically. |
| 2 GLB validity and geometry | **PASS.** Minor: D1. Info: D8. |
| 3 Roof orientation | **PASS.** The image runs up the slope in the same sense as the original. The shop and roof_4m are untouched. |
| 4 Collision and navigation | **PASS.** Byte-identical colliders, 0 of 1,450 floor queries differ, the walls are identical, and the door and walk routes are identical. |
| 5 Cutaway | **PASS.** No new z-fighting or streaks. The old cross-material faces at 1.3 m are gone (177–184 px fewer ambiguous pixels behind the cottage). Info: D9. |
| 6 Studio, export, save/load | **PASS.** |
| 7 New vs existing projects | **PASS.** |
| 8 Performance and GPU lifetime | **PASS.** +2 draws, +250 triangles, +4.1 KB of textures, +18 KB of buffers; about +0.1 ms of CPU. No GL growth. |
| 9 Visual at gameplay scale | **PASS, with a cosmetic nit (D1).** |
| 10 Safeguards | **CONDITIONAL.** They work as specified, including the previous D1/D2 fixes and the per-agent caps. Minor gaps remain: D3–D6. |
| 11 Suites | **PASS.** Fast and GPU are green. ruff is ok. mypy shows only the two known `tooling/hd2d_lab` numpy errors. |

## Measurements

### 1. Reproducibility

- **Kit rebuild:** `blender.exe --factory-startup -noaudio --background --python build_starter_kit.py -- qa\kit`, with Blender 5.2. All **14/14** GLBs equal the committed files, sha256 for sha256. `cottage` is `24399f46…`.
- **Stage 5B demo cottages:** `build_cottage.py -- OUT` equals `tooling/hd2d_assets/cottage.glb`, and `-- OUT --v2` equals `cottage_v2.glb`.
- **Catalog:** `catalog_check.py` rebuilds every entry from the rebuilt GLBs with `make_starter_kit.MODELS` and `LICENSE`. 14/14 entries are equal, and the kit `version` is 2.
- **Previews:** `thumbnail.render` gives byte-equal PNGs for 14/14.
- **Template card:** `make_template_previews.render_hd2d` on a fresh `hd2d_rpg` project is **byte-equal** to `assets/templates/hd2d_rpg.png`.
- **Unchanged files:** `git diff --name-status 4e8ea36 HEAD` lists only `cottage.glb` and `previews/cottage.png` under the kit's models and previews. No sprite changed, so the starter character art is preserved.

### 2. GLB validity and geometry (`glb_check.json`)

| | Old | New |
|---|---|---|
| **Structure:** header, JSON then BIN, 4-byte chunks, views and accessors in bounds and aligned, POSITION min/max exact, indices in range, unit normals, PNG decode | OK | OK |
| `inspect_glb` warnings | none | none |
| Collision / floors | 1 solid, 6 wall / `col_floor` | identical |
| Triangles / parts | 152 / 26 | 402 / 55 |
| Images | 4 × 32² | 5 × 32² (cobbles added); every one pixel-identical to `tooling/hd2d_assets/textures/*.png` |
| Samplers | 1: mag NEAREST, min NEAREST_MIPMAP_NEAREST (every kit model) | the same; the renderer uploads with NEAREST and no mipmaps |
| Degenerate triangles / degenerate UVs | 0 / 0 | 0 / 0 |
| px/m on textured faces (min–max singular value) | 27.86–32.0 | **32.0–32.0** on every textured face |
| Roof slopes: px/m along / across the slope | 27.86 / 32.0 | **32.0 / 32.0** |
| Coplanar overlapping faces of **different** materials | **60** (floor/wall 14, wall low/high 38, lintel/wall 6, lintel/roof 2) | **0** |
| Coplanar overlaps, same material and same facing | 104 | 48: the wall boxes' corner ends, with a UV mismatch of 0.000 px, so invisible |
| Coplanar overlaps, same material, opposite facing | 16 (roof/wall plaster) | 72: timber/timber at the window joints, enclosed |
| Near-coplanar (0.1–6 mm) | 0 | 31: the post bottoms 2 mm over the sill top, opposite-facing and enclosed; the cutaway discards both together. 38: the pane 5 mm behind the frame's back faces, opposite-facing, with the frame front 3.5 cm nearer |
| **Interior clipping:** 45 barycentric samples per triangle, on every drawn triangle except the walls, lintel and slab themselves, tested against 5 wall boxes, the lintel, the slab and the room | 0 | **0** |

**Window joints:**
- Each window has 10 abutting pairs. All are at a gap of **0.000 mm**, with no volume overlap.
- The pane's extent equals the frame's outer extent exactly: W x −1.8 … −1.3, z 1.125 … 1.71875, at y −2.02.
- The frame runs from y −2.06 to −2.025.
- The previous 4 mm gaps and the 2 mm pane overhang are gone.
- Abutting creates T-junctions, not coplanar overlaps: see D8.

**The flat pane material:**
- **In the GLB:** `baseColorFactor` is linear (0.02122, 0.02732, 0.05127, 1), with no texture.
- **Reader:** a 1×1 texel of (40, 46, 64, 255), nearest and repeat.
- **Renderer:** one extra texture (42 against 40 live).
- **Studio:** `inspect_glb` reports "Flat colour: glass". The catalog preview shows the dark panes: 1,219 px at the pane colour, and the preview is byte-equal after reimport. `sharpen_textures` leaves the file untouched (the reimported bytes equal the source).
- **Export:** `mesh export build` ships the file byte-equal, and it inspects with "Flat colour: glass".

### 3. Roof orientation (`game_check.json` `roof`, `game\roof_old_new_x8.png`)

- **Method:** an 8× probe render of the south slope. I sampled the luminance up the slope (392 samples), then correlated it with `shingles.png`'s row profile, predicted from each mapping both ways up.
- **Old:** old mapping, image-up = up the slope, gives r = **0.894**; downslope gives −0.428.
- **New:** new mapping, image-up = up the slope, gives r = **0.917**; downslope gives −0.433.
- **So the shingles run up the slope in both.** Each course reads (up the slope) gap, then shadow row, then lit rows, the same way as the original. Only the scale changes, from 27.9 to 32 px/m.
- **Darkest row:** it sits at the eave (`EAVE_PHASE`), as `views\cmp_eave_door_x4.png` shows.
- **Directions:** measured from the GLB, the new north slope's +v runs the same way relative to the slope as the south slope's. The old north slope's ran the opposite way, so it was upside down.
- **Other roofs:** `shop.glb` and `roof_4m.glb` are byte-identical to the base (D11).

### 4. Collision and navigation

- **`col_` nodes:** all 7 have identical extras, TRS, attribute sets and accessor bytes (sha256 of each accessor's view slice).
- **In the engine, with HiddenGame and the template village:**
  - `World.stand` grid: x 6.5–13.5, y 9–15, 0.25 m steps, z 0 and 0.1. That is **1,450 queries, 0 differences**, and 1,122 standable in both.
  - The cottage walls and surfaces are identical.
  - `walkable()` is 6,800 in both.
- **Walking with key events** (identical for old and new):

| Route | Old | New |
|---|---|---|
| Walk into the south wall at the W window / E window | y 9.797 / 9.797 | the same |
| West wall / east wall / north wall | x 7.188 / x 12.812 / y 14.250 | the same |
| Door: UP from (10, 6.8) | `cottage.json` at (8.0, 5.412), floor `room/col_floor` | the same |
| Inside, east to x 9.562, then west to 5.578, then UP | back in `start.json` at (10.0, 6.338), floor `ground` | the same |

### 5. Cutaway (`game\*`, `zfight_diff.json`)

- **Method:** at 11 spots, each frame was rendered 5 times with the near plane × {1, 1.003, 0.997, 1.01, 0.99}. The x/y projection doesn't change, so any pixel that changes is decided by depth.

| Spot | Ambiguous px, old → new | New-only | Old-only |
|---|---|---|---|
| behind_c / behind_w / behind_nw / behind_ne | 5036→4860 / 5039→4856 / 4982→4818 / 4878→4816 | 1 / 1 / 1 / 1 | 177 / 184 / 165 / 63 (the old 1.3 m timber/plaster faces) |
| behind_e | 3485→3535 | 53 (the window tops, D8) | 3 |
| beside_w / beside_e | 256→258 / 255→257 | 2 / 2 | 0 |
| front, window_w, window_e, inside | identical | 0 | 0 |

- **The shared bulk is pre-existing and not on the cottage's new parts:** the stairs and bridge tops, the fence posts, and the slab and ground band (D10).
- **Player visibility with the cutaway:** behind the cottage, 1,518–2,069 px; without it, 0. This is identical between old and new. Beside the cottage, the player is fully visible (1,727 / 1,728 px) in both.
- **Renders:** `game\cmp_behind_c_old_new_x2.png`, `…nw_corner…`, `…beside_w…` and `cmp_beside_w_cut_x4.png` show no streaks at the windows, sill or posts.

### 6. Studio, export, save/load (`studio_check.json`)

**Reimport:** a fresh `hd2d_rpg` project, a hidden Studio, and Studio's own reimport handlers and button.

| Step | File | Triangles / parts | Materials | Renderer triangles / draws / textures | GL tex / FB / prog | Models dir |
|---|---|---|---|---|---|---|
| open (template) | new | 402 / 55 | 6 (with glass) | 1622 / 31 / 26 | 43 / 7 / 28 | 16 files |
| → old | old | 152 / 26 | 4 | 1372 / 29 / 24 | 41 / 7 / 28 | 16 |
| → new | new | 402 / 55 | 6 | 1622 / 31 / 26 | 43 / 7 / 28 | 16 |
| → old → new (round 2) | | identical to round 1 | | | | |

- The file equals its source at every step.
- `hd2d_error` is None every time.
- The plan text is "402 -> 152 triangles." / "152 -> 402 triangles.", with no warnings.
- The structure entry `{id: cottage, x: 320, y: 384, cutaway: true}` is unchanged throughout.

**Export and save/load:**
- **Export:** `python -m mesh_cli export build --repo-root <project> --deterministic` exits 0 with 1,035 files. The bundle's `assets/models/cottage.glb` is **byte-equal to the new cottage** and inspects cleanly.
- **Save/load:** `save_game` with the player at the east wall (12.812, 12.062, `ground`). I then walked away to (12.812, 6.984) and called `load_game`. The player is back at (12.812, 12.062) on `ground`. The cottage structure (id, model, x, y, rotation, cutaway) is identical, and the scene file is unchanged.

### 7. New vs existing projects

- **New project:** `create_project(..., "hd2d_rpg")` gives `assets/models/cottage.glb` = `24399f46…`, the kit's file. Its catalog source is `{"kit": "Mesh HD-2D starter kit 2", "sha256": …}`.
- **Existing project:** `existing_check.py` simulated a kit-1 project (old cottage, catalog saying kit 1). It was opened in a hidden Studio and a hidden game. **0 files under `assets/` changed**, and the catalog still says kit 1 with the old sha.
- **Code:** `install_kit` has a single caller, `starter_village.build`, which runs only at template creation. It refuses any id or file already present. A grep for an upgrade or migration path (`install_kit`, `hd2d_starter`, `kit`, `upgrade`, `migrat`) in `engine/` and `mesh_cli/` finds none.

### 8. Performance and GPU lifetime (`perf.json`)

- **Method:** 5 interleaved rounds (old/new alternating first), a fresh hidden game at 1280×720 each, 300 frames, the player beside the door.
- **Clock state:** the machine was in a slow state for the first rounds. Its rounds are bimodal: renderer CPU about 3.6–4.0 ms against about 1.35–1.45 ms.

| | Old | New |
|---|---|---|
| Frame ms, round medians | 6.03, 5.70, 5.96, 4.12, 4.07 | 7.57, 7.93, 4.27, 4.27, 4.21 |
| Steady rounds only: frame / HD-2D renderer CPU | 4.07–4.12 / 1.34–1.35 ms | 4.21–4.27 / 1.40–1.44 ms (about +0.15 / +0.08 ms) |
| Draw calls / shadow draws | 29 / 28 | 31 / 30 |
| Triangles | 1,372 | 1,622 |
| Renderer texture bytes | 137,216 | 141,316 (+4,100: cobbles and the glass texel) |
| Static buffer bytes | 110,472 | 128,448 |
| GL texture / FB / program: load → 4 reloads → close | 40/6/27 → 40/6/27 → 5/3/18 | 42/6/27 → 42/6/27 → 5/3/18 |

Live buffer counts drift with GC (91 … 3,016) in both variants, as is known.

### 9. Visual, at gameplay scale

**Sources:**
- `ba\integration_*`;
- my own renders: `views\cmp_*_x2.png` and `_x4.png` (1:1 gameplay camera framings, pitch 30, FOV 12, 53.5 m), `views\new_village.png` and `game\*`.

**At 1× and 2×:** it reads cleanly as a timber-framed cottage.
- The cobbled plinth with the sill on top gives a clear base.
- The windows are legible: dark panes with a cross mullion, and a sun shadow on the plaster.
- The posts frame the corners.
- The roof courses are finer, and regular.

**At 4×:**
- **Plinth:** its top falls on a gap between cobbles, so there are no half cobbles under the sill.
- **Seams:** there are none between the sill, posts and walls.
- **Post grain:** it shows as a single dark board line that steps once along the post. The line follows the narrow lens's keystone lean, the same as the wall edges.
- **Windows:** the only nit is D1, the dark outer stile.

**In the village:** with the shop (timber, awning) and the cobbled wall modules, it sits well. The cobble plinth matches the wall modules' stone. The shop's plain timber walls are now visually simpler than the cottage, but this is not a clash.

**Characters:** the same hero, villager and merchant sheets.

### 10. Safeguards

**Tests:** `tests/test_pixellab_budget.py`, `tests/test_generated_asset_hygiene.py` and `tests/test_mypy_gate_diagnostics.py` give **26 passed**.

**Budget probe:**
- **Refused:**
  - over the agent's own cap ("character has 5 of its 5 left");
  - a subtask under a new name (`character/sub`) or a case variant;
  - caps above the approved total;
  - a second settle, and a release after settle;
  - units 0, −3, 1.5, True and 10⁹;
  - used −1, nan, −inf, True and "3".
- **Concurrency:** 40 threads on caps 15 + 5 gave **20 accepted** (15 / 5 by agent), 20 refused, 20 ledger entries, and no lock left behind.
- **Gaps:** D3, D4, D5 and D7.

**Hygiene probe** (the test's own functions against a seeded scratch repo):
- **Caught:**
  - a raw record under `tooling/hd2d_assets/**/raw/`;
  - a storage URL with an id;
  - a scheme-less bucket path;
  - the token by digest, bare and in upper case.
- **Missed:** D6.

**No PixelLab-derived file:**
- `git ls-files` matching pixellab, pilot, m17, raw, hero_m17, stone_b, window_a or cottage_m17 returns only `tooling/pixellab_budget.py` and its test.
- The branch diff adds no asset other than the regenerated cottage, its preview and the template card.
- The pyproject allow-list is unchanged; it lists `cottage.glb` at the same path.
- The cottage's embedded images are pixel-identical to the starter textures.

### 11. Suites

| Suite | Result |
|---|---|
| `py -3.13 -m pytest -q -m fast -p no:cacheprovider` (from the worktree) | **4605 passed**, 6 skipped, 5385 deselected (125 s) |
| `MESH_GL_SMOKE=1 py -3.13 -m pytest -q -p no:cacheprovider tests/*_gpu.py` (17 files) | **111 passed** (166 s) |
| `py -3.13 tooling/mypy_gate.py` | exit 1, with exactly the 2 known pre-existing errors (`tooling/hd2d_lab/gltf.py` type-var, `tooling/hd2d_lab/lab.py` no-any-return; numpy 2.4.4). Nothing else. |
| `py -3.13 tooling/ruff_gate.py` | ok |

`git status --short` in the worktree is empty after all runs.

**A pre-existing test leak, not caused by this branch:** the fast run wrote two save files into the worktree's git-ignored `saves/` folder:
- `…pytest-273test_hatched_offspring_persist…`
- `…test_pending_egg_survives_save…`

I deleted the two that my run created. The implementer's earlier runs left the same files there at 06:45 and 06:58; I left those alone.

**Cleaned up after the review:** the scratch projects, the export bundle, the scratch ledgers and the source copies are deleted. The scripts, JSON, logs and renders stay in this folder as evidence.
