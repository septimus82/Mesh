# P1: Mesh Studio saves never cross project ownership

#462. Defect independently reproduced in the R4/R5 review: an outer Mesh Studio's Ctrl+S overwrote a room of a nested
Mesh project that another Mesh Studio owned, and said "Saved". Base `redesign/visual-editor` at `ed42bfd4`.

**Verdict: READY FOR INDEPENDENT REVIEW.**

Evidence: `p1_studio_save_ownership_evidence/` (`before.txt`, `after.txt`, `faults.json`, `mutate_p1.py.txt`).

## 1. Root cause

`Studio.save` called `self.project.save()` without an owner. R5 (remediation B) gave `Project.save(owner=...)` a
destination check (every file it is about to hand to `save_documents` must be covered by the lock held:
`Ownership.owns`), but only writers outside Studio passed their lock. Studio holds a lock on its own project
(`open_studio`, R2), yet its save wrote every dirty room the world lists, wherever that room is: a room in a content pack
that had since become a Mesh project of its own was written behind that project's Studio. The save service's
outside-change guard only kept the child's version beside the room (`.outside-change.bak`); the room itself was
overwritten and Studio reported "Saved 1 file(s)".

## 2. Save entry points

Every Studio save goes through the one method `Studio.save` (`engine/studio.py`): Ctrl+S (`on_key_press`), Ctrl+S
while typing in a box (the same handler's field branch), the toolbar's Save button (`_button("Save", self.save)`), and
Save in the close question (`_close_choice("save")`). Nothing else in Studio calls `Project.save`.

## 3. Correction

`engine/studio.py`, `Studio.save`:

- `self.project.save(owner=self.ownership)`: Studio passes the hold it already has (no new lock, no new check). Any file
  of another Mesh project refuses the whole save before anything is written (`not_this_project`); the edits stay
  unsaved, the rooms stay dirty, undo and redo stay as they were (`Project._refused`).
- The refusal message: Studio's existing "Couldn't save: ..." with R5's reason, plus "Your changes are still here,
  unsaved." (previously added only to failures after the validate stage; this refusal is in that stage, and the changes
  are kept):

  > Couldn't save: packs/region2/packs/core_regions/scenes/start.json is in another Mesh project than the one held
  > (...game), so nothing was saved: that project has its own owner. Your changes are still here, unsaved.

A Studio with no ownership (`Studio(window, project)`, tests only; `open_studio` always passes one) saves as before.

Test seams updated to the new call (no behaviour or assertion changed): two `Studio.save` stand-ins
(`tests/test_project_save_transaction.py`, `tests/test_prefab_catalogue_safety.py`) gain `ownership=None`;
`tooling/studio_workflow_polish.py`'s save counter passes the save's arguments through.

## 4. Reproduction and regression

`tests/test_studio_save_ownership_gpu.py`: disposable projects (`create_project`); the outer world lists the room of
`packs/region2`, itself a scaffolded Mesh project. Two real Mesh Studio processes, each a hidden window
(`open_studio` through `tests/studio_owner_process.py real`), each holding its own OS lock; saves are the window's own
Ctrl+S key event (new helper commands `room PATH` and `ctrl_s`).

1. The outer Studio edits the nested room ("Outer Old Edit").
2. The nested project's own Studio edits and saves it with Ctrl+S: saved (a nested project saves through its own Studio).
3. The child makes another unsaved edit.
4. The outer Studio's Ctrl+S: refused; nothing is written anywhere (the whole outer tree, nested files included,
   byte-identical; no `.outside-change.bak`); both locks still held by their own Studio's pid; the child keeps its
   unsaved edit; the outer Studio keeps its edit and stays dirty.
5. Mixed save: the outer Studio also edits its own room; Ctrl+S refused whole, the valid outer room not written either.
6. Undo both; an edit of the outer project's own room saves normally ("Saved 1 file(s)."), the nested files untouched.

| | Result |
|---|---|
| Before (`ed42bfd4`, `before.txt`) | fails at step 4: `Saved 1 file(s). Something else had changed packs/region2/.../start.json ...`, not dirty: the nested room overwritten |
| After (`after.txt`) | passes |

`before.txt` was recorded before one later test-only line (step 6 goes back to the outer room after the undos, which
return to the room they changed); the failing step and its line are unchanged.

Fault injection (`faults.json`): **5/5 caught**, each file put back byte for byte.

| Mutation | Caught at |
|---|---|
| Studio's save without its ownership | step 4 |
| the refusal doesn't say the edits are kept | step 4 (message) |
| `Project.save`'s destination check refuses nothing | step 4 |
| a refused save writes the valid files and skips the foreign one | step 4 |
| only an all-foreign save is refused; a mixed one drops the foreign file | step 5 (mixed) |

## 5. Validation

Local, Windows, Python 3.13, `-W error`:

- Studio, R2 ownership, authoring-session, project-save and remediation suites (`test_studio_project*`,
  `test_studio_room_undo_save`, `test_studio_revision_identity`, `test_studio_object_identity`, `test_studio_ai_*`,
  `test_studio_undo_history_sharing`, `test_studio_canvas`, `test_room_file_ownership`, `test_safe_scene_creation`,
  `test_project_save_transaction`, `test_authoring*`, `test_project_ownership_root`, `test_mcp_project_ownership*`,
  `test_ai_write_paths*`, import-boundary, exception-policy, logging, type-ignore and test-lanes contracts): **403
  passed, 2 failed, 9 skipped** on the first run.
  - `test_project_save_transaction::test_studio_says_the_save_failed...`: its `Studio.save` stand-in had no
    `ownership` (this change's; fixed as above, together with the same stand-in in `test_prefab_catalogue_safety`).
  - `test_studio_project_ownership::test_a_second_studio_opening...`: the windowless Studio process exited reading its
    command file (`PermissionError` on `0002.cmd` just after the test renamed it into place), while the static gates ran
    beside the suite. Pre-existing helper code this change doesn't touch; the test passed alone and in the rerun.
  - After the fixes: the two files **65 passed**, `test_prefab_catalogue_safety` **10 passed**; every default-lane
    test importing `engine.studio`: **130 passed**.
- Real window (`MESH_GL_SMOKE=1`): the new test, `test_studio_project_ownership_gpu`, `test_studio_room_undo_save_gpu`,
  `test_studio_revision_identity_gpu`, `test_studio_object_identity_gpu`, `test_studio_ai_write_set_gpu`,
  `test_room_file_ownership_gpu`, `test_ai_write_paths_gpu`, `test_studio_workflow_polish_gpu`,
  `test_studio_workspace_gpu`, `test_studio_3d_selection_gpu`, `test_studio_panel_scroll_gpu`: **75 passed, 3 errors**
  first (the three `studio_workflow_polish` Ctrl+S cases: its save counter took no arguments, this change's; fixed),
  then `test_studio_workflow_polish_gpu` **12 passed**.
- `tooling.ruff_gate` ok, `tooling.mypy_gate` ok, exception-policy scan 482 silent (baseline unchanged), no new
  import-boundary entry.

CI and Extended first attempts (failures kept, nothing rerun) are in the PR's results comment.

## 6. Limits

- Studio's tileset import (`Project.import_tileset` -> `_add_tileset_to_maps`) writes the map file of every room the
  world lists at once, outside `save`; a listed room in a nested project gets its map file rewritten there. Not a save
  entry point and not changed here (follow-up).
- A project changing *during* `save_documents` itself is not detected (as for R5's check: it runs immediately before,
  under the lock).
- Untouched as briefed: stale-content plan undo, MCP light routing.
