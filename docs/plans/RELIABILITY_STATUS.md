# Mesh reliability: status board

Maintained by the master only (workers report in their PRs). GitHub is the source of truth: a fresh master session
rechecks every row (`RELIABILITY_COORDINATION.md` §5) before acting. IDs and priorities: `MESH_RELIABILITY_MASTER_PLAN.md`.

**As of 2026-11-20 (cycle 5).** Integration `redesign/visual-editor` = `d89f32c4b0b1be502761c357b3a67ba34a4b9a39`
(post-merge CI 44720700860 ✓ a1, Extended 44720700937 ✓ a1). This board lands with its own PR (`gh pr list --head docs/reliability-status-cycle5`).

## Integration record

| PR | Merge commit | Tree (= reviewed) | Post-merge CI | Post-merge Extended |
|---|---|---|---|---|
| #525 stale-content undo | `d2dee7cf` | `baf97aea` | 44544167005 ✓ a1 | 44544167843 ✓ a1 |
| #529 A-01 `mesh new --force` | `190f5349` | `445a000b` | 44549684496 ✓ a1 | 44549684498 ✓ a1 |
| #526 master plan | `7307a48f` | `d3409df5` | 44556297528 ✓ a1 | 44556297554 ✓ a1 |
| #527 agents, runbook, board | `b095ecd4` | `d331da0e` | 44564645751 ✓ a1 | 44564645911 ✓ a1 |
| #531 B-01b duplicate-id snapshot | `55bdd589da2fa5737cf7bc99f19841db82d9e324` | `2a9397f5` (= head `77d72f5c`) | 44589776415 **✗ a1 (waived, below)** | 44589776439 ✓ a1 |
| #530 A-02 quest list erasure | `0e05bd94723f8eb137acd900b1bc03ada0ba59e2` | `a5bb55f4` | 44596602343 ✓ a1 | 44596602245 ✓ a1 |
| #532 status board | `384894d51fdef5426923cb42309d8aa907f61214` | `3947402d` | 44606027334 ✓ a1 | 44606027196 ✓ a1 |
| #534 T-01 Studio helper | `299ad96d7b3455d624ef3187535af9561b261352` | `d1104029` (= tip + exactly #534's reviewed diff) | 44694417509 ✓ a1 | 44694417510 ✓ a1 |
| #533 A-02b dict-form quests | `02782bc5151317e74aeeb9429af34addb41f7a2d` | `a0721217` (= tip + exactly #533's reviewed diff) | 44698696102 ✓ a1 | 44698696238 ✓ a1 |
| #536 status board | `58306e04adf308cb5a1e133ba54f325c56056d4c` | `4b982100` | 44705119411 ✓ a1 | 44705119347 ✓ a1 |
| #535 B-01 v3 save migration | `eda041ac228f0dd7aeae4ec4e5d6590a95941f60` | `9233a34f` (= tip + exactly #535's reviewed diff, head `4cdd233e`) | 44712018838 ✓ a1 | 44712018948 ✓ a1 |
| #528 B-01 design record | `17d88e12e12dca50293ee1646b5d02833cd48af1` | `313c28f7` (docs only) | 44717090335 ✓ a1 | 44717090260 ✓ a1 |
| #537 A-02c quest readers | `d89f32c4b0b1be502761c357b3a67ba34a4b9a39` | `4bd8d225` (= tip + exactly #537's reviewed diff) | 44720700860 ✓ a1 | 44720700937 ✓ a1 |

**Waiver (owner, one-time, narrowly scoped; not a relaxation of CI).** Post-merge CI run 44589776415 on `55bdd589`
FAILED at attempt 1: one Windows test,
`tests/test_mcp_project_ownership_root.py::test_a_nested_project_is_edited_under_its_own_ownership[apply_ops]` (the
windowless Studio helper exited 1 before answering its second command). Extended attempt 1 PASSED. Probable cause:
transient command-file access in `tests/studio_owner_process.py`. Exact exception: **unconfirmed**. The failed run and
its logs are preserved; it was not rerun and is not counted as green. Follow-up: T-01 (#534).

**Earlier failed heads, kept:** #531 `a51c9e86` (CI 44577439782 ✗, Extended 44577435395 ✗: ruff gate), `06c48cda` (CI
cancelled). #535 `5b87c527` (CI 44611731802 ✗: tier-marker ratchet on four renamed tests; Extended 44611733132 ✓),
`46454b4e` (CI 44613893043 and Extended 44613890614 cancelled, superseded), `d668097e` (CI 44614620041 ✓, Extended
44614604198 ✓; superseded by the identity fix). Only final heads passed at attempt 1.

## Work

States: `QUEUED` · `DISCOVERED` · `IN PROGRESS` · `READY FOR REVIEW` · `APPROVED` (master) · `MERGED + VERIFIED`.
Approval: `OWNER` = the owner must approve the merge.

| ID | Pri | Agent (model) | State | Branch / PR | Base → head | Evidence | Master verdict | Approval | Next action |
|---|---|---|---|---|---|---|---|---|---|
| B-01 save identity migration (v3) | P1 | mesh-gameplay-reliability (Sonnet) | MERGED + VERIFIED | #535 → `eda041ac` | `0e05bd94` → `4cdd233e` | see #535 (three review rounds, owner identity challenge resolved) | APPROVED | owner approved (slot-load identity warnings non-fatal; records never guessed, lost or discarded) | |
| A-02b dict-form quests without `"id"` | P2 | mesh-creator-safety (Sonnet) | MERGED + VERIFIED | #533 → `02782bc5` | `0e05bd94` → `ea139378` | see #533 | APPROVED | owner approved | |
| T-01 Studio helper command-file flake | test infra | mesh-creator-safety (Sonnet) | MERGED + VERIFIED | #534 → `299ad96d` | `0e05bd94` → `18298d33` | see #534 (the waived failure's cause stays unconfirmed) | APPROVED | owner approved | |
| B-01 design | | | MERGED | #528 → `17d88e12` | → `bce4f95f` | matches the implementation (WARN in slot loads, absent-entity records carried, backups `slot1.json.v2.bak`) | | owner approved | |
| A-02c other quests.json readers | P2 | mesh-creator-safety (Sonnet) | MERGED + VERIFIED | #537 → `d89f32c4` | `02782bc5` → `00fb0fce` | five readers fixed via a shared `quest_entries`; the editor refuses to save over a dict-form file | APPROVED | owner approved | |
| B-02 primary tag after load | P1/P2 | mesh-gameplay-reliability (Sonnet) | APPROVED | `fix/b02-primary-tag` / #538 (draft) | `eda041ac` → `655dfc0b` | real cycle on base: player came back as "friendly", guard as "alpha"; head keeps both; new optional `primary_tag` (no schema bump); old records keep the live primary when saved, else `tags[0]` + WARN `primary_tag_guessed`; 8 tests (7 fail on base), 5/5 faults; digests unchanged; CI 44720168671 ✓ a1, Extended 44720166357 ✓ a1 | **APPROVE** | OWNER (saved-record field) | owner merge decision |
| U-01 unresolved-record accumulation | P2 | (unassigned) | QUEUED (owner: separate, measurable) | | | B-01: expired projectile records and indistinguishable twins' records accumulate in `saved_entities.unresolved` (deduplicated); never discarded automatically | | owner | measure growth per save/load cycle on real games; propose a bound that discards nothing automatically |

## Follow-ups noted by reviews (not assigned)

- **F1 (A-00, P2):** an `OSError` while `finish_backup` fingerprints a file leaves the plan written with no manifest
  (undo then refuses, safely) and, on the error path, replaces the plan's own error.
- **F2 (A-00, informational):** `_unverified` accepts `{"exists": 0}` as absent; require `record["exists"] is False`.
- **A-01, low:** no test fails without the link check on Python 3.13; Windows reserved names aren't refused.
- **#524 review, low:** `engine/json_io.write_text_atomic` writes `<target>.tmp` unchecked; exclusive temporary file.
- **B-01b, informational:** twins pair by order (positional if the room file was reordered since the save).
- **B-01, informational:** expired projectile records accumulate in `saved_entities.unresolved` (deduplicated) until
  they bind or are edited out; four tests in `test_save_entity_quest_state.py` keep their v2 names while asserting v3.
- **Process:** workers run the gates (and the tier-marker ratchet) on the exact commit they push.

## Task log (models and usage, as reported by the Agent tool)

| Task | Model | Tool calls | Tokens | Output |
|---|---|---|---|---|
| cycles 1-2 | Sonnet 5.5, Haiku 5.5 | 262 | ~1.09M | #529, #530, #531, #528, verdicts |
| A-02b | Sonnet 5.5 | 19 | ~95k | #533 |
| T-01 | Sonnet 5.5 | 28 | ~94k | #534 |
| B-01 round 1 | Sonnet 5.5 | 144 | ~341k | #535 `5b87c527` |
| B-01 round 2 (same agent, resumed) | Sonnet 5.5 | 160 | ~357k | #535 `d668097e` |
| B-01 round 3, identity challenge (resumed) | Sonnet 5.5 | 17 | ~384k | #535 `4cdd233e` |
| A-02c | Sonnet 5.5 | 32 | ~112k | #537 (merged) |
| B-02 | Sonnet 5.5 | 36 | ~108k | #538 |

## Worktrees in use

| Worktree | Holds |
|---|---|
| `D:\Games\Mesh-B-02` | #538 (B-02) |
| `D:\Games\Mesh-board` | this board update |
| `D:\Games\Mesh-B-01-impl`, `D:\Games\Mesh-B-01`, `D:\Games\Mesh-A-02c`, `D:\Games\Mesh-A-02b`, `D:\Games\Mesh-T-01`, `D:\Games\Mesh-A-02`, `D:\Games\Mesh-B-01b` | merged work (#535, #528, #537, #533, #534, #530, #531): removable after verification |
