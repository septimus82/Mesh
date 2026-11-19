# Mesh reliability: status board

Maintained by the master only (workers report in their PRs). GitHub is the source of truth: a fresh master session
rechecks every row (`RELIABILITY_COORDINATION.md` §5) before acting. IDs and priorities: `MESH_RELIABILITY_MASTER_PLAN.md`.

**As of 2026-11-19.** Integration `redesign/visual-editor` = `7307a48f34d2ba8588bde21fb20b3a8daf4355e5` when this
board was written; this board itself lands with PR #527 (its merge commit is the next one: `gh pr view 527 --json
mergeCommit`). Owner-approved order integrated serially, each with tree identity checked and post-merge gates green:

| Merge | PR | Merge commit | Tree (= reviewed) | Post-merge CI | Post-merge Extended |
|---|---|---|---|---|---|
| 1 | #525 stale-content undo | `d2dee7cf37ae8f8073627992cddbdd488fc50d34` | `baf97aea` (= PR head tree) | 44544167005 ✓ a1 | 44544167843 ✓ a1 |
| 2 | #529 A-01 `mesh new --force` | `190f5349812014a9a993ecb1f618c7c74cf9766e` | `445a000b` (= tip + exactly #529's reviewed diff) | 44549684496 ✓ a1 | 44549684498 ✓ a1 |
| 3 | #526 master plan | `7307a48f34d2ba8588bde21fb20b3a8daf4355e5` | `d3409df5` (= tip + exactly #526's diff) | 44556297528 ✓ a1 | 44556297554 ✓ a1 |
| 4 | #527 this board | see `gh pr view 527` | | | |

States: `QUEUED` · `DISCOVERED` (source located, not reproduced) · `IN PROGRESS` · `READY FOR REVIEW` · `APPROVED`
(master) · `MERGED + VERIFIED`. Approval: `OWNER` = the owner must approve the merge.

| ID | Pri | Agent (model) | State | Branch / PR | Base → head | Evidence | Master verdict | Approval | Next action |
|---|---|---|---|---|---|---|---|---|---|
| A-00 stale-content plan undo | P1 | original Opus session; independent Sonnet review | MERGED + VERIFIED | #525 → `d2dee7cf` | `ad91e28c` → `5fd408d6` | PR gates ✓ a1; post-merge ✓ a1 | APPROVED | owner approved | F1/F2 follow-ups (below) |
| A-01 `mesh new --force` deletion | P0 | mesh-creator-safety (Sonnet) | MERGED + VERIFIED | #529 → `190f5349` | `ad91e28c` → `0db758cc` | reproduced (6 cases deleted markers); fixed; PR gates ✓ a1; post-merge ✓ a1 | APPROVED | owner approved | low follow-ups (below) |
| B-01 duplicate-name entity save identity | P1 | mesh-gameplay-reliability (Sonnet) | READY FOR REVIEW (design rev 2) | `design/b01-entity-save-identity` / #528 (draft, docs only) | `ad91e28c` → `ef6ddb9e` | base reproductions by running: duplicate names, id-less duplicates, duplicate-id clone | design covers the owner's three points; **one gap**: refused v3 records are dropped at the next save (state carry-forward or backup needed); owner questions 2, 7, 8, 9 | OWNER (migration v2→v3 not authorised) | owner decisions; worker revises the gap; then an implementation brief |
| B-01b snapshot merge of same-id sprites | P1? | (unassigned) | DISCOVERED | | | B-01 rev 2: `engine/scene_runtime/persistence.py:60-80` merges sprites sharing an id before saved state applies (a clone's hp lost) | | OWNER | owner decides (B-01 question 9) |
| B-02 primary tag after load | P1/P2 | mesh-gameplay-reliability | DISCOVERED | after B-01 (same file) | | `entity_state.py:309` sorted tags, `:413` `mesh_tag = state.tags[0]` | | OWNER | queue behind B-01 |
| A-02 quest list erasure | P1 | mesh-creator-safety | QUEUED | | | `engine/ai_ops.py:322` `payload["quests"] = {}` when the key isn't a dict | | OWNER | next Lane A task |

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
| A-01 implementation | Sonnet 5.5 | 36 | ~102k | #529 (merged) |
| B-01 design | Sonnet 5.5 | 44 | ~140k | #528 |
| B-01 design revision 2 (same agent, resumed) | Sonnet 5.5 | 20 | ~181k | #528 `ef6ddb9e` |

## Worktrees in use

| Worktree | Holds |
|---|---|
| `D:\Games\Mesh-B-01` | #528 |
| `D:\Games\Mesh-relmaster` | #527 |
| `D:\Games\Mesh-staleundo`, `D:\Games\Mesh-A-01`, `D:\Games\Mesh-plan526` | merged work (#525, #529, #526): removable with the owner's OK |
| `D:\Games\Mesh-agent-a`, `D:\Games\Mesh-agent-b` | read-only probes, detached at `ad91e28c` (removable with the owner's OK) |
