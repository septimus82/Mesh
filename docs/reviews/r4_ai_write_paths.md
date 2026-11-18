# R4: the AI commands that wrote project files behind Mesh Studio

#462 R4. R2 made a project's ownership one operating-system lock (`engine.editor.project_ownership`): Mesh Studio
holds it while open, and `engine.authoring_session.apply` (MCP tools, `mesh author`) holds it for each direct write.
Two older AI write paths never asked: `mesh apply-plan` (and its `mesh undo-last-plan`) and the game console's
`ai_job`.

**Verdict: READY FOR INDEPENDENT REVIEW.**

Base `ee1986e0c58f8f93f7339ed8c7bc91d032713ef5`. Evidence: `docs/reviews/r4_ai_write_paths_evidence/`.

## 1. The entry points and their write paths

| Entry point | Reaches | Writes |
|---|---|---|
| `mesh apply-plan PLAN [--from-triage] [--ai-safe] [--run-tests] [--no-lint] [--dry-run]` | `mesh_cli.legacy.dispatch` -> `mesh_cli.ai.handle` -> `_handle_apply_plan` | `PlanExecutor._write_file` (`json_io.write_text_atomic`), paths relative to the working folder |
| `engine.tooling.plan_apply.apply_plan(...)` (used by `mesh pipeline` / `pipeline_runner` and `mesh assist --apply`) | `mesh_cli._handle_apply_plan` -> `legacy_impl._handle_apply_plan` -> `mesh_cli.ai.handle`: the same function | as above |
| `mesh undo-last-plan` | `mesh_cli.ai._handle_undo_last_plan` -> `PlanExecutor.undo_last` -> `BackupManager.restore_last_backup` | deletes the plan's created files, copies its backups over the modified ones |
| console `ai_job <job.json>` (any `GameWindow`: ` or Insert opens the console) | `engine.console_runtime.handlers_ai.handle_ai_job` -> `AIOps(".").apply_job` -> `window.reload_scene()` | `AIOps` (`json_io.write_json_atomic`): scenes, the world, quests, cutscenes, new scene files, all inside the working folder (`AIOps._contain`) |

The working folder is the project: `mesh edit` / `mesh run` change into the project root, and so do the CLI
commands' users. Everything a plan writes besides its targets is in it too: `.mesh/plan_backups/<time>_<id>/`
(the backups and `manifest.json`), `.mesh/plan_history/<time>_<id>.json` (written twice: by the executor and by
the command) and, with `--ai-safe`, `.mesh/ai_history.jsonl`. `--ai-safe` also applies the plan first in a sandbox
(`PlanTester.run_tests_in_sandbox`: a temporary copy, the process's folder changed into it), and `--run-tests`
reads the result afterwards. `--dry-run` writes nothing at all (no backup, no history).

Where the console is reachable: Mesh Studio runs inside the game window (`engine.studio.open_studio`) and takes
every key and every character while editing (`Studio.on_key_press` / `on_text` return True), so there the console
can't be opened. In its **play-test** (F4) Studio passes keys on (`return False`), and ` opens the game's console
exactly as in a game (`engine/game_runtime/input_dispatch.py`). The legacy editor (`MESH_LEGACY_EDITOR=1`, or F4
in a game window) never takes the console key.

## 2. Reproduced before the fix

Disposable projects only (temporary folders, the blank template). Mesh Studio is `tests/studio_owner_process.py`
(Studio's own `Project`, AI host and bridge, the project owned as `open_studio` owns it) for the CLI, and the real
Studio in a hidden window for the console. The person's unsaved edit: "Unsaved Warden" placed in the room.

**`mesh apply-plan`** (a plan adding "Ferryman", the real CLI in a subprocess; `repro_plan_before.json`):

| | Studio open, unsaved | Studio closed |
|---|---|---|
| `mesh apply-plan` | **exit 0, "applied successfully"**: the room rewritten, a backup and a history record made | exit 0, the same |
| Studio afterwards | unaware: its room still "Player", "Unsaved Warden", unsaved | |
| the person's next Save | the room saved as Studio has it: **"Ferryman" gone from the project without a word** (only `start.json.outside-change.bak`, S4's copy, keeps it) | |
| then `mesh undo-last-plan` (Studio still open, more unsaved work) | **exit 0**: the room put back to before the plan, **deleting the person's saved "Unsaved Warden" from disk** | exit 0, the plan undone |

**Console `ai_job`** (a job adding a light to the room and a quest; the real Studio in a hidden window, the keys
F4, `, the command typed as text, Enter, then Stop and Ctrl+S; `repro_console_before.json`):

| | Studio play-test, unsaved work | a game window, Studio closed |
|---|---|---|
| the console | **opens** (` in the play-test) | opens |
| `ai_job` | **"Applied 2 operation(s)"**: the room and `quests.json` written behind Studio; the play-test reloaded (showing Studio's own documents, so not even the change) | applied, the scene reloaded |
| Stop | Studio's unsaved work intact (the reload didn't touch its documents) | |
| the person's next Save | the room saved as Studio has it: **the AI's light dropped**; the quest stays: **half a job** in the project | |

A job with an operation that fails reported "Job failed" and still left its first write on disk (each operation is
applied on its own; section 6).

**With the fix** (the same scripts at `05202d33`: `repro_plan_after.json`, `repro_console_after.json`): with Studio
open, `apply-plan` and `undo-last-plan` exit 1, "nothing was changed. Mesh Studio has this project open ...", every
file identical; `ai_job` in the play-test says "nothing was changed. Mesh Studio has this project open in this
window ...", every file identical; Stop keeps the unsaved work and Save writes exactly it, no `.outside-change.bak`.
With Studio closed, all three apply as before.

## 3. The protection

The one already there, R2's lock, now taken by these commands too. No new mechanism, no new state, no change to
R2's ownership semantics, recovery or messages (one helper wording the refusal is added beside them).

**`mesh apply-plan`** (`mesh_cli/ai.py`): writing (not `--dry-run`), it owns the project
(`project_ownership.acquire(cwd, AUTHORING, wait=0.5)`) **before it reads anything** (the plan's lint, the sandbox
copy, the targets) and holds it until it returns: the writes, the backup manifest, both history records, the AI
history and `--run-tests`. If Mesh Studio, another editor or another writer has the project, or ownership can't be
established, it prints why and exits 1 having written nothing. Read-only `--dry-run` takes nothing and still works
with Studio open. The executor is told the root it owns, and refuses before writing any file outside it, or inside
another project folder within it (a folder with its own `config.json`): only the owned project is held. Before, a
plan's `inputs.into_world` could name a world anywhere, `../another/worlds/...` included (`_check_safety` allows
it). A pack's folder is now checked before it is made, not after.

**`mesh undo-last-plan`**: owns the project the same way around the restore.

**`ai_job`** (`engine/console_runtime/handlers_ai.py`):

- in a window that edits the project (Mesh Studio attached, the window's own hold on the project from `mesh edit`,
  or the legacy editor active) it is **refused before anything is read**: "nothing was changed ... ask an AI
  through Mesh Studio's AI panel (its changes come to you to accept), or close it and run the job in the game". The
  window's own hold is never taken as a pass: it is its editor's, and the job would still be writing behind that
  editor's unsaved work. Turning a legacy job into a Studio proposal was not attempted: `AIOps` operations (quests,
  cutscenes, world links) don't map onto Studio's documents without a redesign, and the brief prefers refusal then.
- elsewhere (a game window) it owns the project while `AIOps` writes, exactly as an outside writer, and lets it go
  before reloading the scene (a read). If it can't own it, nothing is written and nothing reloads.

No fallback anywhere: a refusal is final, never followed by a direct write.

## 4. Races and failures (cross-process, the real OS lock)

`tests/test_ai_write_paths.py` (each Studio its own process) and `tests/test_ai_write_paths_gpu.py` (the real
window):

| Case | Result |
|---|---|
| apply-plan / undo-last-plan, Studio open with unsaved work (the CLI in a subprocess) | exit 1, every project file (backups and history included) byte-identical; Studio's work kept; its Save writes exactly its work, no `.outside-change.bak` |
| `--dry-run` with Studio open | exit 0, nothing written |
| Studio closed | applies and undoes as before; the project free afterwards |
| another writer, or another editor, holding the project (a separate process) | apply-plan and undo refused, nothing written |
| Studio and a plan started at the same instant (a start gate), three times | each time the plan had the project first and Studio waited (Studio waits 2 s), then read the room with the plan's change: Studio's view always equalled the files. (The other order, Studio first, is the refusal case above; this race never produced it here.) |
| Studio opening while a plan is between reading and writing | Studio turned away ("An outside tool is writing this project's files"); the plan completes; Studio then opens with the plan's change in it |
| the writer killed mid-plan (no code of its own runs) | the project free at once; Studio opens it |
| a plan whose action fails; a plan refused by its lint | exit 1, the project free |
| ownership unavailable (fault injected) | apply-plan, undo and ai_job write nothing |
| a plan writing outside the project, or into another project inside it | refused before writing; the other world unchanged |
| ai_job in Studio / with the window's own hold / with the legacy editor active | refused before reading anything; no lock even asked |
| ai_job in a game window, Studio (another process) has the project | refused, nothing written; Studio's Save clean |
| ai_job in a game window, Studio closed | applied, scene reloaded, project free |
| Studio opening while ai_job writes | turned away until the job is written; the project free after |
| ai_job whose job raises | the project free |
| the real Studio while editing: ` | the console doesn't open (Studio takes the key) |
| the real Studio play-test: F4, `, `ai_job ...` typed, Enter | "nothing was changed. Mesh Studio has this project open in this window"; files identical; Stop keeps the unsaved work; Ctrl+S writes exactly it |

## 5. Regressions and fault injection

The new tests on the baseline (the 11 written first; the start-gate race test came after and isn't a deterministic regression) (`regression_before.txt`): **10 fail**, each at the defect (the refusal
expected, "Executing plan" / "Applied 2 operation(s)" found; Studio opening while the plan was pending; the files
changed); the one that passes is the control (the Studio-closed path keeps working).

Fault injection (`faults.json`, `mutate_r4.py.txt`): each mutation removes or weakens one part, the targeted tests
run, the file is put back byte for byte.

| Mutation | Caught by |
|---|---|
| ai_job: no refusal inside an editing window (`engine/console_runtime/handlers_ai.py`) | 2 failed in 8.49s: test_ai_job_is_refused_in_a_window_that_edits_the_project, test_ai_job_typed_into_the_console_of_a_studio_play_test_changes_nothing |
| ai_job: the window's own hold on the project taken as a pass (`engine/console_runtime/handlers_ai.py`) | 1 failed in 3.40s: test_ai_job_is_refused_in_a_window_that_edits_the_project |
| ai_job: the legacy editor being active not checked (`engine/console_runtime/handlers_ai.py`) | 1 failed in 3.24s: test_ai_job_is_refused_in_a_window_that_edits_the_project |
| ai_job: writes without owning the project (`engine/console_runtime/handlers_ai.py`) | 2 failed in 7.13s: test_ai_job_holds_the_project_while_it_writes_and_lets_it_go_however_it_ends, test_ai_job_in_a_game_window_is_refused_while_studio_has_the_project_and_works_once_closed |
| ai_job: lets the project go before writing (`engine/console_runtime/handlers_ai.py`) | 1 failed in 4.65s: test_ai_job_holds_the_project_while_it_writes_and_lets_it_go_however_it_ends |
| ai_job: never lets the project go (`engine/console_runtime/handlers_ai.py`) | 2 failed in 8.44s: test_ai_job_holds_the_project_while_it_writes_and_lets_it_go_however_it_ends, test_ai_job_in_a_game_window_is_refused_while_studio_has_the_project_and_works_once_closed |
| apply-plan: writes without owning the project (`mesh_cli/ai.py`) | 3 failed in 10.94s: test_a_competing_writer_or_an_editor_holding_the_project_stops_the_plan, test_apply_plan_and_undo_are_refused_while_mesh_studio_has_the_project, test_mesh_studio_opening_during_a_plan_is_turned_away_until_it_is_written |
| undo-last-plan: writes without owning the project (`mesh_cli/ai.py`) | 2 failed in 19.75s: test_a_competing_writer_or_an_editor_holding_the_project_stops_the_plan, test_apply_plan_and_undo_are_refused_while_mesh_studio_has_the_project |
| apply-plan: never lets the project go (`mesh_cli/ai.py`) | 2 failed in 3.58s: test_apply_plan_with_studio_closed_writes_and_lets_the_project_go, test_failed_plans_and_unavailable_ownership_leave_no_hold_and_no_change |
| apply-plan --dry-run made to own the project (read-only refused) (`mesh_cli/ai.py`) | 1 failed in 11.17s: test_apply_plan_and_undo_are_refused_while_mesh_studio_has_the_project |
| plan executor: writes outside the owned project (`engine/tooling/plan_executor.py`) | 1 failed in 3.38s: test_a_plan_writes_only_inside_the_project_it_owns |
| plan executor: writes into another project inside the owned one (`engine/tooling/plan_executor.py`) | 1 failed in 3.40s: test_a_plan_writes_only_inside_the_project_it_owns |

**12/12 caught.**

## 6. Limits, and what is left as it was

- **Not transactional** (unchanged, reported as asked): a plan has no automatic rollback (an action failing part
  way leaves the earlier ones written, its backup manifest finished, so `undo-last-plan` can restore them), and
  `ai_job` applies each operation on its own (one failing leaves the others written). The ownership now covers
  those partial writes and their backups; it doesn't make them atomic.
- `undo-last-plan` restores the files as they were before the plan, overwriting anything saved since, Studio's
  saves included (now never while Studio is open). Its manifest paths are relative to the folder the plan ran in.
- `mesh plan test` / `test-ai` apply the plan in a temporary copy; a plan with absolute paths would escape that
  sandbox (`safe_paths_only=False`). Unchanged: not an apply command.
- The human wizards built on `PlanExecutor` (`mesh place-npc`, `mesh add-puzzle`, `mesh scene edit`) write the
  same way without ownership. Out of this brief's scope ("unrelated CLI commands"); a one-line follow-up each.
- **Found, not fixed (separate follow-up):** MCP `apply_ops`' direct-file fallback (operations that aren't room
  edits: world, quests, cutscenes) and MCP `create_scene` check that nothing has the project open
  (`_files_blocked`, F1) but don't *hold* the project while `AIOps` writes. Probed (`probe_mcp.json`,
  `probe_mcp.py.txt`, with a pause between the check and the write standing in for the race): a Studio opened in
  between, and the world file was then written while Studio owned the project. Not fixed here: outside the two named
  paths. The fix is the same few lines (`acquire` around `AIOps`).
- The legacy editor opened with F4 inside a game window takes the project only through its live bridge, and keeps
  editing without it if the bridge can't start (R2's existing behaviour). `ai_job` refuses there anyway (it checks
  the editor being active, not only the hold).

## 7. Validation

Local, Windows, Python 3.13 (`-W error`):

- the new tests: `tests/test_ai_write_paths.py` (11) and `tests/test_ai_write_paths_gpu.py` (1, `MESH_GL_SMOKE=1`),
  with `tests/test_ai_console.py`: **13 passed**;
- the neighbours (apply-plan, plan executor, assist, pipeline, CLI help, `AIOps`, the console) and R1/R2/R3/S4/F1
  (`test_studio_project_ownership`, `test_authoring_session*`, `test_studio_revision_identity`,
  `test_studio_object_identity`, `test_room_file_ownership`, `test_one_editing_path`,
  `test_ai_preview_player_summary`): **264 passed, 1 skipped**;
- the real-window R1/R2/S4 suites with the new one (`test_studio_project_ownership_gpu`,
  `test_studio_revision_identity_gpu`, `test_room_file_ownership_gpu`, `test_ai_write_paths_gpu`): **12 passed**;
- `tooling.ruff_gate` ok, `tooling.mypy_gate` ok.

`tests/test_ai_console.py` now runs in a temporary folder (ai_job owns the folder it runs in while it writes:
never the checkout).

### PR #521: CI and Extended (first attempts, none rerun)

- head `97759e57`: **CI failed** (run 44301684577, attempt 1): `tests/test_runtime_editor_import_boundary.py::
  test_runtime_modules_do_not_import_editor` on Linux and Windows shard 2/2. The cause was this change:
  `engine/console_runtime/handlers_ai.py` (runtime code) now imports `engine.editor` (`project_ownership`). Every
  other test passed (Linux 12,132 passed, 1 failed). The focused local run had not included that boundary test.
  **Extended passed** (run 44301692241, attempt 1, every lane). Fixed in the next commit with a documented entry
  in the test's `ALLOWED_VIOLATIONS`: the import is the project lock (no editor UI), taken lazily, and the brief
  asks for `project_ownership` to be reused. Hiding it behind a call into a non-runtime module would satisfy the
  check without changing the dependency.

FINAL_RESULTS
