# Milestone 17: cottage integration (Stage 1B accepted)

**Ready for owner review.** At the owner's decision on Stage 1B, the HD-2D starter kit's cottage now has the
improved geometry of Stage 1B's variant B, built with the existing starter textures only, and its roof UVs corrected.

- **What changes:**
  - one kit model (with its preview and catalog entry);
  - the launcher's HD-2D template picture;
  - the builder.
- **What is preserved:** collision, floors, the door, navigation, the cutaway, Studio reimport, export and save/load all behave as before, and existing projects are untouched.
- **What is not adopted:** no PixelLab or other generated art. The rejected hero candidates and the starter characters are untouched.
- **The experimental PRs:** #370 and #371 are not merged and stay as review records.

## What changed

| File | Before | After |
|---|---|---|
| `assets/hd2d_starter/models/cottage.glb` | 35,568 B, `7b4c20ff…`, 152 triangles, 4 materials | 72,148 B, `a3677bfc…`, 402 triangles, 6 materials (cobbles and a flat dark pane added) |
| `assets/hd2d_starter/previews/cottage.png` | `048d9e70…` | `fac6ff48…` |
| `assets/hd2d_starter/catalog.json` | kit version 1 | kit version 2; the cottage's note: "A timber-framed cottage on a cobbled plinth, with windows; walk inside." Collision and floor facts unchanged. |
| `assets/templates/hd2d_rpg.png` | `a5ff6fbd…` | `9c1e631b…` (the new cottage's corner at the left edge) |
| `assets/hd2d_starter/PROVENANCE.md` | | names `build_kit()` and the Blender version |

The other 13 kit models, the textures, every sprite (the starter hero included), `pyproject.toml`'s allow-list and
`MANIFEST.in` are unchanged. No filename changed, so packaging is unaffected.

**The builder.**

- `tooling/hd2d_assets/build_cottage.py` gains `build_kit()`. It calls the unchanged `build()`, then refines it, and `build_starter_kit.py` uses it for the kit.
- The Stage 5B pipeline demo cottages (`tooling/hd2d_assets/cottage.glb` and `cottage_v2.glb`, from `build()`) still rebuild byte-identically, so the reimport demonstration and its tests are untouched.
- `build_kit()` is Stage 1B's variant B ported exactly. The first build was byte-identical to #371's `cottage_m17_geo.glb` (`1e7ce0ae…`), so every Stage 1B QA result applies to it.
- On top of B:
  - **window frame gaps:** the window frame pieces abut instead of stopping 2 mm short, so the 4 mm gaps that showed the pane are gone (Stage 1B tech QA D6);
  - **dark frame edges:** each frame piece's texture is shifted to the middle of a timber board, so no dark board line runs along a 2 px frame edge (this QA's D1).

**Refinements, all in starter textures:**
- a cobbled plinth to 0.85 m in place of timber to 1.3 m;
- a timber sill ring and L-shaped corner posts with vertical grain, wholly outside the walls;
- two front windows: a timber frame and cross mullion over a flat dark pane, 2 cm out from the wall;
- no faces hidden inside the model (coplanar faces of different materials: 60 before, 0 now);
- the shingles run up the slope at 32 px/m.

**The roof.** The inverted roof was a Stage 1 pilot mistake. The starter roof was already upright, and so is the
adopted one: measured on renders, the shingles run up the slope, the same way up as the original. The adopted
mapping also corrects the density along the slope from 27.9 to 32 px/m. The shop's and `roof_4m`'s roofs keep the
flat mapping: changing them wasn't in scope, and there's no evidence of a defect. As a result, the cottage's roof now
differs slightly from the shop's next to it.

**New and existing projects.**

- A project is given the kit only when it is created: `engine.hd2d.catalog.install_kit` never overwrites, and nothing upgrades an existing project.
- New projects record the source "Mesh HD-2D starter kit 2" and each model's SHA-256.
- The template test now also checks that a new project's models are the kit's current files.
- In the clean-install acceptance, every project created by the installed engine has the new cottage (matching hash), and so does its exported game bundle.

## Gameplay-scale before and after

Rendering conditions:
- Mesh's own renderer, hidden windows;
- 1280×720, the template's 12° camera, the same sun, lamps and walk;
- the starter hero in both;
- 1:1 crops (the art at 2×), not resampled.

The renders come from the M17 comparison harness on #371's branch (`tooling/m17_visual_pilot.py`), with the shipped cottage against this branch's kit cottage swapped in under the same structure id.

![Before and after beside the cottage door, gameplay scale](milestone17_cottage_integration_evidence/integration_cottage.png)

Close up (1:1 at 4×):

![Before and after, close up](milestone17_cottage_integration_evidence/integration_cottage_close.png)

More pictures:
- [the path](milestone17_cottage_integration_evidence/integration_path.png);
- [the village centre](milestone17_cottage_integration_evidence/integration_centre.png);
- [walking past both at 1:1](milestone17_cottage_integration_evidence/integration_walk.webp);
- the measurements in [`integration.json`](milestone17_cottage_integration_evidence/integration.json).

| | Before | After |
|---|---|---|
| Draw calls / triangles / texture bytes | 29 / 1372 / 241,664 | 31 / 1622 / 245,764 |
| Hero height and visible pixels at the cottage, path and centre | 82 / 83 / 82 px; 1721 / 2431 / 2392 | identical |
| Hero edge contrast at the door | 32.8 | 33.9 (cobbles behind it, not dark timber) |

## Independent QA

A read-only QA agent re-measured everything at commit `11d0b1d` with hidden windows and headless Blender: [full report](milestone17_cottage_integration_evidence/cottage_integration_qa.md). **Verdict: ready for owner review**, with no blocker or major defect.

- **Reproducibility:** all 14 kit models, both demo cottages, the catalog, the 14 previews and the template picture rebuild byte-identically.
- **GLB:** valid, and read with no warnings. NEAREST sampling and 32 px/m on every textured face, the roof included. No degenerate triangles, nothing drawn inside the walls, lintel, slab or room, and window joints closed.
- **Flat pane:** it renders correctly in the reader, the renderer, the Studio catalog and preview, and `mesh export`.
- **Collision and navigation:** the `col_` nodes are byte-identical. 0 of 1,450 floor queries differ. Wall stops and door entry are identical, and so are positions walking into each wall, through the door, round the room and out.
- **Cutaway:** no new z-fighting. Behind the cottage there are 63–184 fewer depth-flickering pixels than before.
- **Studio:** reimport new → old → new → old → new gives exact file matches, nothing left over and stable GPU counts.
- **Export and save/load:** the bundle holds the new cottage, and save/load keeps the player and the structure entry.
- **Existing projects:** a simulated older project opened in Studio and the game had 0 files changed, and there is no migration path.
- **Performance:** +2 draw calls, +250 triangles, +4.1 KB of textures and +18 KB of buffers; about 0.1–0.15 ms per frame in steady state. Textures, framebuffers and programs don't grow across reloads or close; only the pre-existing GC-timed buffer drift appears.
- **Suites:** fast tier 4605 passed, GPU files 111 passed, ruff gate ok. mypy shows only the two pre-existing local `tooling/hd2d_lab` errors.

Fixed after QA, and re-verified on the final commit:

| QA finding | Fix |
|---|---|
| D1 (minor): each window's outer frame post picked up the timber's dark board line | `_mid_board()` centres each frame piece on a board. A 4× crop shows even frames. Collision is still byte-identical, and the build is reproducible (`a3677bfc…` twice). |
| D2 (minor): the builder's docstring linked a report absent from this branch | It now links this report. |
| D3 (minor): the budget accepted an approved total of NaN or ∞, which disabled the cap check | The total and every cap must be finite and above 0; tests added. |
| D4 (minor): settling a usage of ∞ blocked the ledger | Usage must be finite and ≥ 0; tests added. |
| D5 (minor): the sanitizer kept creator fields, URLs or id paths used as keys, percent-encoded storage paths, and `Bearer …` values when the token isn't in the environment | All four are now removed; a test is added. A bare id under an ordinary key such as `id` is still kept, because it can't be told from a job id. The hygiene test is the backstop for that. |
| D6 (minor): the hygiene test missed `raw/` outside `tooling/hd2d_assets/`, `.log`, `.html`, `.js` and similar files, and a token written without hyphens | Any `raw/` folder is now ignored and may never be tracked. Six more text types are scanned. Digests are taken without hyphens, so either form is caught. The digests still recognise exactly the 10 raw files known to hold the account id. |

**Smaller notes, not changed:**
- Through the cutaway, the room's lower inside walls show cobbles where they showed timber.
- The floor slab's ground-level flicker band predates this change.
- Studio's reimport keeps the old licence line; that's tracked in `docs/asset_licensing.md`.
- The fast tier leaves two save files in an ignored `saves/` folder; that predates this change.

## Safeguards ported from Stage 1B

- **`tooling/pixellab_budget.py`, one shared reserve-before-request budget:**
  - Unknown endpoint costs are refused, and so is anything over budget, any non-positive or non-finite amount, and any agent not in the ledger. QA agents are never listed.
  - Results are stored sanitized.
  - **New: per-agent caps.** Each generation agent's cap is fixed when the ledger is made, and the caps never exceed the approved total. A subtask an agent delegates reserves under that agent's name, since any other name is refused, so delegating can't add budget.
  - QA's attack tests held: 40 concurrent reservations on a budget of 20 accepted exactly 20, split 15 and 5.
- **Hygiene:**
  - `raw/` folders are git-ignored;
  - `tests/test_generated_asset_hygiene.py` (its full scan is integration-tier: it reads every tracked text file, about 2.6 s, so it runs in CI's whole-suite pytest step rather than the time-budgeted fast tier) rejects tracked raw records, storage or signed URLs containing ids, bearer-token literals, and the owner's token or account id by digest.
- **mypy gate:** `tooling/mypy_gate.py` skips git-ignored folders as well as untracked ones.

## Licensing

`docs/asset_licensing.md` records the decisions and requirements:
- no PixelLab-generated asset is in the starter kit or the allow-list;
- the open requirements: written clarification from PixelLab, a Mesh code licence with separate starter-asset usage terms, and provenance for any third-party or AI-generated asset;
- the safeguards.

The clarification email is prepared from the licence review's draft (#371, `licence_review.md` §4.2) and **has not been sent**. Sending it needs the owner's explicit confirmation.

## CI investigation (#371)

#371's pull-request run passed while its push run failed `verify-all`. Both tested the same tree (`990db11`). The push
run's failures were enforced fixed-millisecond budgets on runners the speed advisory measured at 1.12× (Windows) and
1.20× (Linux) the median runner:

| Step | Duration | Advisory's expected range | Enforced threshold |
|---|---|---|---|
| `pytest-fast` | 130.0 s | 104.7–153.4 s | 121.8 s |
| `exception-policy-scan` | 3.69 s | 3.25–4.12 s | 3.56 s |

The PR run's runners were 0.60–0.67×. A re-run with budgets unchanged passed. The only real difference from the
updated base is that the stacked branches predate #369, so their pushes still trigger the retired `build.yml`. No test
or budget was changed.

**On this PR's own CI.**

- The first push run was fully green.
- The pull-request run's Windows `tests` job failed the same fixed `pytest-fast` budget twice, on runners measured at 1.22× and then 1.34× the median: 131.7 s and 130.7 s against 121.8 s. The advisory judged both within range for those speeds (120.7–176.8 s at 1.34×).
- Part of the time was this branch's: the hygiene test's full scan reads every tracked text file (about 2.6 s locally). It is now `integration`-tier. It still runs on every PR in CI's whole-suite pytest step, but no longer in the time-budgeted fast tier.
- No budget was changed.

## Tests on the final commit

- fast tier;
- the 17 GPU files (`MESH_GL_SMOKE=1`);
- the HD-2D template, catalog, cutaway and launcher tests;
- the clean-install wheel test (`tests/test_wheel_bundles_engine_data.py`, slow; run without `PYTHONPATH`, which would make pip build from the repo's `build/` folder);
- the installed-engine acceptance (`tooling/hd2d_install_acceptance.py`): wheel = allow-list, 178 files; driver exit 0;
- the ruff and mypy gates.

Results are in the PR.
