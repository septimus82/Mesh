# Mesh reliability: status board

Maintained by the master only (workers report in their PRs). GitHub is the source of truth: a fresh master session
rechecks every row (`RELIABILITY_COORDINATION.md` §5) before acting. IDs and priorities: `MESH_RELIABILITY_MASTER_PLAN.md`.

**As of 2026-11-19 (cycle 3).** Integration `redesign/visual-editor` = `0e05bd94723f8eb137acd900b1bc03ada0ba59e2` when
this board was written (this board lands with PR #532: `gh pr view 532 --json mergeCommit`).

## Integration record

| PR | Merge commit | Tree (= reviewed) | Post-merge CI | Post-merge Extended |
|---|---|---|---|---|
| #525 stale-content undo | `d2dee7cf` | `baf97aea` | 44544167005 ✓ a1 | 44544167843 ✓ a1 |
| #529 A-01 `mesh new --force` | `190f5349` | `445a000b` | 44549684496 ✓ a1 | 44549684498 ✓ a1 |
| #526 master plan | `7307a48f` | `d3409df5` | 44556297528 ✓ a1 | 44556297554 ✓ a1 |
| #527 agents, runbook, board | `b095ecd4` | `d331da0e` | 44564645751 ✓ a1 | 44564645911 ✓ a1 |
| #531 B-01b duplicate-id snapshot | `55bdd589da2fa5737cf7bc99f19841db82d9e324` | `2a9397f5` (= head `77d72f5c`) | 44589776415 **✗ a1 (waived, see below)** | 44589776439 ✓ a1 |
| #530 A-02 quest list erasure | `0e05bd94723f8eb137acd900b1bc03ada0ba59e2` | `a5bb55f4` (= tip + exactly #530's reviewed diff) | 44596602343 ✓ a1 | 44596602245 ✓ a1 |

**Waiver (owner, one-time, narrowly scoped; not a relaxation of CI).** Post-merge CI run 44589776415 on `55bdd589`
FAILED at attempt 1: one Windows test,
`tests/test_mcp_project_ownership_root.py::test_a_nested_project_is_edited_under_its_own_ownership[apply_ops]` (the
windowless Studio helper exited 1 before answering its second command; 6,120 passed in that shard). Extended attempt 1
PASSED. Probable cause: transient command-file access in `tests/studio_owner_process.py` (a previously observed Windows
helper flake). Exact exception in the failed run: **unconfirmed** (the helper's stderr is not in the CI log). The
failed run and its logs are preserved; it was not rerun and is not counted as green. Follow-up: T-01.

**#531's own history (kept):** heads `a51c9e86` (CI 44577439782 ✗, Extended 44577435395 ✗: ruff gate) and `06c48cda`
(CI 44580098831 cancelled) preceded the reviewed head `77d72f5c` (CI 44580262193 ✓ a1, Extended 44580263301 ✓ a1).
Only the final head passed at attempt 1.

## Work

States: `QUEUED` · `DISCOVERED` · `IN PROGRESS` · `READY FOR REVIEW` · `APPROVED` (master) · `MERGED + VERIFIED`.
Approval: `OWNER` = the owner must approve the merge.

| ID | Pri | Agent (model) | State | Branch / PR | Base → head | Evidence | Master verdict | Approval | Next action |
|---|---|---|---|---|---|---|---|---|---|
| A-02 quest list erasure | P1 | mesh-creator-safety (Sonnet) | MERGED + VERIFIED | #530 → `0e05bd94` | `b095ecd4` → `62af786b` | see #530 | APPROVED | owner approved | |
| B-01b duplicate-id snapshot | P1 | mesh-gameplay-reliability (Sonnet) | MERGED (post-merge CI waived) | #531 → `55bdd589` | `b095ecd4` → `77d72f5c` | see #531 | APPROVED after one correction | owner approved | |
| A-02b dict-form quests without `"id"` | P2 | mesh-creator-safety (Sonnet) | IN PROGRESS | `fix/a02b-dict-quest-ids` (worktree `D:\Games\Mesh-A-02b`) | base `0e05bd94` | `engine/quests.py` loader ignores dict keys; `normalize.py` drops entries without `"id"` | | OWNER | review the draft PR |
| B-01 save identity migration (v3) | P1 | mesh-gameplay-reliability (Sonnet) | IN PROGRESS (implementation authorised) | `fix/b01-save-identity-migration` (worktree `D:\Games\Mesh-B-01-impl`) | base `0e05bd94` | spec: design rev 3, #528 (`99e1768e`) | | OWNER + independent review | review the draft PR |
| T-01 Studio helper command-file flake | test infra | mesh-creator-safety (Sonnet) | QUEUED (after A-02b) | | | the waived failure above; earlier local `PermissionError` on `0002.cmd` | | owner | reproduce; limited retry for Windows sharing violations only (no other errors swallowed, no assertion weakened); child-process exceptions surfaced in CI output |
| B-01 design | | | READY (docs) | #528 (draft) | `ad91e28c` → `99e1768e` | rev 3 with the owner's decisions | design complete | owner | merge with or before the B-01 implementation |
| B-02 primary tag after load | P1/P2 | mesh-gameplay-reliability | DISCOVERED | after B-01 (same file) | | `entity_state.py:309`, `:413` | | OWNER | queue behind B-01 |

## Follow-ups noted by reviews (not assigned)

- **F1 (A-00, P2):** an `OSError` while `finish_backup` fingerprints a file leaves the plan written with no manifest
  (undo then refuses, safely) and, on the error path, replaces the plan's own error.
- **F2 (A-00, informational):** `_unverified` accepts `{"exists": 0}` as absent; require `record["exists"] is False`.
- **A-01, low:** the link check has no test that fails without it on Python 3.13; Windows reserved names (`CON`, `NUL`)
  aren't refused (no deletion outside the target).
- **#524 review, low:** `engine/json_io.write_text_atomic` writes `<target>.tmp` unchecked (a planted hard link there
  redirects the write); exclusive temporary file, refuse links.
- **B-01b, informational:** twins pair by order (positional if the room file was reordered since the save).
- **Process:** workers run the gates on the exact commit they push (a "ruff ok" report preceded a ruff-red head).

## Task log (models and usage, as reported by the Agent tool)

| Task | Model | Tool calls | Tokens | Output |
|---|---|---|---|---|
| cycle 1 (probes, lookup, #525 review, A-01, B-01 design + rev 2) | Sonnet 5.5 ×6, Haiku 5.5 ×1 | 136 | ~725k | #529, #528, verdicts |
| cycle 2: A-02 | Sonnet 5.5 | 19 | ~94k | #530 |
| cycle 2: B-01b rounds 1 + 2 | Sonnet 5.5 | 107 | ~274k | #531 |
| cycle 3: A-02b, B-01 implementation | Sonnet 5.5 ×2 | (running) | | |

## Worktrees in use

| Worktree | Holds |
|---|---|
| `D:\Games\Mesh-A-02b` | A-02b (in progress) |
| `D:\Games\Mesh-B-01-impl` | B-01 implementation (in progress) |
| `D:\Games\Mesh-B-01` | #528 |
| `D:\Games\Mesh-board` | this board (#532) |
| `D:\Games\Mesh-A-02`, `D:\Games\Mesh-B-01b` | merged work (#530, #531): removable after verification |
