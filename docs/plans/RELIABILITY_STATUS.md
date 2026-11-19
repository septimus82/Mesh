# Mesh reliability: status board

Maintained by the master only (workers report in their PRs). GitHub is the source of truth: a fresh master session
rechecks every row (`RELIABILITY_COORDINATION.md` §5) before acting. IDs and priorities: `MESH_RELIABILITY_MASTER_PLAN.md`.

**As of 2026-11-19.** Integration `redesign/visual-editor` = `ad91e28c665ae6adc22be4ce0b2c4e7d26e1817b`
(post-merge CI 44507117728 and Extended 44507117836 green, attempt 1). Nothing merged since.

States: `QUEUED` · `DISCOVERED` (source located, not reproduced) · `IN PROGRESS` · `READY FOR REVIEW` · `APPROVED`
(master) · `MERGED + VERIFIED`. Approval: `OWNER` = the owner must approve the merge.

| ID | Pri | Agent (model) | State | Branch / PR | Base → head | Evidence | Master verdict | Approval | Next action |
|---|---|---|---|---|---|---|---|---|---|
| A-00 stale-content plan undo | P1 | original Opus session; independent review by a Sonnet reviewer | APPROVED | `fix/stale-plan-undo` / #525 (draft) | `ad91e28c` → `5fd408d6` | CI 44517832117 ✓ a1; Extended 44517840518 ✓ a1; 23 CLI tests; 8/8 faults | **APPROVE**; F1, F2 tracked separately (not in #525) | OWNER | merge on owner approval (order below) |
| A-01 `mesh new --force` deletion | P0 | mesh-creator-safety (Sonnet) | READY FOR REVIEW | `fix/a01-new-force-deletion` / #529 (draft) | `ad91e28c` → `0db758cc` | reproduced on base (6 cases deleted markers, exit 0); head: all refused, markers intact; 16 of 20 new tests fail on base; 18 pass + 2 skips on head; 4/5 faults caught (link check alone masked by Python 3.13's own `rmtree` junction refusal) | **APPROVE** pending its first CI/Extended (see PR) | OWNER | merge on owner approval |
| B-01 duplicate-name entity save identity | P1 | mesh-gameplay-reliability (Sonnet) | READY FOR REVIEW (design) | `design/b01-entity-save-identity` / #528 (draft, docs only) | `ad91e28c` → `c08b68e0` | reproduced on base through SaveManager + hidden GameWindow (two "Goblin" records land on one sprite, other keeps authored state, no diagnostic) | **design accepted with one change**: keep name-keying for id-less entities with a unique name (dropping them would lose runtime-spawned state); owner answers open questions 1–6 | OWNER (migration v2→v3) | owner decisions, then B-01 implementation brief |
| B-02 primary tag after load | P1/P2 | mesh-gameplay-reliability | DISCOVERED | after B-01 (same file) | | `entity_state.py:309` sorted tags, `:413` `mesh_tag = state.tags[0]` | | OWNER | queue behind B-01 |
| Plan doc | | master (corrections) | READY FOR REVIEW | `docs/reliability-master-plan` / #526 (draft) | `ad91e28c` → `a9d89f01` | docs only; #525 status and evidence provenance corrected | integrate | owner | merge on owner approval |
| Agent definitions + runbook + board | | master | READY FOR REVIEW | `docs/reliability-agents` / #527 (draft) | `ad91e28c` → (see PR) | docs + `.claude/agents/`; CI 44531913505 ✓ a1 on `11492053` | integrate | owner | merge on owner approval |

## Proposed merge order (owner approval required; one at a time)

1. #525, then post-merge CI + Extended on the new tip.
2. #529, then post-merge CI + Extended.
3. #526 (docs), then CI.
4. #527 (docs), refreshed with the merge SHAs above in a last commit before merging, then CI.

No file overlaps between them. Each merge: head unchanged, `git merge-tree` equals the reviewed tree, merged tree
checked. #528 stays open as the design record until the owner answers its questions.

## Follow-ups noted by reviews (not assigned)

- **F1 (A-00, P2):** an `OSError` while `finish_backup` fingerprints a file leaves the plan written with no manifest
  (undo then refuses, safely) and, on the error path, replaces the plan's own error. Correction: catch around
  `finish_backup` in `PlanExecutor.execute`, keep raising the original error; or record the file as
  `{"exists": true, "sha256": null}`.
- **F2 (A-00, informational):** `_unverified` accepts `{"exists": 0}` as absent; require `record["exists"] is False`.
- **A-01, low:** the link check has no test that fails without it on Python 3.13 (rmtree refuses junctions itself);
  Windows reserved device names (`CON`, `NUL`) aren't refused (no deletion outside the target).
- **#524 review, low:** `engine/json_io.write_text_atomic` writes `<target>.tmp` unchecked; a planted hard link there
  redirects the write. Correction: exclusive temporary file (`mkstemp` in the same folder), refuse links.

## Task log (models and usage, as reported by the Agent tool)

| Task | Model | Tool calls | Tokens | Output |
|---|---|---|---|---|
| A-01 probe (read-only) | Sonnet 5.5 | 11 | ~72k | located the deletion path |
| B-01/B-02 probe (read-only) | Sonnet 5.5 | 6 | ~75k | located keying and tag code |
| plan reference lookup | Haiku 5.5 | 11 | ~68k | 8 references confirmed |
| #525 independent review | Sonnet 5.5 | 8 | ~87k | APPROVE, F1/F2 |
| A-01 implementation | Sonnet 5.5 | 36 | ~102k | #529 |
| B-01 design | Sonnet 5.5 | 44 | ~140k | #528 |

## Worktrees in use

| Worktree | Holds |
|---|---|
| `D:\Games\Mesh-staleundo` | #525 |
| `D:\Games\Mesh-A-01` | #529 |
| `D:\Games\Mesh-B-01` | #528 |
| `D:\Games\Mesh-plan526` | #526 (master's corrections) |
| `D:\Games\Mesh-relmaster` | #527 |
| `D:\Games\Mesh-agent-a`, `D:\Games\Mesh-agent-b` | read-only probes, detached at `ad91e28c` (removable with owner's OK) |
