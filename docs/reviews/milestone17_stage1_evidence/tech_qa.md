# M17 Stage 1 HD-2D pilot: technical QA

Independent review of `D:\Games\Mesh-m17` (branch `feature/m17-visual-quality`). The repo was only read. All scripts, projects and evidence are in this folder. Windows were hidden or the checks were headless; no PixelLab calls were made.

**Verdict: CONDITIONAL PASS.** In the engine, the pilot cottage and hero are drop-in replacements with no functional regression:

- collision is byte-identical;
- walls, floors, the door, the inside room and the cutaway behave identically;
- textures are NEAREST;
- GPU objects stay stable across reloads, reimports and closing;
- the cost difference can't be measured.

It can't be merged or shipped as it stands, for these reasons:

- The mypy gate would fail (D1).
- `raw/` exposes the owner's PixelLab account ID (D2).
- Nothing allows the generated art to ship under `assets/NOTICE.md` (D3).

## Defects

| # | Sev | Defect | Evidence | Fix |
|---|---|---|---|---|
| D1 | **major** (blocks the CI merge) | 2 new mypy errors under the repo's config (`warn_return_any`). `tooling/mypy_gate.py` runs `mypy .` and excludes only untracked *directories*, so it checks `m17_visual_pilot.py` now and `pilot_m17/` once it is committed. Neither error is in `mypy_baseline.txt`. | The errors are `build_cottage_m17.py:46: Returning Any from function declared to return "int" [no-any-return]` and `m17_visual_pilot.py:70: Returning Any ... "Path"`. Local mypy is 1.18.2; the repo pins 1.19.1. | `return int(...)` and `return Path(...)`, or a typed local. |
| D2 | **major** (blocks committing `raw/`) | `raw/` (144 files, 248 KB) holds the owner's PixelLab **account UUID** (`<account id, redacted in Stage 1B>`) in storage URLs in 10 JSON files: `raw/characters/*/character.json`, `*/job_*/meta.json` and `raw/textures/t01_plaster_64/record.json`. It also holds 3 `character.zip` files that duplicate the extracted frames. | `grep -rl <account id>` finds 10 files. The URLs have the form `backblaze.pixellab.ai/file/pixellab-characters/<account>/<character>/…?t=…`. | Don't commit `raw/`: keep the md5s and job IDs in provenance (already there). Alternatively, strip `storage_urls`/`images` URLs and the zips. |
| D3 | **major** (blocks shipping; not the pilot) | The assets can't ship under the current rules. `assets/NOTICE.md` and `assets/hd2d_starter/PROVENANCE.md` say the kit is "original work made for Mesh by Mesh's own scripts … no third-party art", with textures "drawn in code"; the `hd2d_hero.png` row says "drawn in code by make_starter_art.py". The kit's catalog licence line says the same. Licence findings: (a) PixelLab ToS §3.3 says "You retain ownership of any content you create using PixelLab" and permits use and distribution; (b) the same ToS forbids training models on outputs without permission, and §4.1 requires Open RAIL-M compliance; (c) an open repo licence can't pass the training restriction on, and the copyright status of AI outputs is uncertain. | [pixellab.ai/termsofservice](https://www.pixellab.ai/termsofservice), last updated 2025-11-23; `docs/packaging.md` "To bundle another file". | The owner or a legal reviewer decides on (b) and (c). Then: a new NOTICE row (PixelLab-generated, owner's paid tier, date, ToS link and restrictions); allow-list entries in `pyproject.toml` `[tool.setuptools.data-files]`; `test_wheel_bundles_engine_data.py` expectations; a PROVENANCE.md section; and catalog `license` strings that no longer say "Mesh's own scripts". |
| D4 | minor | The framing boxes reach **into** the walls, and culling is off (`renderer.py:651`), so the cutaway exposes z-fighting planes. At z = 0.9 m, three coplanar faces from different materials overlap: sill bottoms (timber), `wall_*_high` bottoms (plaster) and `wall_*_low` tops (stone). At z = 2.5 m, post tops (timber) sit coplanar with, and facing the same way as, the wall tops (plaster). The starter already has a 2-material split at 1.3 m; the pilot adds a third material and a timber-on-plaster case. | `glb_check.json` lists 142 coplanar overlaps (starter: 58), for example `frame_sill_west/timber` vs `wall_west_low/stone_b_seamfix`, overlap 0.2 m², and `frame_post_*` vs `wall_*_high` at 2.5 m. In the cutaway render, `corner_A_vs_B.png` shows a timber streak on the cut stone wall. | Build the framing only outward from the wall faces: sills from Y0−0.03 to Y0, and so on. Keep posts within the wall: depth ≤ 0.20 m, not 0.22 m. |
| D5 | minor | The corner posts stand **2 cm proud inside the room**: their inner faces are at 0.22 m and the walls are 0.20 m thick. This shows as 2 cm timber slivers in all 4 interior corners from 0.9 to 2.5 m, which the cutaway exposes. | `near_coplanar_lt5cm`: `frame_post_* vs wall_*_high same 0.02`; the code is `build_cottage_m17.py` `cx + 0.22`. | Use 0.20 (or 0.18). |
| D6 | minor | A Studio reimport leaves a **false licence**. Reimporting the pilot into the template's `cottage` entry keeps `"license": "Mesh HD-2D starter kit: original, made by Mesh's own scripts; ships with Mesh"`, now attached to PixelLab content. This is engine behaviour, since `catalog.reimport_model` never touches `license`, but the pilot workflow triggers it. | See the `cottage` entry in `studio/catalog_after_reimport.json` (a copy of the test project's catalogue after the reimport). | Pilot docs: import it as a new asset with a licence. Engine (separately): clear or confirm the licence when a reimport changes sha256. |
| D7 | minor | Two deliverables can't be rebuilt from the repo. `hero_m17.png` and `stone_b_seamfix.png` were made by one-off scripts that are only in the session scratchpad (`m17/char/build.py`, `m17/tex/*`); `characters/provenance.json` itself says "kept in the session scratchpad". | I re-derived the hero sheet from `raw/` using the documented crop and shift: all 16 frames match pixel-exactly, with nothing clipped. So the steps are right, but no script ships. | Commit a small build script next to `build_cottage_m17.py`, or state that the documented steps are the record. |
| D8 | minor | The hero's **ground shadow is about 19 % narrower**. The engine sizes it once per sprite from the feet width of the first frame (`scene_render_pipeline._ground_shadow_size`). The pilot's idle-down feet are 9 px against the baseline's 12 px, so the shadow is 19.5 px wide instead of 24. In the side walk frames the feet are 22–23 px (baseline: 8–10). | See `sprite_check.json` `per_frame`. | Cosmetic. Accept it, or have the art pass check it. |
| D9 | minor (reporting) | The pilot's frame-cost claim isn't reproducible. `pilot.json` reports B at 8.26 ms against A at 6.61 ms (+25 %) from a single run. Four interleaved runs show no difference beyond noise (below). | See `game/perf.json`. Single rounds range from 4.8 to 7.9 ms for both variants. | Don't cite the cost figure from `pilot.json`; use the deterministic counts. |
| D10 | info | `ruff format --check` would reformat both new `.py` files. This isn't enforced: `ruff_gate.py` runs only `ruff check`, which passes. | — | Optional. |

## Measurements

### 1. GLB validity (`glb_check.py`, `glb_check.json`)

| | Starter `assets/hd2d_starter/models/cottage.glb` | Pilot `cottage_m17.glb` |
|---|---|---|
| Bytes | 35,568 | 64,876 (sha256 `4b745284…`, matches provenance) |
| Nodes / meshes | 20 / 20 | 33 / 33 |
| Drawn triangles / parts | 152 / 26 | 288 / 50 |
| Materials / textures / images | 4 / 4 / 4 (32²) | 6 / 6 / 6 (floorboards, timber, plaster 32²; stone_b_seamfix, roof_slate 64²; window_a 26×29). No duplicate images. |
| Samplers | mag NEAREST, min NEAREST_MIPMAP_NEAREST | The same, plus CLAMP_TO_EDGE for the window |
| Bounds | 5.6 × 4.6 × 3.8 m | identical |
| Structural | header, 4-byte chunk alignment, bufferView and accessor bounds, accessor min/max, index ranges, unit normals and embedded PNGs: all OK | all OK |
| `inspect_glb` warnings | none | none |
| Degenerate triangles / winding disagreeing with normals / inward normals | 0 / 0 / 0 | 0 / 0 / 0 |
| Collision | 7 `col_` nodes | byte-identical POSITION and index data, extras and transforms (`colliders_identical: true`); engine colliders identical |

**Depth precision at the gameplay camera.** The camera has pitch 30°, fov 12° and distance 53.5 m; the eye is 54.05 m from the wall. Near is 0.1 m, far 500 m, and the depth buffer is `GL_DEPTH_COMPONENT24`. One depth step is about 1.74 mm at that distance.

| Offset from the wall | Depth steps |
|---|---|
| Window decal, 1 cm | **6.6** |
| Sill, 3 cm | 19.7 |
| Posts and jambs, 4 cm | 26.3 |
| Window decal at the 2× close-up | 25.5 |

The 1 cm decal is safe, but the margin is thin; 2 cm would give about 13 steps. No z-fighting was seen in the renders. The exact-coplanar risks only appear when the cutaway exposes them (D4).

### 2. Studio import and reimport (`studio_check.py`, `studio_check.json`; hidden Studio, fresh `hd2d_rpg` project)

- Importing the pilot as a new asset worked: `cottage_m17` was created, its bytes equal the pilot's, and no "sharpen" was needed.
- The `cottage` structure was then pointed at the pilot with Studio's own reimport. Sequence: reimport pilot → reload → reimport pilot again → reimport starter → reimport pilot.
- No errors occurred and `hd2d_error` stayed None.

| Step | Live GL buffer / texture / framebuffer / program |
|---|---|
| Open (starter) | 119 / 41 / 7 / 28 |
| Pilot (all 3 times, and after the reload) | **123 / 43 / 7 / 28**, every time |
| Back to starter | 119 / 41 / 7 / 28 |

After each swap, the renderer's cottage model had the right triangle count (288 or 152) and the right material set, so no geometry or texture was left over from the previous file. The first Play/Stop adds 1 texture, 1 framebuffer and 1 program once (the known one-time setup); the second round is stable.

### 3. Collision and navigation (`game_check.py`, `game/game_check_A_B.json`)

A is the template; B is the pilot cottage.

| Check | Result |
|---|---|
| `World.stand` grid (0.25 m over the cottage ±1 m, z 0 and 0.1) | 1,450 queries: **0 differences** |
| Wall boxes near the cottage | identical (6) |
| Floors | identical |
| Walking into the south wall at both window spans | stopped at y = 9.797 in A and in B |
| Walking into the west and east walls | stopped at x = 7.172 and 12.828 in both |
| Walking into the north wall | stopped at y = 14.203 in both |
| Door | start.json → `cottage.json`, arriving at (8.0, 5.41) |
| Inside | walked east to x = 9.56, then back to the west door |
| Exit | → start.json at (10.0, 6.34), floor `ground`, the same in both |
| Cutaway behind the cottage | player visible 2394 / 2394 px with the cutaway, 0 without it, the same in both (`behind_A_vs_B.png`) |

### 4. Texture sharpness

- **In-engine:** every one of the renderer's textures is filtered (NEAREST, NEAREST), before and after 4 reloads. The window is CLAMP_TO_EDGE and the rest are REPEAT.
- **Renders:** pixel runs in `B_*_close.png` average about 10 px, and the 3× nearest zooms (`zoom_B_window_roof.png`) show hard texel edges with no bilinear blur.
- **Mipmaps:** the renderer ignores the GLB's minFilter and makes no mipmaps.
- **Texels per screen pixel at 1280×720:** at most 0.61 on the slate roof (starter shingles: 0.53) and at most 0.58 on the window. All faces facing the camera are magnified, so no texel drops out and there is no moiré.
- **At smaller windows:** the slate starts to minify below about 435 px of height (1.21 texels/px at 640×360; starter: 1.06).
- **Edge-on side faces:** they exceed 1 texel/px in both models (about 46). This is the same in both and not a regression.
- **Shimmer:** at 720p, pixels can only crawl between 1 and 2 px widths, as with the starter.
- **Eaves:** the gradient band under the eaves is the engine's soft shadow and is present in both (`zoom_eaves_A_vs_B.png`).

### 5. Sprite (`sprite_check.py`, `sprite_check.json`)

| Check | Baseline `hd2d_hero.png` | Pilot `hero_m17.png` |
|---|---|---|
| Size and mode | 128×192 RGBA | 128×192 RGBA |
| Alpha | {0, 255} | {0, 255} |
| Feet row in all 16 frames | 47 | 47 |
| Frames touching a cell edge | 0 | 0 (no bleed) |
| Blank frames | 0 | 0 |

- **Clips:** `character_clips(sheet, 32, 48, 4, {down:0, left:1, right:2, up:3}, walk_count=4, idle_count=1, sheet_rows=4)` builds all 8 clips.
- **Auto collider:** it depends only on the 32×48 frame size, so it is unchanged: `{w: 19, h: 12, offset_y: -18}`.
- **Bounding boxes:** the figure is 43–44 px tall against 40–41 px for the baseline. The side stride frames reach x = 3–29 and stay inside the cell.
- **Ground shadow:** see D8.

### 6. GPU cleanup and performance

Measured again: 4 interleaved rounds per variant, each a fresh hidden game at 1280×720 with 300 frames at the cottage door (`game/perf.json`).

| Median | A starter | B pilot | Δ |
|---|---|---|---|
| Frame (update + draw + GPU wait), ms | 6.80 | 6.45 | noise (single rounds 4.8–7.9 for both) |
| HD-2D renderer CPU, ms | 3.53 | 2.56 | noise (bimodal 1.3–3.8 in both) |
| GPU wait, ms | 2.40 | 2.37 | ≈0 |
| Draw calls | 29 | 31 | +2 (one batch per new texture) |
| Shadow draws | 28 | 30 | +2 |
| Triangles drawn | 1,372 | 1,508 | +136 |
| Renderer texture bytes | 137,216 | 168,904 | +31,688 (cottage: 16,384 → 48,072) |
| Static buffer bytes | 110,472 | 120,808 | +10,336 |
| GL objects after load | 567 / 40 / 6 / 27 | 571 / 42 / 6 / 27 | +4 buffers, +2 textures |
| After 4 room reloads | stable | stable | — |
| After close | 5 / 3 / 18 (textures / framebuffers / programs) | the same | no pilot leak |

The extra cost doesn't matter: 2 draw calls, about 136 triangles and 31 KB per cottage.

One observation that the pilot didn't cause: the live *buffer* count drifts with Python GC timing in both variants (for example, A was 2932 → 5942 after about 600 frames in one run but stable in the perf runs). Textures, framebuffers and programs never drift.

### 7. Licence and provenance

- **Texture records:** each of the 15 PNGs in `textures/` has a record with endpoint, prompt/request, seed, IDs, UTC time, generations used and a licence note. 14 are byte-identical to their raw file; `stone_b_seamfix` is a documented lossless offset of its raw file, which I verified as a pixel permutation. `contact_sheet.png` is a preview with no record. The 3 plaster variants and the moss candidate record "see record note" for submit time, because they share one call.
- **Character record:** the hero provenance has the calls, candidates and post-processing. Its cost is only bounded ("6 generations, worst case 9") because a sibling agent used the account at the same time.
- **Model record:** the model provenance has sha256 (verified), build command, Blender version and the textures used.
- **API token:** `PIXELLAB_API_TOKEN` (its value, either half of it, or its base64) appears in none of the 190 files under `pilot_m17`, in `m17_visual_pilot.py`, in any of the 567 scratchpad files, or inside the 3 zips. I checked this with `token_check.py`, which prints booleans only.
- **ToS and shipping:** see D3.

### 8. Repo hygiene

- `git status --porcelain` shows only `?? tooling/hd2d_assets/pilot_m17/` and `?? tooling/m17_visual_pilot.py`, which is 191 untracked files. `git diff` is empty, so no starter or engine file was modified.
- The pilot folder is 1.3 MB:
  - `raw/`: 144 files, 248 KB. Don't commit it (D2).
  - `textures/contact_sheet.png`: 257 KB, `characters/contact_sheet.png`: 33 KB, `walk_preview.webp`: 22 KB. These are previews: commit them only if they're wanted as review evidence.
  - `hero_m17_frames/`: 16 per-frame copies of the sheet. They are redundant.
  - Deliverables: `models/cottage_m17.glb` (65 KB), `characters/hero_m17.png` (9.6 KB) and the 3 textures used.
- `ruff check` passes on both new `.py` files. mypy finds 2 errors (D1).

## Conditions for a full PASS

1. Fix D1, the two mypy return types.
2. Leave `raw/` out of the commit, or redact the account UUID and drop the zips (D2). Commit only the deliverables, the READMEs, the provenance and the build script(s).
3. Before anything moves into `assets/hd2d_starter` or `assets/sprites`, resolve D3: the owner or a legal reviewer decides on the PixelLab training restriction and Open RAIL-M, then update NOTICE, PROVENANCE, the allow-list, the wheel test and the catalog licence lines.
4. Recommended but not blocking: D4 and D5 in `build_cottage_m17.py` (keep the framing outside the wall volume, posts ≤ 0.20 m), and D7 (commit the hero and seam-fix build steps).
