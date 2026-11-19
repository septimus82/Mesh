# Studio tileset import never crosses project ownership

#462, the follow-up named in `p1_studio_save_ownership.md` §6. Base: `redesign/visual-editor` at `3c82c6c9` (#523
merged: its reviewed head `be14c8ff`, tree identical).

**Verdict: READY FOR INDEPENDENT REVIEW.**

Evidence: `tileset_import_ownership_evidence/`.

## 1. Production path and its writes

Import tileset panel -> its Import button -> `Studio.import_tileset` (`engine/studio.py`) -> `Project.import_tileset`
(`engine/studio_project.py`). Straight away, not as part of a save, it wrote, in this order:

1. the folder `assets/tilesets` (made if missing);
2. `assets/tilesets/<name>.png` (the picture);
3. `assets/tilesets/<name>.json` (its description);
4. `_add_tileset_to_maps`: the map file of every room the world lists that doesn't reference the tileset yet, each
   written as soon as it was worked out.

Nothing was checked against Studio's hold on the project. It is the only caller; `tooling/studio_workflow_polish.py` and
`tests/test_studio_project.py` call `Project.import_tileset` directly without an owner and are unchanged.

## 2. Reproduction (before: `before.json`, `before_gpu.txt`)

Disposable projects: the outer game's world lists the start room of `packs/region2`, a scaffolded Mesh project of its
own, whose Studio (a separate process) holds its OS lock; the outer project held as Studio holds it.

- `repro_tileset.py.txt`, through `Project.import_tileset` as Studio called it: the import returned success, created
  `assets/tilesets/rocks.png` and `.json`, and **changed** both the outer map and
  `packs/region2/packs/core_regions/maps/start.json`: the child's map gained
  `{"firstgid": 17, "source": "../../../../../assets/tilesets/rocks.json"}`, a tileset outside its own project, while
  its Studio held the lock.
- Two real Studio windows (`test_studio_tileset_ownership_gpu.py` on the base): the outer Studio said
  `Imported Rocks: 2 tiles. Pick one and paint.`

## 3. Correction

- `Project.import_tileset(..., owner=None)`: every destination is worked out first: the picture, the description, and
  the updated map files (`_maps_with_tileset`, which replaces `_add_tileset_to_maps` and only computes, each map file
  once). Each is checked with the shared rule, `owner.owns(...)` (`Ownership`, R2/R5: inside the held project and not in
  another Mesh project nested in it, after resolving links). Any foreign destination refuses the whole import before
  the folder, picture, description or any map file is written:

  > Not imported: packs/region2/packs/core_regions/maps/start.json is in another Mesh project than the one held
  > (...game), so nothing was written: that project has its own owner.

  It is not a filter: foreign map files are never skipped while the rest is imported.
- `Studio.import_tileset` passes `owner=self.ownership`, the hold `open_studio` took. Studio's existing handler shows the
  message as a refusal and keeps the panel and form open; the project's in-memory state is untouched (the import
  changes none).
- No new lock, no transaction: the writes after the check are as before (a disk failure part way is as before).

## 4. Tests

| File | Covers |
|---|---|
| `tests/test_studio_tileset_ownership_gpu.py` (real windows, GL lane) | two Studio processes, each holding its own lock; the import is the panel's own action. The nested project's Studio imports into its own project (two independent writers); the outer Studio's import (its own picture, description and map allowed, the nested map not: a mixed set) is refused with the message, every file of both projects byte-identical, no picture or description; both locks still their Studio's pid; both Studios' unsaved edits kept; then an ordinary project imports normally (picture, description, map) |
| `tests/test_tileset_import_ownership.py` (default lane, real OS locks; the nested project's Studio its own process) | the refusal and its exact message, byte-identical files, the outer edit still unsaved (revision and room unchanged), the child's hold and unsaved edit; refused also when the nested project isn't open; ordinary imports write every destination; the nested project under its own lock imports into itself while the outer one is held |
| `tests/studio_owner_process.py` | new `import_tileset JSON` command (`real`): the form filled, then Studio's Import action |

Before (base `3c82c6c9`): the real-window test fails at the outer import (`before_gpu.txt`). After: all 4 pass
(`after_tests.txt`); the repro records the refusal and no file created or changed (`after.json`).

Fault injection (`faults.json`, `mutate_tileset.py.txt`), the two new files and `test_studio_project.py`: **5/5
caught**, each file put back byte for byte:

| Mutation | Failed |
|---|---|
| Studio's import without its ownership | the real-window test |
| the destination check refuses nothing | 3 (both new files) |
| map files left out of the check | 3 |
| foreign map files skipped, the rest imported (success) | 3 |
| the picture and description written before the check | 3 |

## 5. Validation

Local, Windows, Python 3.13, `-W error`:

- every default-lane test importing `engine.studio` or `engine.studio_project`, plus the tileset, map, Studio ownership,
  room-file ownership, room undo/save, scene creation, project save, prefab catalogue, authoring session, R4/R5
  remediation, import-boundary, exception-policy, logging, type-ignore and test-lanes tests: **1166 passed, 17 skipped,
  0 failed**. (One behaviour-neutral edit, a redundant guard removed from `_maps_with_tileset`, landed while that run
  was going; the tileset tests then ran again on the final code: **17 passed**.)
- real window (`MESH_GL_SMOKE=1`): the new test, `test_studio_save_ownership_gpu`, `test_studio_project_ownership_gpu`,
  `test_studio_workflow_polish_gpu` (imports a tileset), `test_studio_panel_scroll_gpu` (the import panel),
  `test_studio_room_undo_save_gpu`, `test_room_file_ownership_gpu`, `test_studio_workspace_gpu`: **68 passed**.
- `tooling.ruff_gate` ok, `tooling.mypy_gate` ok, exception-policy scan 482 silent (unchanged), no new import-boundary
  entry.

CI and Extended first attempts (failures kept, nothing rerun) are in the PR's results comment.

## 6. Limits

- A failure part way through the writes after the check (a full disk) can leave some written, as before; the import is
  not transactional (as briefed).
- A project changing between the check and the writes is not detected; the check runs immediately before, under
  Studio's lock (as R5's save check).
- Untouched, as briefed: stale-content plan undo, MCP routing and light-index translation.
