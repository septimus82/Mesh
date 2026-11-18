# R4/R5 Remediation A: each writer holds the lock of the project its files are in

#462, independent review (Astra) of #521 (R4) and #522 (R5), P1 cross-project data integrity. Both PRs stay drafts.

**Verdict: READY FOR INDEPENDENT REVIEW.**

Common base `ee1986e0c58f8f93f7339ed8c7bc91d032713ef5`. Evidence: `docs/reviews/r4_r5_remediation_a_evidence/`.
The review's text was not available to me (no review or comment on either PR, none in the repository); the findings
worked from are those the remediation brief restates, each reproduced below before it was changed.

## 1. Root cause and the changed invariant

R4 and R5 took R2's lock on the folder a writer was *given* (`mesh apply-plan`'s and `ai_job`'s working folder, the
MCP tools' `root`) and limited targets with two separate, slightly different checks. Neither asked which Mesh project
that folder belongs to. So:

- started in an ordinary folder inside a project, a writer locked `<folder>/.mesh/owner.lock`, a lock no editor
  takes: a Studio holding the project didn't stop it (R4 directly; R5 when Studio opened after F1's check, which looks
  at the project), and two writers of one project held two locks at once;
- `ai_job`'s `AIOps(".")` could write into a nested Mesh project (its own owner) under the outer project's lock;
- `undo-last-plan` restored whatever its manifest named, anywhere, and printed "Undo successful" when it restored
  nothing.

**The invariant now:** a Mesh project is the nearest folder, the path's own or above, holding a `config.json` (what
`mesh edit`, Mesh Studio and `authoring_session` already require), once `..`, links and junctions are resolved.
An ordinary folder inside a project is that project's; a folder with its own `config.json` is a nested project with
its own owner (in this repository: `examples/template_game/sample_project`; templates have none). **Every protected
writer locks the project its starting folder is in (`ownership_root`), wherever inside it it started, and changes
only that project's files (`in_project`): inside it, in no project nested in it.** Outside any project (no editor can
open such a folder) the folder itself is the lock, as before.

One implementation, `engine/editor/project_ownership.py` (`project_root`, `ownership_root`, `in_project`), beside
R2's lock; `AIOps(project=...)` enforces it on every path `AIOps` reads for a write or writes. No new lock, no new
lock identity, no import-layer exception.

## 2. Integration: one commit in both PRs

The rule is one commit on the common base (`60b09b37`, branch `fix/project-ownership-root`), merged (not rebased,
nothing force-pushed) into both PR branches. Both PRs contain the same commit; each then uses it:

| PR | Production paths corrected |
|---|---|
| #521 R4 | `mesh_cli/ai.py`: `apply-plan` and `undo-last-plan` lock `ownership_root(cwd)`; a refused or failed undo exits 1 and never prints "Undo successful". `engine/tooling/plan_executor.py`: forward execution checks `in_project` (R4's own check replaced); `undo_last(root)` checks every manifest destination before deleting or restoring anything and refuses whole. `engine/console_runtime/handlers_ai.py`: `ai_job` locks `ownership_root(cwd)` and runs `AIOps(".", project=held.root)`. |
| #522 R5 | `engine/mcp_server/tools.py`: `_own_for_files` runs F1's check on, and locks, `ownership_root(root)`; `apply_ops`' fallback and `create_scene` run `AIOps(root, project=held.root)` (R5's own nested-project subclass removed). |

The undo check: each `created` / `modified` entry must be a non-empty path; resolved (relative to the folder the
undo runs in, as the restore resolves it), it must be `in_project` of the held project; each modified entry's copy
must exist inside the backup folder. Any failure: "Not restored: nothing was changed, because ...", exit 1. Valid
historical backups (relative paths inside the project) restore as before.

Combined: base + #521 + #522 merges with no conflict, and #522 then #521 gives the identical tree
(`git merge-tree`: `8309e56e` both ways); `project_root` is defined once.

## 3. Before and after

`repro_boundaries.py.txt`: disposable scaffolded projects; Studio and every lock holder their own process (the OS
lock); the production paths. Before: #521 at `bec3c4a5`, #522 at `3793786f` (`before_r4.json`, `before_r5.json`).
After: the combined tree (`after_integration.json`) and each PR on its own (`after_r4.json`, `after_r5.json`).

| Reviewed case | Before | After |
|---|---|---|
| R4 `ai_job` from `<project>/packs/core_regions`, Studio owns the project | "Applied 1 operation(s)": the room written behind Studio | refused: "Mesh Studio has this project open"; nothing written |
| R4 `ai_job` in the outer project into `inner/...`, Studio owns the nested project | applied: the nested project's room written behind its Studio | "path is in another Mesh project than the one held"; nothing written |
| R4 `apply-plan` from `<project>/packs/core_regions`, Studio owns the project | exit 0: the room, a backup and history written (under `packs/core_regions/.mesh/`) | exit 1, refused; nothing written |
| R4 undo, the manifest naming a valid room and a scene in `packs/region2`, now its own project (Studio has it) | exit 0, "Undo successful": the nested project's scene deleted, the room restored | exit 1, "Not restored: nothing was changed, because packs\region2\... isn't a file of this project"; nothing changed in either project |
| R4 undo with a corrupt backup | exit 0, "Undo successful" after "Corrupt backup" | exit 1, "Undo failed: see above." |
| R5 `apply_ops` / `create_scene` with `root` = `<project>/packs/core_regions`; Studio opens the project after F1's check | ok: the world rewritten / the scene created behind Studio, under `packs/core_regions/.mesh/owner.lock` | refused `studio_open`; nothing written; no inner lock file |
| R5 the same `root` while another process owns the project as a writer | ok: wrote alongside it (two locks) | refused `project_busy`; nothing written |

## 4. Regression tests

Shared rule, `tests/test_project_ownership_root.py` (5): whose project a path is (ordinary folders, nested
projects, paths not yet existing, `..`, none); `ownership_root` from inside; `in_project`; Windows case and a
junction into a nested project; a symbolic link (skipped where links can't be made: Windows without the privilege;
runs on Linux); two writers starting in different folders of one project, the second in another process, refused
by the one lock (no inner `.mesh` made), while the nested project takes its own; `AIOps(project=...)`.

#521, `tests/test_ai_write_paths_project_root.py` (8), #522, `tests/test_mcp_project_ownership_root.py` (13): the
brief's eight cases on the production paths, each refusal byte-for-byte:

| Brief | R4 (console, apply-plan, undo) | R5 (MCP) |
|---|---|---|
| 1. Studio owns the outer project; started inside | all three refused | refused (live and session-off Studio), and Studio opening after the check (Astra's reproduction) |
| 2. Studio owns a nested project; the outer writes into it | refused (two operations, both refused) | `apply_ops` and `create_scene` refused |
| 3. a historical manifest into a since-nested project | refused whole, with the nested project free and owned | (no undo) |
| 4. one invalid destination among valid ones | refused whole; also outside paths, `..` aliases, non-paths, a missing copy | |
| 5. ordinary inner folders | `ai_job` (the project's lock held while it writes, no inner lock), apply-plan, undo work | both tools work under the project's lock |
| 6. a nested project edited under its own ownership (outer owned by Studio) | `ai_job` and apply-plan in it work | both tools work in it |
| 7. byte-for-byte | every refusal | every refusal |
| 8. two writers via different folders | `ai_job` from `.../scenes` holds the project; `mesh apply-plan` from the root (another process) refused | a writer owning the project (another process) stops a tool started inside |

On the old heads (`regression_before_r4.txt`, `regression_before_r5.txt`): R4 **7 of 8 fail** (the nested project
edited on its own passes: that already worked); R5 **7 of 13 fail**. R5's passing six are the refusals F1's check
already gave while Studio was visibly open and the nested-project edits; one R5 failure there is wording only (the
old head already refused writes into a nested project, with "another project inside this one").

Fault injection on the combined tree (`faults.json`, `mutate_r45.py.txt`):

| Mutation | Caught by |
|---|---|
| rule: a writer locks the folder it started in (no walk up to the project) (`engine/editor/project_ownership.py`) | 12 failed, 58 passed, 1 skipped: tests/test_ai_write_paths_project_root.py::test_inside_an_ordinary_folder_writers_work_under_the_projects_lock, tests/test_ai_write_paths_project_root.py::test_started_from_a_folder_inside_a_project_studio_has_every_writer_is_refused, tests/test_ai_write_paths_project_root.py::test_two_writers_starting_in_different_folders_cannot_both_hold_the_project, tests/test_mcp_project_ownership_root.py::test_a_writer_owning_the_project_stops_one_started_in_an_inner_folder, tests/test_mcp_project_ownership_root.py::test_an_inner_root_works_under_the_projects_lock, tests/test_mcp_project_ownership_root.py::test_studio_opening_after_the_check_is_never_written_behind_through_an_inner_root, tests/test_project_ownership_root.py::test_whose_project_a_path_is, tests/test_project_ownership_root.py::test_windows_case_and_junctions, tests/test_project_ownership_root.py::test_writers_starting_in_different_folders_of_one_project_take_one_lock |
| rule: a nested project's files count as the outer project's (`engine/editor/project_ownership.py`) | 9 failed, 61 passed, 1 skipped: tests/test_ai_write_paths.py::test_a_plan_writes_only_inside_the_project_it_owns, tests/test_ai_write_paths_project_root.py::test_an_undo_with_a_destination_outside_the_project_or_an_unsafe_alias_is_refused, tests/test_ai_write_paths_project_root.py::test_an_undo_with_any_destination_in_another_project_is_refused_whole, tests/test_ai_write_paths_project_root.py::test_the_outer_projects_console_cant_change_a_nested_project, tests/test_mcp_project_ownership.py::test_writes_stay_in_the_owned_project, tests/test_mcp_project_ownership_root.py::test_the_outer_root_cant_change_a_nested_project_studio_has, tests/test_project_ownership_root.py::test_aiops_held_to_a_project_writes_its_files_and_no_nested_projects, tests/test_project_ownership_root.py::test_whose_project_a_path_is, tests/test_project_ownership_root.py::test_windows_case_and_junctions |
| rule: links and junctions not resolved (`engine/editor/project_ownership.py`) | 2 failed, 68 passed, 1 skipped: tests/test_mcp_project_ownership.py::test_refused_while_studio_holds_unsaved_edits, tests/test_project_ownership_root.py::test_windows_case_and_junctions |
| AIOps: the held project not enforced (`engine/ai_ops.py`) | 4 failed, 66 passed, 1 skipped: tests/test_ai_write_paths_project_root.py::test_the_outer_projects_console_cant_change_a_nested_project, tests/test_mcp_project_ownership.py::test_writes_stay_in_the_owned_project, tests/test_mcp_project_ownership_root.py::test_the_outer_root_cant_change_a_nested_project_studio_has, tests/test_project_ownership_root.py::test_aiops_held_to_a_project_writes_its_files_and_no_nested_projects |
| undo: destinations not checked (`engine/tooling/plan_executor.py`) | 2 failed, 68 passed, 1 skipped: tests/test_ai_write_paths_project_root.py::test_an_undo_with_a_destination_outside_the_project_or_an_unsafe_alias_is_refused, tests/test_ai_write_paths_project_root.py::test_an_undo_with_any_destination_in_another_project_is_refused_whole |
| undo: a missing backup copy not checked (`engine/tooling/plan_executor.py`) | 1 failed, 69 passed, 1 skipped: tests/test_ai_write_paths_project_root.py::test_an_undo_with_a_destination_outside_the_project_or_an_unsafe_alias_is_refused |
| undo CLI: a failed undo reported as success (`mesh_cli/ai.py`) | 3 failed, 67 passed, 1 skipped: tests/test_ai_write_paths_project_root.py::test_a_failed_undo_exits_nonzero_and_never_says_it_succeeded, tests/test_ai_write_paths_project_root.py::test_an_undo_with_a_destination_outside_the_project_or_an_unsafe_alias_is_refused, tests/test_ai_write_paths_project_root.py::test_an_undo_with_any_destination_in_another_project_is_refused_whole |
| apply-plan / undo: lock the starting folder (`mesh_cli/ai.py`) | 1 failed, 69 passed, 1 skipped: tests/test_ai_write_paths_project_root.py::test_started_from_a_folder_inside_a_project_studio_has_every_writer_is_refused |
| ai_job: locks the starting folder (`engine/console_runtime/handlers_ai.py`) | 4 failed, 66 passed, 1 skipped: tests/test_ai_write_paths_project_root.py::test_inside_an_ordinary_folder_writers_work_under_the_projects_lock, tests/test_ai_write_paths_project_root.py::test_started_from_a_folder_inside_a_project_studio_has_every_writer_is_refused, tests/test_ai_write_paths_project_root.py::test_two_writers_starting_in_different_folders_cannot_both_hold_the_project, tests/test_mcp_project_ownership.py::test_refused_while_studio_holds_unsaved_edits |
| ai_job: AIOps not held to the project (`engine/console_runtime/handlers_ai.py`) | 1 failed, 69 passed, 1 skipped: tests/test_ai_write_paths_project_root.py::test_the_outer_projects_console_cant_change_a_nested_project |
| MCP: locks root as given (`engine/mcp_server/tools.py`) | 6 failed, 64 passed, 1 skipped: tests/test_mcp_project_ownership_root.py::test_a_writer_owning_the_project_stops_one_started_in_an_inner_folder, tests/test_mcp_project_ownership_root.py::test_an_inner_root_works_under_the_projects_lock, tests/test_mcp_project_ownership_root.py::test_studio_opening_after_the_check_is_never_written_behind_through_an_inner_root |
| MCP: AIOps not held to the project (`engine/mcp_server/tools.py`) | 2 failed, 68 passed, 1 skipped: tests/test_mcp_project_ownership.py::test_writes_stay_in_the_owned_project, tests/test_mcp_project_ownership_root.py::test_the_outer_root_cant_change_a_nested_project_studio_has |

**12/12 caught**, each file put back byte for byte.

## 5. Validation

Local, Windows, Python 3.13 (`-W error`), on the combined tree (base + #521 + #522):

- the remediation tests (5 + 8 + 13), R4's and R5's own (`test_ai_write_paths`, `test_mcp_project_ownership`,
  `test_ai_console`), the plan, assist and pipeline tests, every MCP-tool test, `test_ai_ops*`, `test_authoring*`
  (F1), the creator-integrity and R1/R2/R3 suites (`test_studio_ai_base_revision*`, `test_studio_ai_identity`,
  `test_studio_ai_write_set`, `test_proposal_memory`, `test_live_bridge_request_states`, `test_room_file_ownership`,
  `test_project_save_transaction`, `test_safe_scene_creation`, `test_one_editing_path`, `test_hot_reload_preflight`,
  `test_studio_project*`, `test_studio_revision_identity`, `test_studio_object_identity`,
  `test_ai_preview_player_summary`), and the import-boundary and exception-policy checks: **736 passed, 9 skipped**;
- real window (`MESH_GL_SMOKE=1`): `test_ai_write_paths_gpu`, `test_studio_project_ownership_gpu`,
  `test_studio_revision_identity_gpu`, `test_studio_object_identity_gpu`, `test_room_file_ownership_gpu`,
  `test_studio_ai_write_set_gpu`, `test_live_bridge_request_states_gpu`: **15 passed**;
- `tooling.ruff_gate` ok, `tooling.mypy_gate` ok, the exception-policy scan 482 (the baseline, unchanged); no new
  entry in `ALLOWED_VIOLATIONS`.

CI and Extended run on each PR's new head after this report is committed; their first attempts (failures kept,
nothing rerun) are in each PR's "Remediation A: CI and Extended results" comment.

## 6. Limits

- A folder with a `config.json` is taken as a project. Templates put one only at the root; a game that keeps a file
  named `config.json` in a data folder would see that folder as a nested project and the writers refuse it (fail
  closed). Studio has the same marker.
- Undo checks destinations, not contents: a file changed since the plan is still overwritten (the separate P1
  "stale-content plan undo", out of scope).
- `ai_job` and `apply_ops` still apply each operation on its own: a job mixing a nested-project operation with valid
  ones applies the valid ones (each result says which failed). Out of scope (transactional jobs).
- `authoring_session.apply` (R2) locks the `root` it is given, but only opens a project whose `root` holds a
  `config.json`, so an inner folder can't be written through it ("isn't a Mesh project"); unchanged.
- Out of scope, untouched: stale-content undo, MCP stale routes and light indexes, transactional jobs, Windows
  termination-test PIDs, human authoring commands.
