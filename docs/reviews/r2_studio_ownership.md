# R2: one writable Mesh Studio per project

#462 R2. Two Mesh Studio processes could open one project, and closing the second let outside tools write the
project's files behind the first. Baseline `ad762a2b` (`redesign/visual-editor`). Evidence:
`docs/reviews/r2_studio_ownership_evidence/`.

**Verdict: READY FOR RE-REVIEW** (the independent review's recovery-boundary finding is corrected: section 9).

## 1. The defect, reproduced

Two real processes (`tests/studio_owner_process.py`: Studio's own project documents, AI host and live-session
bridge), the outside tool `engine.authoring_session.apply`, on the baseline (`repro_before.json`):

| step | what happened |
|---|---|
| Studio A opens, makes an unsaved edit | A's session is the project's |
| Studio B opens the same project | **let in**; the discovered session is now B's |
| B closes | the record is removed: outside tools see `state: none`, while A is still open |
| an outside tool applies a change | `ok: true, source: "files"`: written to disk |
| A, in memory | still its own unsaved edit; it never saw the change |
| A saves | its version replaces the file; the tool's change survives only as `start.json.outside-change.bak` |

A regression test for this failed on the baseline before anything was changed
(`test_a_second_studio_opening_and_closing_never_lets_outside_changes_past_the_first`: "the second Studio was let in").

## 2. Root cause

The session record (`.mesh/live_session.json`) was the only thing that said a project was open, and it was last
writer wins: `write_live_session_file` replaced whatever was there, and `delete_live_session_file` removed it if the
ids matched. Replacing it atomically made each write whole; it never made a project one editor's. Nothing stopped a
second Studio opening, and nothing but the record told outside tools that a Studio was there.

## 3. The mechanism

`engine/editor/project_ownership.py`: an operating-system file lock on `<project>/.mesh/owner.lock`, held on an open
file for as long as the owner lives. `LockFileEx` on Windows, `flock` elsewhere; both from the standard library, no
new dependency.

Why this:

- **It belongs to the open file**, so a second owner is refused whether it is another process or another part of
  the same one, on both systems.
- **The operating system releases it** the moment the process ends, however it ended. A crashed Studio cannot lock a
  project for good, and no process id is ever read to decide whether an owner is alive.
- **Nothing else is needed to hold it**: no bridge, no HTTP, no record. A Studio with its live session turned off
  owns its project just the same.
- **Asking takes nothing.** `owned(root)` takes the lock shared for an instant, so any number may ask at once and
  none is an owner; a project with no lock file is free, and asking creates none. An owner made at that instant
  waits a moment (`wait`) before giving up.
- The lock file is never deleted (deleting a lock file is itself a race). It stays in `.mesh`, the project's
  existing folder for editor state, which git ignores and the export skips. The few bytes in it (who, since when)
  are for messages only.

**Who owns a project, and when:**

| owner | from | until |
|---|---|---|
| Mesh Studio launched by `mesh edit` or the launcher | before a window exists or a file is read (`game_launch._run_editor`) | the window has closed (`GameWindow.close`: session stopped, record removed, then the lock) |
| Mesh Studio opened directly (`open_studio`, as tools and tests do) | before `Project.open` | the same |
| the live-session bridge | `start()`, before it serves or publishes: with Studio's hold if given, else its own | `stop()`, after its record is removed, if the hold was its own |
| an outside tool's direct write (`authoring_session.apply`) | before the files are read | they are saved (or the write failed) |
| `mesh author recover` | while it removes an abandoned record | it has |

Only an owner writes or removes the session record. So a second editor never replaces the first one's, and closing
never removes another's.

## 4. Behaviour

**A second Studio** is refused: "This project is already open in Mesh Studio. Use the window that has it: a project
can be open in one Mesh Studio at a time, so that neither overwrites the other's unsaved work." `mesh edit` exits
with code 3 before it opens a window; the launcher shows the message instead of "closed straight away". The first
Studio's record, session and unsaved work are untouched.

**What outside tools are told** (`live_session_client.session_state`; the three states are as they were):

| the project | state | what the tool does |
|---|---|---|
| a verified Studio session | `live` | proposes to it |
| no record, no owner | `none` | writes the files, owning the project while it does |
| a record that can't be verified, and an owner | `uncertain`, `owned: true` | refuses; the message says Studio is running and not to delete its record |
| a record, and no owner (its Studio crashed or was killed) | `uncertain`, `owned: false` | refuses; the message says no editor has it now, and how to recover |
| no record, and an owner | `uncertain`, `owned_without_session` | refuses: a Studio still starting, one with its live session off, or a tool writing at that moment |
| ownership can't be told | `uncertain`, `ownership_unknown` | refuses |

The existing reason codes are unchanged; `owned` is added to `problem`.

**At the write boundary.** `apply` used to check for a session a second time just before writing; a Studio could
still open between that check and the write, or between the read and the write. It now owns the project from
before it reads the files until they are saved. A Studio started meanwhile waits up to two seconds for the project
and then opens on the files as written; if a Studio got there first, `apply` is refused (`studio_open`,
`other_editor_open`, or `project_busy` for another tool).

**After a crash.** The lock is gone with the process, so another Studio opens the project at once and its record
replaces the old one. Until then the old record still refuses direct writes: the crashed Studio may have held
unsaved work the person will want to know about, and a record is never removed to make a write possible.
`mesh author recover` removes it on purpose; it owns the project while it does, so with an editor open it removes
nothing. It removes only the record of the project it was given and owns (section 9).

## 5. Evidence

**The reproduction, before and after** (`repro_before.json`, `repro_after.json`): after, B is refused; the session
discovered is A's at every step; the tool's change is proposed to A; nothing on disk changes; A's save makes no
backup.

**Separate processes** (`tests/test_studio_project_ownership.py`, 21 tests, default lane, both systems in CI;
26 with the churn note test and the recovery-boundary tests of section 9):

| # in the brief | test |
|---|---|
| 1-8 | a second Studio opening and closing never lets outside changes past the first (A owns, B refused, A discoverable, change proposed to A, A saves, A closes, C opens) |
| 9 | a crashed Studio's record authorizes nothing until recovered on purpose; after a crash the next Studio opens the project; recovery takes nothing from a running Studio; `mesh author recover` says what it did |
| 10 | a running Studio whose session can't be confirmed (a malformed record; a record nobody answers at) is never written behind |
| 11 | two projects are each edited in their own Studio |
| 12 | of six Studios started at once, one owns the project; a Studio opening as another closes gets the project only once it is let go; a Studio opening during an outside write opens on what was written |
| 13 | a Studio without a live session still owns its project |
| launch | `mesh edit` refuses before it opens a window, exit code 3 |
| the lock | one owner, asking takes nothing and makes no file; many ask at once while owners are made; someone asking is not an owner to another who asks; waiting gets the project when a brief owner lets go |
| faults | ownership that can't be established is not taken as free (no locks; the ownership file can't be made); a session that fails to publish leaves nothing behind (no server, no record, no hold); a second session in one process is refused and touches nothing; letting go never fails |

**Mesh Studio itself** (`tests/test_studio_project_ownership_gpu.py`, 2 tests, GPU lane): real Studio processes
with real hidden windows through `open_studio`, and `mesh edit` run as the launcher runs it: the second is refused
with exit code 3 before a window opens; an outside change goes to the first; a Studio with
`MESH_STUDIO_NO_AI_BRIDGE` still owns its project; after a kill the next Studio opens it.

**Deliberate faults** (`faults.json`): see section 6.

**Existing suites**, unchanged in what they assert except as listed in section 7: the bridge, discovery, policy,
request-state, proposal and save suites (216 tests) pass; 42 existing real-window Studio tests that close and
reopen Studio in one process pass.

## 6. Fault injection

`mutate_ownership.py.txt` breaks one thing at a time and runs the cross-process tests (and the existing discovery
suite where marked). **15 of 15 fail a test** (`faults.json`):

| fault | tests that fail |
|---|---|
| the lock is never taken: every owner is let in (the defect itself) | 14 of 20, and 3 of the existing discovery suite |
| the bridge publishes its record without owning the project | 1 |
| a bridge that stops lets go of a project it was only given | 1 |
| a bridge that took the project itself keeps it when it stops | 2, and 2 existing |
| a session that fails to publish keeps the project and its server | 1 |
| outside tools take a project with no record as free whoever owns it | 1 |
| ownership that can't be told is taken as free | 1 |
| an abandoned record is reported as a running Studio's | 1 |
| a direct write does not own the project | 2, and 3 existing |
| recovery removes the record without owning the project | 4 |
| asking whether a project is owned takes it (exclusive, not shared) | 1 |
| asking makes the lock file | 2 |
| an owner never waits | 4 |
| letting go leaves the file open | 10 |
| `mesh edit` opens its window before it owns the project | 1 |

The first run left one alive: asking with an exclusive lock. The test for many asking at once could not tell the
difference (an asker turned away by another simply tried again). A direct test was added: with one asker holding
the lock shared, another is still told the project has no owner.

## 7. Existing tests changed

- `tests/test_authoring_session_discovery.py`
  - *an editor opening between the check and the write*: it faked the second state check. There is no second check
    now; the test takes the project for real (as Studio, as the legacy editor, as another tool) at that moment and
    expects the write refused.
  - *a Studio that stopped answering ... and recovers*: it stood for both "frozen" and "crashed", and then opened a
    second Studio beside the first. A frozen Studio still owns its project; the test now lets the hold go as a
    crash does. The frozen case is the health-check tests above it, which pass unchanged.
  - its file comparison leaves out `.mesh/owner.lock`.
- `tests/test_project_save_transaction.py`, `tests/test_room_file_ownership.py`, `tests/test_safe_scene_creation.py`:
  their whole-tree comparisons leave out `.mesh`. A direct write now leaves the lock file there, also when its
  save fails.
- `tooling/d1_debug_scenario.py`, `tooling/d2_ai_playtest_scenario.py` (the scenarios behind
  `tests/test_runtime_debugger_gpu.py` and `tests/test_ai_playtest_gpu.py`): each stood for "Studio closes" by
  stopping its session only, and then expected `studio_not_open`. A Studio whose session has stopped but which is
  still open owns its project (`owned_without_session`). They now close as Studio closes: `release_project()`.

**The first CI and Extended runs failed, and are kept** (head `1f855cbb`: CI 44104873884, Extended 44104866232).
Five tests, none run locally before the push (the brief asked for targeted local runs, and these were not in mine):

| lane | test | cause |
|---|---|---|
| pytest, both systems | `test_safe_scene_creation.py` (2 tests) | a whole-tree comparison saw the new `.mesh/owner.lock` |
| pytest, Linux | this change's own "ownership can't be established" test | with `.mesh` a file, asking raised "not a directory" on Linux where Windows says "not found": the reason differed. `owned` now takes both as "no lock file" |
| gpu, both systems | `test_runtime_debugger_gpu.py`, `test_ai_playtest_gpu.py` (1 each) | the scenarios' "Studio closes" (above) |

The other 20 cross-process tests and both real-window tests passed on Linux and Windows in those runs. Corrected
in the next commit (`b51c1dc7`). Not rerun.

**The second CI run failed too, and is kept** (head `b51c1dc7`: CI 44110970103; one job, Windows pytest shard 2/2,
1 failed of 6,001). `test_many_may_ask_at_once_and_an_owner_being_made_waits_for_them` asserted that, while owners
are made and let go as fast as possible, nobody asking is ever told "owned, by someone whose note can't be read"
(`{}`). That is a real answer, and the documented one: an owner holds the lock for an instant before its note is
written, and for an instant after clearing it. `owned` asks again for up to a quarter of a second to get the note;
on that runner one of 1,600 asks ran out of time. It had passed on Windows in the first run and in every local run.

- Nothing in the product changed. `{}` is an owner to every caller (each tests `is None`, checked again for this),
  so the answer was never "free": a refusal's wording falls back to "open in Mesh Studio", nothing more.
- Measured locally (`churn_probe`, 8 askers against owners made in a loop): no `{}` in 32,000 asks at the normal
  wait; 10 in 32,000 at a fifth of it; 196 in 8,000 with no wait. So it is the wait running out, not a second cause.
- The assertion was mine, tightened during the fault-injection work to more than the mechanism promises. It now
  allows `{}` there, and a new test without a race pins what it was reaching for: an owner with no note yet is an
  owner (to someone asking, and to another owner being made), and asking waits for the note and returns it.

Extended on `b51c1dc7` passed at its first attempt (44110957374: every lane, Linux and Windows). CI not rerun.

## 8. Limits

- **The lock file stays** in `.mesh` once a project has been owned.
- **File systems without locks** (some network shares): ownership can't be established, so Studio refuses to open
  the project there and outside tools refuse to write it, each saying why. Nothing is taken as free.
- **Two paths to one folder** that the operating system doesn't resolve to the same one (a share and its local
  path) each get the same lock file, so they still exclude each other; two *copies* of a project are two projects.
- **Writers that never asked.** `mesh ai apply-plan` and the console's `ai_job` write files without consulting the
  session or ownership. They were outside the F1 contract and are outside this change.
- **The legacy editor** launched by `mesh edit` owns the project like Studio. Started some other way with its bridge
  off, it holds nothing.
- **Read-only tools that open Studio** on a project (`tooling/scene_snapshot.py`) are refused while a Studio has it.
- **Not addressed:** R1 (revisions reused across restarts) and R3 (ids reused for structures, rivers, dialogue
  lines).

## 9. Independent review: the recovery boundary

The review found, from the source, that `authoring_session.recover(A)` owned only A but removed the session record
of A **and** of A's discovery root, `_resolve_discovery_root(A)`. `find_repo_root` returns `MESH_REPO_ROOT` first
whenever it names a folder with a project marker, so the discovery root can be another project, B.

**Reproduced first, with the production code** (`recover_before.json`, `repro_recover.py.txt`, head `49206ba4`):
A has a record left by a Studio that crashed; B is open in Mesh Studio itself (a real hidden window, live session
on) with unsaved work. `mesh author recover --project A` run as its own process with `MESH_REPO_ROOT=B`:

| | before (`49206ba4`) | after |
|---|---|---|
| what recover reported removing | A's record **and B's** | A's record only |
| B's record | deleted | byte-identical |
| B's ownership | still B's Studio | still B's Studio |
| outside tools asking about B | `uncertain`, `owned_without_session` | `live`, B's session |
| an outside change to B | refused, `studio_session_uncertain` | proposed to B, waiting for review |
| B's unsaved work, B's files | intact, unchanged | intact, unchanged |
| A afterwards | `none` | `none` |

So the lock kept the failure closed (nothing was written behind B), but one project's repair cut another project's
running Studio off from outside tools until it was opened again. That is the defect: an action authorised by A's
ownership changed B.

**Root cause.** `remove_abandoned_session` reused discovery's "where may this project's record be" list (the folder
given, and its discovery root) as the list of records to delete. Discovery may look in more places than the caller
owns; removal must not.

**The correction** (smallest; ordinary discovery unchanged):

- `live_session_client.remove_abandoned_session(root)` removes `root`'s own record and nothing else.
- `authoring_session.uncertain`: when the leftover record it reports belongs to another folder (found through the
  discovery root), its advice now names that folder: `` `mesh author recover --project "<the record's project>"` ``,
  so the record can still be recovered, by owning the project it belongs to. Before, it said `mesh author recover`,
  which (with the correction) would remove nothing.

No second lock is taken; recovery still refuses a project that is owned, and still answers `ownership_unknown`
when ownership can't be established. Reason codes and answers are unchanged.

**Regressions** (`tests/test_studio_project_ownership.py`, separate Studio processes; the first three fail on
`49206ba4`, checked by running them against the unchanged production files):

- recovering A never touches B open in Studio, in-process (`MESH_REPO_ROOT=B`) and through `mesh author recover`
  as its own process: A's record removed, B's record byte-identical, B still owned by its Studio and `live`, an
  outside change proposed to B with B's unsaved work intact, A then `none` (2 cases);
- a record found through `MESH_REPO_ROOT` (B's Studio crashed, A has no record): writing A is refused as before, the
  advice names B, recovering A removes nothing, recovering B removes B's record;
- recovery refuses a project open in Studio (A) and touches no other (B), `MESH_REPO_ROOT=B`, through the CLI (a
  guard: it passed before too).

The existing recovery tests (a genuinely abandoned record recovered; refused while a Studio runs; `mesh author
recover` single-project) are unchanged and pass.

**Local:** the ownership, authoring-session (discovery, policy, session), request-state and repo-root modules, 103
passed; the real-window ownership tests, 2 passed; ruff and mypy.

**Limits, changed.** A record that is found only through the discovery root is no longer removed by recovering the
folder that found it; it is removed by recovering its own project, as the refusal says.
