# R4/R5 Remediation B: ownership and undo preflight gaps

#462. Three findings of the independent verification of remediation A (`r4_r5_remediation_a.md`). Both PRs stay
drafts.

**Verdict: READY FOR INDEPENDENT REVIEW.**

Starting heads: #521 `f9478ae8`, #522 `0bd783f9`; base `ee1986e0`. Evidence: `r4_r5_remediation_b_evidence/`.

## 1. Root causes and corrections

| Finding | Root cause | Correction | Where |
|---|---|---|---|
| **1 (P1)** MCP adapted authoring crosses ownership | `authoring_session.apply` owns the project it is given, then `Project.save` writes every changed room the *world lists*, wherever it is: a room in a pack that became its own Mesh project was saved under the outer lock. Remediation A confined `AIOps`, not this route. | `Project.save(owner=...)`: before anything is written, every document it is about to write (the exact list it hands to `save_documents`: maps, rooms, world, prefabs) must be covered by the lock held (`Ownership.owns`); otherwise the whole save is refused (`not_this_project`, `refused()`: nothing written, the edits stay unsaved). `authoring_session.apply` passes the lock it holds, taken before the project is read, so the destinations are found and checked under it. Studio's own saves (no owner) are unchanged. | #522: `engine/studio_project.py`, `engine/authoring_session.py` |
| **2 (P2)** undo accepts folders where files are needed | the preflight checked where entries point, not what is there now | the whole-manifest preflight also requires, for every entry before the first deletion or restoration: a file or nothing where a created file is deleted or a modified file restored (never a folder); every existing folder above a restored file a folder; the modified file's copy a file inside the backup. Missing destinations and valid backups restore as before. Any bad entry: nothing changed, exit 1. | #521: `engine/tooling/plan_executor.py` |
| **3 (P2)** identity changes after acquisition | `in_project(root, target)` rediscovered `root`'s project at every check: a nested project whose `config.json` was removed rediscovered as its parent, and the parent's files were accepted under the child's lock | `acquire` captures what the lock is the lock of (`Ownership.project`: the root if it is a Mesh project then, else None); `in_project(root, target, project)` takes it explicitly and `Ownership.owns(target)` is what writers ask (a released lock covers nothing). Writers stop once the project changed: `AIOps(owner=...)` per path, `PlanExecutor(owner=...)` per file and before its own records (backup manifest, history: `records_allowed`), undo before each deletion or restoration. A folder that began in no project keeps covering its files until it becomes a project. | shared commit `cb837dfe` (`engine/editor/project_ownership.py`, `engine/ai_ops.py`), callers in #521 and #522 |

No new lock or lock identity; one discovery rule (`project_root`); `AIOps` no longer imports the editor package
(`owner` is the `Ownership` object). No import-boundary entry or exception-policy change.

## 2. Integration

The identity change is one commit (`cb837dfe`) on the shared branch `fix/project-ownership-root`, merged into both
PRs as remediation A's was; each PR then adapts its callers and adds its finding. Combined (base + #521 + #522):
clean, and `git merge-tree` gives the identical tree in both orders.

## 3. Before and after

`repro_b.py.txt`: disposable scaffolded projects; Studio and lock holders their own processes; production entry
points. Before: `before_r4.json` (#521 `f9478ae8`), `before_r5.json` (#522 `0bd783f9`). After: the combined tree
(`after_integration.json`) and each PR alone (`after_r4.json`, `after_r5.json`).

| Case | Before | After |
|---|---|---|
| 1. MCP `add_light` (adapted route) on the outer world's room in `packs/region2`, now its own project, open in Studio (unsaved work) | ok: `packs/region2/scenes/cellar.json` **written** behind its Studio | refused (`save_failed` / `not_this_project`), every file identical, Studio's work kept; a normal room still saves |
| 2a. undo: created `made.json`, then a created path that is now a folder | `made.json` **deleted**, then an error (exit 1) | refused, nothing changed, exit 1 |
| 2b. undo: a modified path that is now a folder | its copy put **inside** the folder; "Undo successful", exit 0 | refused, nothing changed, exit 1 |
| 2c. undo: valid created and modified entries plus one whose folder is a file | the room **restored** and `made.json` **deleted**, then an error | refused, nothing changed, exit 1 |
| 3. console `ai_job` / MCP fallback holding the nested project's lock, its `config.json` removed mid-write, Studio on the outer project | applied: the outer project's file **written** | refused per operation ("another Mesh project than the one held"), nothing written |

## 4. Tests

| File | Covers |
|---|---|
| `tests/test_project_ownership_root.py` (shared, +1) | a lock's identity captured: the nested `config.json` removed while held (Studio holding the outer project in another process): `owns` refuses, `AIOps(owner=...)` writes nothing; a loose folder that becomes a project; a released lock covers nothing |
| `tests/test_ai_write_paths_remediation_b.py` (#521, 10) | the two reviewed undo cases through `mesh undo-last-plan` (CLI subprocess); one bad entry among valid ones (a file above, a copy that is a folder, a missing copy), byte-for-byte; missing destinations and valid backups still restore; `ai_job` and `apply-plan` stop once their project stopped being one (nothing written, the plan's records included); an undo stops before its first write if the project changes after its preflight |
| `tests/test_mcp_project_ownership_remediation_b.py` (#522, 5) | Astra's scenario (Studio holding the nested project, unsaved work) through MCP `apply_ops`; the same through `authoring_session.apply`; a normal room and the nested project under its own lock still save; both MCP routes with the marker removed mid-write |

On the starting heads (`regression_before_r4.txt`, `regression_before_r5.txt`): #521's file **6 of 10 fail** (the
two reviewed cases, the folder-above case, both mid-write cases, and the shared identity test); the four that pass
are the controls and the cases remediation A already refused (a missing copy, a copy that isn't a file). The
mid-undo test was added later. #522's file **4 of 5 fail**; the normal-room control passes.

Fault injection on the combined tree (`faults.json`, `mutate_r45b.py.txt`):

| Mutation | Caught by |
|---|---|
| finding 3: identity rediscovered from the held root (`engine/editor/project_ownership.py`) | 6 failed, 35 passed, 1 skipped: test_a_lock_never_covers_another_project_after_a_marker_changes, test_a_nested_projects_lock_covers_nothing_once_it_stopped_being_a_project, test_a_plan_stops_once_its_project_stopped_being_one, test_an_undo_stops_writing_once_its_project_stopped_being_one, test_the_console_stops_once_its_project_stopped_being_one |
| finding 3: a released lock still covers files (`engine/editor/project_ownership.py`) | 1 failed, 40 passed, 1 skipped: test_aiops_held_to_a_project_writes_its_files_and_no_nested_projects |
| finding 1: Project.save checks nothing (`engine/studio_project.py`) | 3 failed, 38 passed, 1 skipped: test_a_nested_projects_lock_covers_nothing_once_it_stopped_being_a_project, test_adapted_authoring_never_saves_a_room_of_a_nested_project, test_the_persistence_path_refuses_it_whoever_calls_it_and_whether_or_not_the_nested_project_is_open |
| finding 1: authoring_session doesn't pass its lock to the save (`engine/authoring_session.py`) | 3 failed, 38 passed, 1 skipped: test_a_nested_projects_lock_covers_nothing_once_it_stopped_being_a_project, test_adapted_authoring_never_saves_a_room_of_a_nested_project, test_the_persistence_path_refuses_it_whoever_calls_it_and_whether_or_not_the_nested_project_is_open |
| finding 2: a folder accepted where a file is deleted or restored (`engine/tooling/plan_executor.py`) | 2 failed, 39 passed, 1 skipped: test_a_created_file_that_is_now_a_folder_refuses_the_undo_before_anything_is_deleted, test_a_modified_file_that_is_now_a_folder_is_never_copied_into_it |
| finding 2: a file accepted where a folder is needed above a restored file (`engine/tooling/plan_executor.py`) | 1 failed, 40 passed, 1 skipped: test_one_bad_entry_among_valid_ones_refuses_the_whole_undo |
| finding 3: undo doesn't check again before each write (`engine/tooling/plan_executor.py`) | 1 failed, 40 passed, 1 skipped: test_an_undo_stops_writing_once_its_project_stopped_being_one |
| finding 3: the plan's records written after the project changed (`engine/tooling/plan_executor.py`) | 1 failed, 40 passed, 1 skipped: test_a_plan_stops_once_its_project_stopped_being_one |
| finding 3: plan writes not checked against the lock (`engine/tooling/plan_executor.py`) | 1 failed, 40 passed, 1 skipped: test_a_plan_stops_once_its_project_stopped_being_one |
| ai_job: AIOps without the lock (`engine/console_runtime/handlers_ai.py`) | 2 failed, 39 passed, 1 skipped: test_the_console_stops_once_its_project_stopped_being_one, test_the_outer_projects_console_cant_change_a_nested_project |
| MCP fallback: AIOps without the lock (`engine/mcp_server/tools.py`) | 2 failed, 39 passed, 1 skipped: test_a_nested_projects_lock_covers_nothing_once_it_stopped_being_a_project, test_the_outer_root_cant_change_a_nested_project_studio_has |

**11/11 caught**, each file put back byte for byte.

## 5. Validation

Local, Windows, Python 3.13 (`-W error`), on the combined tree (base + #521 + #522):

- the remediation A and B tests, R4's and R5's own, the plan, assist and pipeline tests, every MCP-tool test,
  `test_ai_ops*`, `test_authoring*` (F1), the creator-integrity and R1/R2/R3 suites, the import-boundary,
  exception-policy, logging, type-ignore and test-lanes contracts: **765 passed, 1 failed, 9 skipped** on the
  first combined run. The failure was this change's: R2's
  `test_a_studio_opening_during_an_outside_write_opens_on_what_was_written` replaces `Project.save` with a
  stand-in that took no arguments, and `authoring_session` now calls `save(owner=held)`. #522's focused run hadn't
  included that file. The stand-in now passes the save's arguments through (behaviour and assertions unchanged);
  that file with the session and remediation B tests: **75 passed**.
- real window (`MESH_GL_SMOKE=1`): `test_ai_write_paths_gpu`, `test_studio_project_ownership_gpu`,
  `test_studio_revision_identity_gpu`, `test_studio_object_identity_gpu`, `test_room_file_ownership_gpu`,
  `test_studio_ai_write_set_gpu`, `test_live_bridge_request_states_gpu`: **15 passed**;
- `tooling.ruff_gate` ok, `tooling.mypy_gate` ok, exception-policy scan 482 (baseline unchanged), no new
  `ALLOWED_VIOLATIONS` entry.

CI and Extended run on each PR's new head after this report is committed; their first attempts (failures kept,
nothing rerun) are in each PR's "Remediation B: CI and Extended results" comment.

## 6. Limits

- Studio's own save checks nothing new: it owns its project, and a room its world lists in a nested project is
  written by Studio as before (R2 semantics, out of scope). The check applies to writers outside Studio
  (`authoring_session`, and so MCP and `mesh author apply`).
- A project changing *during* `save_documents` itself (between the check and its renames) isn't detected; the
  check runs immediately before, under the lock. Folder restructuring isn't transactional (as the brief says).
- Undo stops at the first destination whose project changed, after any earlier deletions or restorations (they are
  reported; not rolled back). It checks destinations and types, not content: the stale-content undo protection is
  the separate deferred P1.
- Deferred, untouched: stale-content undo, MCP stale routing, light-index translation, Windows launcher PID tests,
  transactional jobs.
