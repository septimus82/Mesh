# M17 Stage 1B: technical QA

Independent review of `D:\Games\Mesh-m17` (branch `feature/m17-stage1b`, working tree on top of `be13ad1`).

- The repo was only read: `git status` is unchanged by this review.
- Windows were hidden (`HiddenGame`, hidden `StudioDriver`); Blender ran headless only. No PixelLab calls were made, and no budget was reserved.
- All scripts and evidence are in this folder:
  - `glb_check.py` / `.json`
  - `texel_check.py` / `.json`
  - `game_check.py`, with `game/` (renders, z-fight masks, `game_check.json`)
  - `studio_check.py`, with `studio/studio_check.json`
  - `hero_check.py` / `.json`
  - `perf_check.py`, with `perf/perf.json`
  - `secret_scan.py`
  - `budget_probe/probe.py`
  - `rebuild/` (the headless rebuilds)
- Every number below was re-measured. None was copied from the generator.

**Verdict:** the art is technically sound. B and C are valid, reproducible, drop-in models. The three Stage 1 geometry defects are fixed, and H2–H4 are correct sheets. The new **budget** module has real bypasses, and the hygiene layer has gaps. Neither guards what it claims yet (D1, D2, D3).

## Defects

| # | Sev | Element | Defect | Evidence | Fix |
|---|---|---|---|---|---|
| D1 | **major** | budget | `reserve` and `settle` accept **negative, zero and fractional amounts**, so the shared budget can be bypassed. `units=-3` on inpaint gives committed = −30, after which a 45-generation reservation passes on a 20 budget. `units=0` followed by `settle(used=50)` records 50 on a 20 budget, flagged only as an "overrun". `settle(used=-10)` gives committed = −10. `units=0.01` is accepted. | `budget_probe/probe.py` (output in the summary below) | `units` must be an `int ≥ 1`. `used` must be a finite number `≥ 0`. Optionally refuse `used > reserved` unless it is forced. |
| D2 | **major** | budget / hygiene | `sanitize()` doesn't keep account data out, although its docstring and the ledger test promise it does. It keeps: (a) a bare account id under any key (`user_id`, `owner`, …); (b) **scheme-less storage paths** such as `backblaze.pixellab.ai/file/pixellab-characters/<id>/…`, because the URL regex needs `://`; (c) the token under any key that isn't one of the 7 listed (`x-api-key`, `bearer_token`, …) whenever `secret` is left at its default `""`; (d) anything inside a tuple. | `probe.py`: `sanitize_keeps_bare_account_field`, `…schemeless_storage_path`, `…x_api_key_without_secret_arg` and `…url_in_tuple` are all `true`. | Make `secret` default to `os.environ["PIXELLAB_API_TOKEN"]`. Redact every UUID that follows `pixellab-characters/` or a storage host with or without a scheme. Drop keys matching `*id` when they equal the account id (from env), plus `*key*`/`*token*`/`*auth*`. Recurse into tuples. |
| D3 | minor | hygiene | The CI-side leak test can't see the two secrets it exists for. The token is **UUID-shaped** (`token_uuid_shaped: True`), so outside `Bearer …` no pattern matches it, and CI has no `PIXELLAB_API_TOKEN`. A bare account id in tracked JSON isn't matched either: only storage URLs and paths are. The test is also detective only: it runs after a commit, and could run after a push. Other paths still reach a commit: `git add -f`; a `raw` folder outside `tooling/hd2d_assets/`; zips, `.log`/`.html` files, PNG text chunks; text over 4 MB. | `secret_scan.py` (prints booleans only). `tests/test_generated_asset_hygiene.py`: `TEXT`, `FORBIDDEN` and the `len(token) >= 16` guard. | Commit **sha256 digests** of the account id and of the token. The test then hashes every UUID in tracked files, so it works in CI without the secret. Add the same check as a pre-commit hook. Optionally scan zip members and PNG text. |
| D4 | minor | hygiene / gate | The local **mypy gate is red: 15 errors, 13 of them new**. All 13 are in the git-**ignored** `raw/scripts/{char,tex}/*.py`. `mypy_gate._untracked_dirs` uses `ls-files --others --exclude-standard`, so ignored folders are not excluded, and mypy checks them. CI is unaffected, because `raw/` is never committed. The 2 `tooling/hd2d_lab` numpy errors are the known pre-existing ones. | `mypy_gate.log` | The gate also excludes ignored directories (`git ls-files --others --ignored --exclude-standard --directory`). Alternatively, keep scripts out of `raw/`. |
| D5 | minor | hygiene / gate | `build_hero_1b.py` is **never type-checked by the gate**. The repo's mypy `exclude = ["build", …]` is a regex, and it drops every path containing "build": `build_hero_1b.py`, `build_cottage_m17.py`, `build_cottage.py`. Run directly, `build_hero_1b.py` has **19 mypy errors**: `PixelAccess \| None` indexing and `getpixel` unions. This is a pre-existing config quirk. It also means Stage 1's D1 half about `build_cottage_m17.py` was never reachable by the gate. | `mypy -v` source list (no `build_*` files); a direct `mypy` run on the file. | `exclude = ["^build/", "^dist/", …]`. Then `px = f.load(); assert px is not None` and similar fixes in the script. |
| D6 | minor | B, C models | The window frame pieces stand **4 mm apart, not 2 mm**: each piece is `EPS` short on every side. The pane also extends 2 mm past the frame's outer edge on all four sides. Both are sub-pixel at gameplay scale (0.26 px and 0.13 px at 64 px/m). At the 4× close-up they leave dark 1 px specks at the joints, and at any scale they can crawl as the camera moves. The documentation says "pieces 2 mm apart". | `glb_check.json` `framing.extents`: `stile_l` x −1.798 vs pane −1.8; `rail_top` −1.7355 vs `stile_l` −1.7395. See also `window_close_x6.png`. | Shrink by `EPS/2`, or let the stiles run full height with the rails between them. Inset the pane by `EPS`, or extend the frame by `EPS`. Correct the provenance and README wording. |
| D7 | minor | hygiene / provenance | `NOTICE.md` links to `docs/reviews/milestone17_stage1b_refinement.md`, which doesn't exist. Stage 1's D7 is only partly closed. H2–H4 now rebuild from a committed script. `hero_m17.png` and `stone_b_seamfix.png` still come from scripts that sit only in the ignored `raw/scripts/`, and `characters/provenance.json` `scripts` still says "kept in the session scratchpad". | `ls docs/reviews`; `characters/provenance.json` | Write the review doc, or fix the link. Commit the two derivation scripts outside `raw/` (they hold no secrets: the scan found none in `raw/scripts`), or state that the documented steps are the record. |
| D8 | minor (reporting) | tool | The tool still records **one frame-cost run per variant** (Stage 1 D9 recurs). The committed `characters/gameplay_1b/hero.json` and `m17b/*/{set}.json` show H1–H4 and B/C at +0.8 to +1.4 ms over the baseline. Interleaved rounds show ±0.05 ms (below). | `cottage.json`: A 7.14, B 8.52, C 8.19 ms. `perf/perf.json`: medians A 5.03, B 5.07, C 5.07, H4 5.01 ms. | Cite only the deterministic counts. Optionally, `frame_cost` interleaved over ≥3 rounds. |
| D9 | minor (engine, report only) | Studio | **Licence line on reimport (Stage 1 D6): still present.** After reimporting C (PixelLab textures), the `cottage` entry still says "Mesh HD-2D starter kit: original, made by Mesh's own scripts; ships with Mesh". `source.kit` is dropped, but `license` isn't touched. The line is true for B (starter textures and repo scripts) and false for C. | `studio/studio_check.json`, every step | Engine: clear the licence, or ask for it, when a reimport changes sha256. Pilot: import C as a new asset with its own licence. |
| D10 | info (pre-existing) | engine / starter kit | **Z-fighting at the foot of every cutaway**, in A, B and C alike. The floor slab's bottom face (z = 0) is coplanar with the ground. The cutaway discards the slab top (above floor + 0.05), so the pair shows as a 2–3 row flickering band at the bottom of the opening. B/C change only the slab bottom's material, from timber to plinth. | Near-plane probe, in-box ambiguous pixels: `behind_c` A 573 / B 558 / C 558; `behind_w` 949 / 941 / 941. See `game/zfight_overlay.png`. | Drop the slab's bottom face in the kit, or raise the cutaway floor margin. |
| D11 | info | hygiene | `ruff format --check` would reformat 6 of the 7 new or changed `.py` files. This isn't enforced: `ruff_gate` is ok, and `ruff check` passes. Stage 1 left a 9-character fragment of the account id (`7415…fb30d`) in `be13ad1`'s `tech_qa.md`, on `origin/feature/m17-visual-quality`. It is redacted in the working tree. A history scan found **no** full account id or token in any blob reachable from `HEAD`. | `secret_scan.py`; `ruff format --check` | Optional. |

## Stage 1 defect status

| Stage 1 | Status | Evidence |
|---|---|---|
| D4: coplanar framing z-fighting in the cutaway | **Fixed** | Coplanar overlapping pairs **between different materials**: A 60, **B 0, C 0** (this matches the generator's 60 → 0). The remaining 48 same-material pairs (A has 120) are the overlapping wall-box ends at the corners. They use the same texture and the same planar UVs, so they are invisible. In the cutaway, near-plane perturbation finds no depth-ambiguous pixels in B/C beyond A's pre-existing ground band (D10). No streak shows in `cut_zoom_ABC.png`. |
| D5: corner posts 2 cm into the room | **Fixed** | 296 framing and window triangles, 45 barycentric samples each: **0** points inside a wall box, the lintel, the floor slab or the room. Posts run x −2.57…−2.34 (1 cm clear outside), z 1.002–2.49. The sill ring's top and bottom areas equal the ring band exactly (0.6816 m²), so the concave 12-gon is triangulated correctly. The L-post tops are each 0.024 m², as expected. |
| 1 cm window offset | **Fixed** | The pane is 2 cm out. At the gameplay camera (pitch 30°, fov 12°, distance 53.518; eye 54.9 m from the window; near 0.1, far 500; the depth attachment is `GL_DEPTH_COMPONENT24`, read from GL) this is **12.8 depth steps**. The other gaps: frame back face to pane, 3.2 steps; frame front, 25.7; sill to wall, 6.4. The two thin cases are occluded by their own front faces. |
| D6: catalog licence on reimport | **Still present** (engine) | D9 above |
| D1 mypy | The Stage 1 lines are gone. The gate is now red locally for a new reason. | D4 and D5 above |
| D2 raw/ account id | **Mitigated**: `raw/` is ignored and was never in history. The test has gaps. | D2 and D3 above |
| D7 rebuildability | **Partly fixed** | D7 above |
| D8 ground shadow | Moot in this template, which uses real sun shadows: `mesh_ground_shadow` is None for every variant. If the blob is used, H4 gives 22.5 px against H0's 24, because its idle feet are 11 px against 12. | |
| D9 single-run cost | **Recurs** | D8 above |

## Measurements

### 1. GLB validity (`glb_check.json`, `texel_check.json`)

| | A starter | B `cottage_m17_geo.glb` | C `cottage_m17.glb` |
|---|---|---|---|
| Bytes / sha256 | 35,568 / `7b4c20ff…` | 72,836 / `1e7ce0ae…` (= provenance) | 75,560 / `8b7cb34f…` (= provenance) |
| Structure | OK | OK | OK |
| Drawn triangles / parts | 152 / 26 | 402 / 55 | 402 / 55 |
| Images (embedded PNG, pixel-identical to source) | 4 × 32² | 5 × 32², plus `glass` flat colour | 5 × 32², plus `stone_b_seamfix` 64², `window_a_glass` 26×29 (CLAMP) |
| Renderer texture bytes for the model | 16,384 | 20,484 | 35,784 |
| Degenerate triangles / normal–winding mismatches | 0 / 0 | 0 / 0 | 0 / 0 |
| Texel density, every textured face | 27.9–32 px/m (roof) | 32.0 | 32.0 |
| Collision (7 `col_` nodes: extras, transforms, POSITION/index bytes) | — | byte-identical | byte-identical |

The structure checks covered: header, chunk order and alignment, bufferView and accessor bounds, POSITION min/max, indices in range, unit normals, and PNG decode. `load_glb` and `inspect_glb` both pass, with no warnings.

- **Reproducibility.** Two headless rebuilds of each set (`rebuild/`) all give the committed sha256: `starter` → `1e7ce0ae…`, `pixellab` → `8b7cb34f…`. `build_cottage.py` also rebuilds the starter byte-identically, and `make_window_glass.py` (run on a copy) reproduces `window_a_glass.png`. B is still untracked. C's committed blob is the Stage 1 file; the working tree holds the 1B file.
- **The flat material (B's panes)** survives every step:
  - **Blender export:** `baseColorFactor` is linear (0.0212, 0.0273, 0.0513, 1), with no texture.
  - **`glb.py`:** `_Reader.materials` turns it into a 1×1 sRGB texel. It comes back as exactly **(40, 46, 64, 255)**, with `nearest` and `repeat`.
  - **Renderer:** the texel is batched as its own texture (+1 draw).
  - **Studio:** `inspect_glb` reports "Flat colour: glass", the catalogue preview shows dark panes (`preview_B_x2.png`), and `sharpen_textures` skips the material, so the reimported bytes equal the source.
  - **Exporter:** `mesh export` (`build_bundle`, exit 0) ships the file byte-identical to B, and it inspects cleanly.

### 2. Collision, navigation and cutaway (`game/game_check.json`; hidden 1280×720 games)

| Check | A | B | C |
|---|---|---|---|
| `World.stand` grid (x 6.5–13.5, y 9–15, 0.25 m, z 0/0.1; 1,450 queries) | — | 0 differences | 0 differences |
| Wall boxes near the cottage | — | identical | identical |
| Walk into the south wall at each window / west / east / north | y 9.75 / x 7.172 / 12.828 / y 14.194 | same | same |
| Door: enter (UP) → walk east inside → back to the west door → exit | `cottage.json` at (8.0, 5.41) → x 9.56 → `start.json` at (10.0, 6.34), floor `ground` | same | same |
| Player behind the cottage (3 spots): visible px with / without cutaway | 2394, 2392, 2382 / 0 | same | same |
| Beside the cottage (E, W), front (E) | fully visible | same | same |

The z-fight probe renders each spot 5 times with the near plane scaled by 1, 1.003, 0.997, 1.01 and 0.99. The x/y projection is unchanged, so any pixel that changes is decided by depth quantisation alone. It found nothing new in B/C, only A's pre-existing ground band (D10).

### 3. Studio import and reimport (`studio/studio_check.json`; fresh `hd2d_rpg` project, hidden Studio, Studio's own reimport path)

| Step | Triangles / parts | Materials | Renderer textures | GL buffer / texture / FB / program |
|---|---|---|---|---|
| Open (starter) | 152 / 26 | 4 | 24 | 119 / 41 / 7 / 28 |
| Round 1: B → C → A → C | 402/55 → 402/55 → 152/26 → 402/55 | B 6 (with `glass`), C 6, A 4 | 26 / 26 / 24 / 26 | 123/43/7/28 for B/C; 119/41/7/28 for A |
| Round 2: the same | identical to round 1 | identical | identical | identical |

- After each step the file equals its source.
- Nothing is left over: the material set switches exactly, and `assets/models` holds the same 29 files throughout.
- `hd2d_error` is None every time.
- The plan text is right ("152 -> 402 triangles.", "Same shape and collision").

### 4. Hero sheets (`hero_check.json`)

| | H0 | H1 | H2 | H3 | H4 |
|---|---|---|---|---|---|
| Mode / size / alpha | RGBA 128×192 {0, 255} | same | same | same | same |
| Feet row, all 16 frames | 47 | 47 | 47 | 47 | 47 |
| Frames touching a cell edge / blank | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Figure height / width (px) | 40–41 / 12–18 | 42–44 / 12–23 | 42–44 / 12–23 | 42–44 / 12–23 | 43–45 / 14–25 |
| `character_clips(…)` identical to H0 | — | yes | yes | yes | yes |

- The auto collider is `footprint(32, 48)` = `{w: 19, h: 12, offset_y: −18}` for every sheet; in game the AABB is 19×12 for both H0 and H4.
- `build_hero_1b.py`, run from a copy, reproduces h2, h3 and h4 **byte-identically**.

### 5. Performance and GPU lifetime (`perf/perf.json`)

5 interleaved rounds; each is a fresh hidden game at 1280×720, 300 frames, player beside the door.

| | A (= H0) | B | C | H4 |
|---|---|---|---|---|
| Frame ms, median of round medians | 5.03 | 5.07 | 5.07 | 5.01 |
| Rounds | 6.36 4.92 2.85 5.10 5.03 | 8.11 5.01 3.50 5.07 5.13 | 7.98 5.04 4.97 5.12 5.07 | 7.90 7.55 4.98 5.01 5.00 |
| HD-2D renderer CPU, steady rounds | 1.34 | 1.41 | 1.42 | 1.35 |
| Draw calls / shadow draws | 29 / 28 | 31 / 30 | 31 / 30 | 29 / 28 |
| Triangles | 1,372 | 1,622 | 1,622 | 1,372 |
| Renderer texture bytes | 137,216 | 141,316 | 156,616 | 137,216 |
| Static buffer bytes | 110,472 | 128,448 | 128,448 | 110,472 |
| GL texture / FB / program: load → 4 reloads → close | 40/6/27 → 40/6/27 → 5/3/18 | 42/6/27 → 42/6/27 → 5/3/18 | the same as B | the same as A |

- The real cost of B and C is +2 draws, +250 triangles and +18 KB of buffers. Textures add +4 KB for B and +19 KB for C. The renderer's CPU time is about 0.07 ms higher. The frame cost is otherwise noise.
- Textures, framebuffers and programs never drift, in any variant, through reloads or after closing.
- The live **buffer** count drifts with Python GC in every variant, the starter included (for example 2,517 ↔ 2,667 ↔ 2,821). This is the known behaviour, not a leak from this pilot.

### 6. Hygiene and cost controls

- **Tests:** `pytest -q -p no:cacheprovider tests/test_generated_asset_hygiene.py tests/test_pixellab_budget.py` gives **7 passed**.
- **`raw/`:**
  - It is ignored (`.gitignore:39`).
  - 0 files are tracked.
  - It never appears in history.
- **Secret scan** (`secret_scan.py`, booleans and counts only):
  - 1 account id was found in `raw/`.
  - All 59 files under `pilot_m17` outside `raw/` were scanned, binaries and zips included. None holds the account id or the token, in plain text, upper case, halves or base64.
  - No text file holds a URL containing a UUID.
  - Across the repo's tracked and untracked (not ignored) files: 0.
  - Across blobs reachable from HEAD: 0.
- **Budget probe** (D1, D2):
  - **Correct:**
    - Concurrency: 40 threads on a budget of 20 gave 20 accepted, 20 refused and 20 ledger entries.
    - Settle twice, settle unknown and release after settle are all refused.
    - Unknown endpoint, a QA name and re-init are refused.
    - A stale lock is refused after the timeout: it fails closed but needs a hand removal.
  - **Not correct:**
    - Negative, zero and fractional units are accepted.
    - Negative `used` is accepted.
    - Any caller can **claim a generation agent's name**: the agent string is self-declared.
    - `release` returns the budget on the caller's word.
    - Nothing stops an agent from calling PixelLab without reserving, because the token is in every agent's environment. The ledger is advisory.
  - **Robustness (minor):**
    - `_locked` writes the ledger in place, not atomically. A crash mid-write leaves invalid JSON, every call then fails with `JSONDecodeError`, and `init` refuses to recreate it.
    - `status()` reads without the lock.
- **Ruff and mypy:** `ruff check` and `ruff_gate` are ok. The mypy gate fails: see D4 and D5.

## Technical verdict per element

| Element | Verdict |
|---|---|
| **B model** (`cottage_m17_geo.glb`) | **PASS.** Valid, reproducible, collision byte-identical, 0 cross-material coplanar faces, framing fully outside, flat panes survive every path. Minor: D6. |
| **C model** (`cottage_m17.glb`) | **PASS** (technical). As B, with embedded PixelLab images pixel-identical to their sources. Minor: D6. Licence and catalogue: D9; shipping is the owner's call (NOTICE). |
| **H2** | **PASS.** Format, feet, cells, clips, collider and byte-exact rebuild are all correct. |
| **H3** | **PASS.** Same. |
| **H4** | **PASS.** Same. The figure is 45 px at most and 25 px wide at most, inside the 32×48 cell. |
| **Tool** (`m17_visual_pilot.py`) | **PASS with a reporting caveat.** It works: hidden windows, identical variant setup, and GL counts recorded. Its single-run frame cost is noise (D8). |
| **Hygiene** | **CONDITIONAL.** No leak today: 0 hits in files, the tree and history. The guards have gaps: CI can't detect a bare token or account id (D3), and the local mypy gate is red because of ignored `raw/scripts` (D4) and the hidden `build_*` files (D5). |
| **Budget** (`pixellab_budget.py`) | **FAIL until D1 and D2 are fixed.** Locking and refusals work, but negative or zero units, negative usage and the sanitize gaps defeat its two stated guarantees. Both fixes are a few lines each. Agent identity and API use remain advisory by design; document that. |
