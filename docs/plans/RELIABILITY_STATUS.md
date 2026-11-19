# Mesh reliability: status board

Maintained by the master only (workers report in their PRs). GitHub is the source of truth: a fresh master session
rechecks every row (`RELIABILITY_COORDINATION.md` §5) before acting. IDs and priorities: `MESH_RELIABILITY_MASTER_PLAN.md`.

**As of 2026-11-19.** Integration `redesign/visual-editor` = `ad91e28c665ae6adc22be4ce0b2c4e7d26e1817b`
(post-merge CI 44507117728 and Extended 44507117836 green, attempt 1).

States: `QUEUED` · `DISCOVERED` (source located, not reproduced) · `IN PROGRESS` · `READY FOR REVIEW` · `APPROVED`
(master) · `MERGED + VERIFIED`. Approval: `OWNER` = the owner must approve the merge.

| ID | Pri | Agent | State | Branch / PR | Base → head | Evidence | Master verdict | Approval | Next action |
|---|---|---|---|---|---|---|---|---|---|
| A-00 stale-content plan undo | P1 | (implemented before the agents; original implementer: the Opus master session) | READY FOR REVIEW | `fix/stale-plan-undo` / #525 (draft) | `ad91e28c` → `5fd408d6` | CI 44517832117 ✓ a1; Extended 44517840518 ✓ a1; 23 new CLI tests; 8/8 faults | **APPROVE** (independent Sonnet review + master), non-blocking follow-ups F1, F2 below | OWNER | owner decides: merge as is, or fold in F1/F2 first |
| A-01 `mesh new --force` deletion | P0 candidate | mesh-creator-safety | DISCOVERED | (none yet) | base `ad91e28c` | source-confirmed: `mesh_cli/blank_project.py:42` `(dest/name).resolve()` then `:60` `shutil.rmtree`; only an engine-folder check before it; `..`/absolute names reach it; one test (`test_cli_new_project_command_contract.py::test_refuses_to_overwrite_without_force`) | brief ready (owner go needed) | OWNER | dispatch A-01 to Agent A in `D:\Games\Mesh-A-01` |
| B-01 duplicate-name entity save identity | P1 | mesh-gameplay-reliability | DISCOVERED | (none yet) | base `ad91e28c` | source-confirmed: `engine/save_runtime/entity_state.py:220` keys by `mesh_name`; load map `:527-531` last-wins; `sprite.mesh_id` exists (`entity_factory.py:120`) but unused; save-format change = migration | brief ready (owner go needed) | OWNER (migration) | dispatch B-01 to Agent B in `D:\Games\Mesh-B-01` |
| B-02 primary tag after load | P1/P2 | mesh-gameplay-reliability | DISCOVERED | after B-01 (same file) | | source-confirmed: tags sorted `:309`, `mesh_tag = state.tags[0]` `:413` | | OWNER | queue behind B-01 |
| Plan doc | | master | READY FOR REVIEW | `docs/reliability-master-plan` / #526 (draft) | `ad91e28c` → `7b69ef33` | docs only | corrections listed in the coordination PR | owner | owner applies corrections, merges |
| Agent definitions + runbook | | master | READY FOR REVIEW | `docs/reliability-agents` / this PR (draft) | `ad91e28c` → (see PR) | docs + `.claude/agents/` only | | owner | owner review |

## Follow-ups noted by reviews (not assigned)

- **F1 (A-00, P2):** `BackupManager.finish_backup` fingerprints files; an `OSError` there (a file locked by another
  process) leaves the plan written with no manifest (undo then refuses, safely), and on the error path replaces the
  plan's own error. Correction: catch it around `finish_backup` in `PlanExecutor.execute`, log, keep raising the
  original error; or record such a file as `{"exists": true, "sha256": null}` (never restorable). Test: a fingerprint
  that raises.
- **F2 (A-00, informational):** `_unverified` accepts `{"exists": 0}` as `{"exists": false}` (`0 == False`); require
  `record["exists"] is False`. Hand-edited manifests only.
- **#524 review, low:** `engine/json_io.write_text_atomic` writes `<target>.tmp` unchecked; a planted hard link there
  redirects the write. Correction: exclusive temporary file (`mkstemp` in the same folder), refuse links.

## Worktrees in use

| Worktree | Holds |
|---|---|
| `D:\Games\Mesh-staleundo` | #525 |
| `D:\Games\Mesh-relmaster` | this PR |
| `D:\Games\Mesh-agent-a`, `D:\Games\Mesh-agent-b` | read-only probes, detached at `ad91e28c` |
