# P1: a stale plan undo never erases creator work

#462. `mesh undo-last-plan` restored a plan's backup over whatever was there, erasing work saved after the plan. Base
`redesign/visual-editor` at `ad91e28c`.

**Verdict: READY FOR INDEPENDENT REVIEW.**

Evidence: `p1_stale_plan_undo_evidence/`.

## 1. Reproduction (`before.json`, `repro_stale_undo.py.txt`)

Disposable scaffolded project, base `ad91e28c`:

1. `mesh apply-plan` (subprocess) adds NPC "Ferryman";
2. the production project API, as Mesh Studio saves (`acquire(root, STUDIO)`, `engine.studio_project.Project`,
   `authoring.apply`, `Project.save(owner=held)`), adds "Later human edit" and saves; the hold is let go;
3. `mesh undo-last-plan` (subprocess), nothing holding the project.

Result: exit **0**, "Restoring packs\core_regions\scenes\start.json ... Undo successful", room afterwards `["None"]`:
**both NPCs erased**.

Also found on the base, in scope ("multiple actions touching the same file"): a plan that creates a scene and then
changes it (`create_scene` + `add_npc` into it) recorded the scene as both `created` and `modified`, the copy of its
in-plan state as the "original". Undo deleted it, then restored it from that copy: the scene the plan made survived its
undo.

## 2. Manifest format and fingerprint semantics

`.mesh/plan_backups/<time>_<plan>/manifest.json`, `version` 2 (`manifest_v2_example.json`):

```json
{"version": 2, "completed": true,
 "created": ["<path>", ...], "modified": ["<path>", ...],
 "after": {"<path>": {"exists": true, "sha256": "<64 hex>"} | {"exists": false}, ...}}
```

- `created` / `modified` and `files/` (the copies before the plan) are unchanged: what restoration needs.
- `after`: for every created or modified path (the same string as in its list), what the plan left there: absent, or a
  file and the SHA-256 of its exact bytes (`sha256: null` for something there that isn't a file: no undo restores over
  it). Taken by `BackupManager.finish_backup` from the files themselves after the plan's last write, while the plan's
  writer (`mesh apply-plan`) still holds the project (R2/R4 lock); the undo never derives it from the files.
- A file several actions touch is recorded once: its state before the plan at the first touch (`backup_file` now
  ignores later touches, which fixes the create-then-change case above), its final state in `after`.
- `completed`: false for a plan that stopped with an error (section 4).

## 3. Undo behaviour

Before anything is deleted, restored or replaced (`BackupManager.restore_last_backup`):

1. the newest backup's manifest is read (unreadable: refused);
2. a manifest without `version` (from before this record): refused (legacy policy below); an unknown version, a missing
   or malformed `after` or `completed`, or any created/modified path without a valid record (`exists` a boolean; a
   64-hex `sha256` or null; no other keys): refused (`_unverified`);
3. R4/R5 checks unchanged (`_unsafe_entries`: every destination in the held project, a file or nothing, folders above,
   copies inside the backup);
4. every path is compared with its record (`_changed_since`); any difference refuses the whole undo, naming each path
   and how it differs: "its contents changed", "it is gone", or "something is there now; the plan left nothing".

| Case | Result |
|---|---|
| every file exactly as the plan left it | modified files restored from their copies, created files removed; exit 0 |
| any file differs (edited, replaced, removed, created since, or the plan already undone) | `Not restored: nothing was changed, because files changed after the plan finished, and undoing it would erase that: <path> (<how>); ...` and where the pre-plan copies are, to take back by hand; exit 1; every file byte-identical |
| legacy manifest (no `version`) | `Not restored: nothing was changed, because this backup was made before Mesh recorded what a plan leaves behind, so it can't tell whether those files were changed since ...`, with the copies' folder and the plan's modified and created files for recovery by hand; exit 1, even if nothing changed |
| malformed or incomplete record | refused, nothing changed, exit 1 |

No force option. A repeated undo refuses: after a successful undo every file differs from what the plan left (the
message says "or this plan was undone already"). Ownership (R2 lock), the R4 per-write recheck and history or backup
retention are unchanged. Manual recovery: the pre-plan copies stay in the backup's `files/` folder at their project
paths.

## 4. A plan that stopped (partial failure)

A plan whose action raises already wrote its manifest (so its changes could be undone); it now writes it the same way,
`completed: false`, with `after` taken at the point it stopped (under the same lock, and only while the lock still
covers its records: `records_allowed`). Every path it had begun (backed up first, before the action writes) is in it;
what an action never wrote is recorded as it is (unchanged or absent). So the record is as verified as a completed
plan's, and its undo is allowed only while every file is exactly what the stopped plan left; the undo says "That plan
stopped with an error: undoing what it changed before it stopped". A plan that never got to write its manifest (killed,
or its project changed during it) leaves a backup without one, refused as before ("Corrupt backup (missing manifest)").
No automatic rollback.

## 5. Tests

`tests/test_stale_plan_undo.py` (23, the production CLI in subprocesses, disposable projects):

| Test | Covers |
|---|---|
| `test_a_later_human_edit_refuses_the_undo_and_both_npcs_stay` | the reproduction: refused, both NPCs, byte-identical, exit 1 |
| `test_an_undo_right_after_the_plan_restores_it` | success; the manifest's record equals the room's bytes |
| `test_an_unchanged_multi_file_plan_restores_every_file` | create + change a scene + change a room: all undone (the created scene removed) |
| `test_two_actions_changing_one_file_restore_it_to_before_the_plan` | one record, the final state; restored to before the plan |
| `test_a_created_file_changed_since_refuses_the_undo[edited/deleted/replaced]` | created file changed, removed, replaced |
| `test_a_modified_file_edited_by_hand_refuses_the_undo` | modified file changed |
| `test_a_file_the_plan_left_absent_that_exists_now_refuses_the_undo` | expected absent, now present |
| `test_one_changed_file_in_a_multi_file_plan_refuses_every_file` | one conflict: the untouched room not restored either |
| `test_an_undo_already_done_or_followed_by_an_edit_never_runs_again` | repeated undo, and after a later edit |
| `test_a_plan_that_stopped_is_undone_only_while_what_it_left_is_unchanged` | partial failure: refused once changed, restored when exactly as left |
| `test_a_backup_from_before_the_record_is_never_restored` | legacy manifest, even unchanged |
| `test_missing_malformed_or_incomplete_records_refuse_the_undo[10 cases]` | no `after`, not an object, an entry missing, bad hash, `exists` not a boolean, an extra key, unknown version, no `completed`, not JSON, not an object |

Existing tests updated (their intent kept): R4's hand-made backups (`test_ai_write_paths_remediation_b.py`) and
edited manifests (`test_ai_write_paths_project_root.py`) now carry a version-2 record of the files as they are, so the
destination checks they exercise are still what refuses (or restores) them. Nested-project and OS-lock protection:
R4's and R5's suites unchanged and passing (refused while Studio holds the project, nested projects, mid-undo marker
change).

On the base (`regression_before.txt`): **22 of 23 fail**. The behavioural ones fail on the bad outcome (the undo
succeeded and erased the edits, or restored a changed file); the success and record tests also fail on the new manifest
format itself; the one that passes is the manifest-that-isn't-an-object case, which the base already refused.

Fault injection (`faults.json`, `mutate_stale_undo.py.txt`): **8/8 caught**, each file put back byte for byte:

| Mutation | Failed |
|---|---|
| the conflict check disabled | 9 |
| only existence compared, not the hash | 6 |
| the expected state taken from the file at undo time | 9 |
| legacy backups not refused as such | 1 |
| records not validated | 5 |
| the plan records no final state | 15 |
| a file touched twice backed up twice | 1 |
| a stopped plan recorded as completed | 1 |

## 6. Validation

Local, Windows, Python 3.13, `-W error`:

- every test of plan execution, apply, undo, history, lint, assist, pipeline, triage and wizard (56 files), R4's and
  R5's ownership suites, Studio ownership, `ai_console`, `ai_ops`, authoring session, import-boundary, exception-policy,
  logging and test-lanes contracts: **268 passed, 1 skipped**; their slow/e2e tests (`-o addopts= -m "slow or e2e"`):
  **7 passed**;
- real window: `test_ai_write_paths_gpu` (apply and undo refused while Studio holds the project): **1 passed**;
- `tooling.ruff_gate` ok, `tooling.mypy_gate` ok, exception-policy scan 482 silent (unchanged), no new import-boundary
  entry.

CI and Extended first attempts (failures kept, nothing rerun) are in the PR's results comment.

## 7. Limits

- The record is advisory against writers that ignore the project lock: a file changed between the undo's check and its
  write (by a tool not taking the lock) isn't detected; anything taking the lock (Mesh Studio, MCP, the CLI) can't run
  meanwhile.
- Backups made before this change are never restored by the command (by design); their copies stay for recovery by
  hand.
- The undo still only reaches the newest backup; an undo that stops part way (the R4 per-write recheck) isn't rolled
  back.
- Paths are recorded as the plan named them (relative to where it ran, as before); an undo run from another folder
  compares other files with the record, which in practice differ or are absent, so it refuses.
- A file an action writes without `_track_file` would be in neither the backup nor the record, as before (not audited
  action by action here).
