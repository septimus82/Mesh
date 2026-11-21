# R5: MCP direct-file writes own the project (closing a check-then-write gap)

#462 R5. MCP `apply_ops`' direct-file fallback and MCP `create_scene` checked that no editor had the project open
(`tools._files_blocked`, F1), then wrote with nothing held. A Mesh Studio opening between the check and the write
read the files, and the write then landed behind it. Found in R4 (`probe_mcp.json` there).

**Verdict: READY FOR INDEPENDENT REVIEW.**

Base `ee1986e0c58f8f93f7339ed8c7bc91d032713ef5` (`redesign/visual-editor`; R4, PR #521, is not merged and this does
not depend on it). Evidence: `docs/reviews/r5_mcp_project_ownership_evidence/`.

## 1. The changed paths

Only `engine/mcp_server/tools.py`:

| Entry point | Before | Now |
|---|---|---|
| `apply_ops` when its operations aren't all room edits of a Studio project (the fallback: the world, quests, cutscenes, and room operations on projects Studio can't open) | `_files_blocked` (F1), then `AIOps.apply_job` and the optional validation, nothing held | `_own_for_files`: F1's check, then R2's lock (`project_ownership.acquire(root, AUTHORING, wait=0.5)`), held through `apply_job`, the result and the validation |
| `create_scene` | `_files_blocked`, then `AIOps.create_scene`, nothing held | the same: owned through the scene's creation |
| `add_entity_from_prefab` | goes through `apply_ops` | unchanged (covered through `apply_ops`) |

`apply_ops` for room edits of a Studio project (`_studio_changes`, then `authoring_session.apply`) was already owned
(R2) and is unchanged.

No new mechanism: R2's lock, imported lazily in the tool (`engine/mcp_server` is not runtime code; no import-layer
exception added; `tools.py` already reaches `engine.editor.project_ownership` through `engine.authoring_session`).
No R1/R2/R3 semantics, proposals, transactions or human authoring commands changed.

## 2. Ownership lifetime

1. F1's check as before: a live Studio, another editor, an uncertain session record, or an owner without a session
   record ("an outside tool is writing its files at this moment") refuse with their existing messages. The lock
   can't be taken before this check: the check asks about owners itself (a shared lock), and would see its own.
2. **The lock**, waiting half a second as `authoring_session.apply` does. Owned elsewhere: `studio_open` (a Studio
   opened since the check), `other_editor_open`, or `project_busy` (another writer). Anything else that keeps it
   from being taken, `OwnershipUnavailable` or an unexpected exception: `ownership_unknown`. Each is a refusal with
   nothing read or written; there is no path from a refusal to an unlocked write.
3. **Held** (a `with` block) from before `AIOps` reads a file until the files are written, the result built and the
   validation run. Released however the block ends: normally, by an operation failing, or by an exception. A killed
   process releases it with the process (the OS lock).
4. **Within the project**: `AIOps` already refuses paths outside `root`. The tool's `AIOps` (`_owned_ops`) also
   refuses paths in another project inside it (a folder with its own `config.json`), whose owner is not the one held.
   For `create_scene` the refusal raises `ValueError`, as a path outside `root` always has.

## 3. Before and after (deterministic reproduction)

`repro_mcp.py.txt`: on a fresh project for each path, `tools._files_blocked` runs as written; the seam pauses right
after it says "free"; Studio (its own process) opens and makes an unsaved edit; then the tool continues.

| Path | Baseline `ee1986e0` (`repro_before.json`) | With the fix (`repro_after.json`) |
|---|---|---|
| world (`set_world_start`) | Studio opened; **ok**; the world file written while Studio owned the project | **refused** `studio_open`; every file identical; Studio's unsaved work kept |
| quests (`add_quest_definition`) | **ok**; `assets/data/quests.json` written behind Studio | refused; identical |
| cutscenes (`add_cutscene`) | **ok**; `cutscenes.json` created behind Studio | refused; identical |
| `create_scene` | **ok**; `attic.json` created behind Studio | refused; identical |
| each, Studio closed (control) | ok, only its target changed, the project free | the same |

## 4. Tests

`tests/test_mcp_project_ownership.py` (34): every Studio and second writer its own process (the real OS lock), each
path on its own (parametrized over world, quests, cutscenes, `create_scene`):

| Case | Result |
|---|---|
| Studio holding unsaved edits, with its live session and without one | refused (`studio_open` / `studio_session_uncertain`); files byte-identical; Studio's work kept |
| Studio opening between the check and the write (the reproduction) | refused `studio_open`; identical; work kept |
| Studio opening during a permitted write | Studio waits (still unanswered 1.5 s in, the project owned by the tool); opens once the write is done; its ownership began after the file's last change |
| a second MCP writer (a separate process) while one writes | refused ("an outside tool is writing its files at this moment"); identical; the first completes |
| Studio and an MCP write started at once (a start gate), twice per path | never overlapping: the tool was refused with nothing written, or Studio's ownership began after the tool's last write |
| an operation that fails; a write that raises; a writer killed mid-write | the project free afterwards; Studio opens it |
| ownership unavailable, or an unexpected error taking it (injected) | refused `ownership_unknown`; identical |
| Studio closed | each path succeeds, only its target changed, the project free |
| a world in, or a scene into, another project inside this one; a scene outside | refused; nothing written |

On the baseline (`regression_before.txt`): **18 fail**, each at the gap (the write landed behind Studio; Studio
opened mid-write; the second writer wrote; the killed writer held nothing; ownership never consulted; nested
projects written). **16 pass**: the refusals while Studio is visibly open (F1 already caught those), the
Studio-closed controls, and the start-gate race (on the baseline the tool's write happened to finish before Studio
read: that race is evidence for the fix, not a regression detector; the reproduction above is).

Fault injection (`faults.json`, `mutate_r5.py.txt`):

| Mutation | Caught by |
|---|---|
| writes without owning the project (the check alone, as before) | 8 failed in 18.87s: test_studio_opening_between_the_check_and_the_write_is_never_written_behind, test_studio_opening_during_a_permitted_write_waits_until_it_is_done |
| a Studio that opened since the check taken as a pass | 4 failed in 14.49s: test_studio_opening_between_the_check_and_the_write_is_never_written_behind |
| an unexpected lock error taken as permission | 4 failed in 3.48s: test_an_ownership_that_cant_be_established_is_a_refusal |
| create_scene lets the project go before writing | 1 failed, 4 passed in 11.37s: test_studio_opening_during_a_permitted_write_waits_until_it_is_done |
| apply_ops lets the project go before writing | 7 failed, 1 passed in 16.96s: test_a_second_mcp_writer_is_turned_away_while_one_writes, test_studio_opening_during_a_permitted_write_waits_until_it_is_done |
| apply_ops never lets the project go | 4 failed, 1 passed in 6.41s: test_failed_raising_and_killed_writes_let_the_project_go, test_with_studio_closed_each_write_succeeds_and_lets_the_project_go |
| create_scene never lets the project go | 2 failed, 3 passed in 10.44s: test_failed_raising_and_killed_writes_let_the_project_go, test_with_studio_closed_each_write_succeeds_and_lets_the_project_go |
| writes into another project inside the owned one | 1 failed in 3.28s: test_writes_stay_in_the_owned_project |

**8/8 caught**, the file put back byte for byte after each.

## 5. Validation

Local, Windows, Python 3.13 (`-W error`):

- `tests/test_mcp_project_ownership.py`: **34 passed**;
- with every test that calls the MCP tools (`test_mcp_*`, `test_one_editing_path`, `test_safe_scene_creation`,
  `test_authoring_playable_prefabs_contract`, `test_runtime_play`, `test_runtime_diagnose`, `test_hot_reload_preflight`,
  `test_project_save_transaction`, `test_hd2d_lighting_controls`, `test_hd2d_shadow_allocation`,
  `test_studio_ai_base_revision`, `test_cocreative_live_bridge`), F1 (`test_authoring_session*`), R1/R2/R3/S4
  (`test_studio_revision_identity`, `test_studio_project_ownership`, `test_studio_object_identity`,
  `test_room_file_ownership`), `test_ai_ops*`, and the import-layer and policy tests
  (`test_runtime_editor_import_boundary`, `test_*import_surface*`, `test_logging_policy_contract`,
  `test_type_ignore_inventory_ratchet`, `test_no_direct_singleton_imports_policy`): **530 passed, 8 skipped**;
- real window (`MESH_GL_SMOKE=1`): `test_live_bridge_request_states_gpu`, `test_studio_project_ownership_gpu`,
  `test_studio_revision_identity_gpu`: **4 passed**;
- `tooling.ruff_gate` ok, `tooling.mypy_gate` ok (one F541 in the new test fixed before commit).

### PR #522, first attempts (none rerun)

- head `d1f29f9e`: **CI failed** (run 44324837662) and **Extended failed** (run 44324833415), from one cause.
  The exception-policy scan counted the new `except Exception` in `_own_for_files` (an unexpected lock failure is a
  refusal) as a *silent* broad catch: 483 against the baseline's 482 (`test_scan_exception_policies_contract::
  test_baseline_matches_scan` on both OSes, verify-all's `exception-policy-scan` step). Every other failure (the
  verify jobs, Extended's verify-all-dependent tests) followed from verify-all failing. Linux pytest otherwise
  12,155 passed, 1 failed; Extended's GPU lanes passed. The focused local run had not included that scan.
  Fixed without touching the baseline: the catch now logs the failure with its traceback (`exc_info=True`) and
  still refuses; the scan counts 482 again.
- The next head's results are in the PR's "CI and Extended results" comment (this report is committed before
  they run).

## 6. Limits

- `apply_ops` routing decides between the authoring path and the fallback by reading the project first
  (`_studio_changes`, unchanged, unowned). It writes nothing; the authoring path then reads again under ownership
  (R2). A Studio opening in between makes that path propose to it, as before.
- `AIOps.apply_job` applies each operation on its own (one failing leaves the others written). Unchanged: the
  ownership now covers those writes, without making them all-or-nothing.
- `validate_scene` and the read tools take no ownership (read-only).
- A second MCP writer is usually refused at F1's check ("an outside tool is writing ..."), before the lock. Past
  the check, the lock refuses it (`project_busy`).
- The other direct `AIOps` writers are outside this brief: the console's `ai_job` and `mesh apply-plan` are R4
  (PR #521, unmerged).

## Remediation A (independent review, P1: project ownership boundaries)

The independent review found this PR's writers locked the folder they were given, not the Mesh project it is in,
and limited targets with a check of their own. Corrected with one rule shared with the other PR (#521 / #522): one
commit, `60b09b37` (`project_ownership.project_root` / `ownership_root` / `in_project`, and `AIOps(project=...)`),
merged into both. The root cause, the changed invariant, the corrected paths, the before/after reproductions, the
tests, fault injection and the combined results are in `docs/reviews/r4_r5_remediation_a.md`. Sections above
describing this PR's own nested-project check, or a lock on the working folder or `root`, are superseded by it.
