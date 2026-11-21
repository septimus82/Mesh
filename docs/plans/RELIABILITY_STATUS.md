# Mesh reliability: status board

Maintained by the master only (workers report in their PRs). GitHub is the source of truth: a fresh master session
rechecks every row (`RELIABILITY_COORDINATION.md` §5) before acting. IDs and priorities: `MESH_RELIABILITY_MASTER_PLAN.md`.

**As of 2026-11-21 (cycle 9).** Integration `redesign/visual-editor` = `9341bfdd08bebb5318961acab190a5c322a5dee5`
(post-merge CI 44876963282 ✓ a1, Extended 44876963293 ✓ a1). This board lands with its own PR (`gh pr list --head docs/reliability-board-cycle9`).

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
| #539 status board | `eb9e03b71912ee6be15a2289849daed473f7b8e6` | `9f59c51b` | 44726823616 ✓ a1 | 44726823629 ✓ a1 |
| #538 B-02 primary tag | `551ba25ffca2684011351f12c1383fa7688adf05` | `b8a15e9f` (= tip + exactly #538's reviewed diff) | 44730232987 ✓ a1 | 44730233136 ✓ a1 |
| #540 GAME-1 acceptance | `446236a6ac26c88ae784e02c78dbd6422bfca679` | `2e1fa844` (= reviewed head) | 44746454898 ✓ a1 | 44746454540 ✓ a1 |
| #541 B-09 removed runtime entities | `d525eea3d49b865d89af06bd0654962fc11da80b` | `f99d158d` (= tip + exactly #541's reviewed diff, head `90378a9d`) | 44754391666 ✓ a1 | 44754391627 ✓ a1 |
| #542 status board | `36d60f1d00710a50e144174823d111fc40c82119` | `8d2173f9` | 44763294564 ✓ a1 | 44763294786 ✓ a1 |
| #544 A-03 read-only ops never edits | `d3f451a479aff5ae41157984fa1d67a65f04aff6` | `d9f66b64` (= tip + exactly #544's reviewed diff, head `9a4c5f75`) | 44811646730 ✓ a1 | 44811646841 ✓ a1 |
| #543 B-05 behaviour teardown | `68ad13b0486f175f61fd2d8b26895b2c3eeaeaee` | `1a9d6cf7` (= tip + exactly #543's reviewed diff, head `19db914b`) | 44816833213 ✓ a1 | 44816833218 ✓ a1 |
| #545 status board | `0791b04d45dff6e9951d2123c9220db9cf44d261` | `1ac31173` (= head `3ee634d8`) | 44825716598 ✓ a1 | 44825716831 ✓ a1 |
| #547 A-04 CLI writers own the project | `4ae467c5f7282d3664fe27efa711580ab0b3acbf` | `bca38154` (= tip + exactly #547's reviewed diff, head `2df87f6f`) | 44832791487 ✓ a1 | 44832791497 ✓ a1 |
| #546 A-05 `paint_tiles` bounds | `4512aec8e9fb444b049606820ba806eafe0bc096` | `2542f4f6` (= tip + exactly #546's reviewed diff, head `b750bbbf`) | 44836606461 ✓ a1 | 44836606490 ✓ a1 |
| #548 status board | `11c5809fc8179aa457f574491ab3196f2c6676f2` | `2e5b4b20` (= tip + exactly #548's diff) | 44845816189 ✓ a1 | 44845816188 ✓ a1 |
| #550 B-05b every removal path ends behaviours | `052cf097e93387e0237e82e89e88d174db90aa4a` | `9e11d779` (= tip + exactly #550's reviewed diff, head `6d911e31`) | 44874121077 ✓ a1 | 44874121078 ✓ a1 |
| #551 T-02 bridge retry tests: normal deadline for the retry | `9341bfdd08bebb5318961acab190a5c322a5dee5` | `07fcb01d` (= tip + exactly #551's reviewed diff, head `c803ede9`) | 44876963282 ✓ a1 | 44876963293 ✓ a1 |

**Waiver (owner, one-time, narrowly scoped; not a relaxation of CI).** Post-merge CI run 44589776415 on `55bdd589`
FAILED at attempt 1: one Windows test,
`tests/test_mcp_project_ownership_root.py::test_a_nested_project_is_edited_under_its_own_ownership[apply_ops]` (the
windowless Studio helper exited 1 before answering its second command). Extended attempt 1 PASSED. Probable cause:
transient command-file access in `tests/studio_owner_process.py`. Exact exception: **unconfirmed**. The failed run and
its logs are preserved; it was not rerun and is not counted as green. Follow-up: T-01 (#534).

**Earlier failed heads, kept:** #531 `a51c9e86` (CI 44577439782 ✗, Extended 44577435395 ✗: ruff gate), `06c48cda` (CI
cancelled). #535 `5b87c527` (CI 44611731802 ✗: tier-marker ratchet on four renamed tests; Extended 44611733132 ✓),
`46454b4e` (CI 44613893043 and Extended 44613890614 cancelled, superseded), `d668097e` (CI 44614620041 ✓, Extended
44614604198 ✓; superseded by the identity fix). #544 `bd7d75d7` (CI 44762715843 ✗: the
fast-marking policy, a module named `*contract*` without fast markers; Extended 44762706497 ✓; fixed by a pure rename).
#546 `5dc2edca` and #547 `86af1526` (CI cancelled, superseded by the review corrections). #549 `cbb7fa66` (CI 44841828542 ✗ a1:
`test_live_bridge_request_states.py::test_a_proposal_that_timed_out_while_queued_never_reaches_the_person`, unrelated to B-06: the
retry kept the 0.2 s deadline; not rerun, owner chose a fix over a waiver → T-02 #551; Extended 44841862606 ✓ a1).
Only final heads passed at attempt 1.

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
| B-02 primary tag after load | P1/P2 | mesh-gameplay-reliability (Sonnet) | MERGED + VERIFIED | #538 → `551ba25f` | `eda041ac` → `655dfc0b` | see #538 | APPROVED | owner approved | |
| GAME-1 persistence acceptance | P1 | mesh-gameplay-reliability (Sonnet) | MERGED + VERIFIED | #540 → `446236a6` | `551ba25f` → `7f73502a` | fresh-process save/exit/load: health, quests, inventory, entity state, primary tags, v2 fixtures (`.v2.bak` byte-identical), ambiguous ids; 10 GPU cases | APPROVED | owner approved | found F-1 (→ B-09) |
| B-09 removed runtime entities resurrected (F-1) | P1/P2 | mesh-gameplay-reliability (Sonnet) | MERGED + VERIFIED | #541 → `d525eea3` | `551ba25f` → `90378a9d` | projectile measurement flat (7 entities, 191,828 B over 6 cycles) | owner challenge: order-based room/runtime pairing could drop the room-file object → fixed order-independent; APPROVED | owner approved | **Accepted limitation:** a runtime object sharing a name and prefab with an id-less room-file object is kept after it expires (warned), never at the room object's expense. **Process breach:** the worker ran `git stash` once (immediately popped; the stash list was verified intact). |
| A-03 read-only project ops applied as edits | P1 | mesh-creator-safety (Sonnet) | MERGED + VERIFIED | #544 → `d3f451a4` | `d525eea3` → `9a4c5f75` | an explicit `EDIT_OPS` allowlist (82 edits) plus `NOT_EDITS`; naming a reader is refused, files byte-identical; a guard test fails for any unclassified function | APPROVED | owner approved | |
| B-05 behaviours never unsubscribe | P2 | mesh-gameplay-reliability (Sonnet) | MERGED + VERIFIED | #543 → `68ad13b0` | `d525eea3` → `19db914b` | round 1 fixed the unsubscribe calls but nothing called teardown → round 2: `MeshEntitySprite.remove_from_sprite_lists` ends behaviours once (deaths, pickups, projectile expiry, `kill()`) | CHANGES REQUIRED → APPROVED | owner approved | follow-up B-05b below |
| A-04 legacy CLI writers bypass locks | P1 | mesh-creator-safety (Sonnet) | MERGED + VERIFIED | #547 → `4ae467c5` | `68ad13b0` → `2df87f6f` | one guard in `dispatch()` (same `project_ownership.acquire` as R4); ~40 in-place writers own the project or refuse (exit 1, files byte-identical); mutants 3/3 caught | round 1 missed `polish` and `assets import-sprites` → CHANGES REQUIRED → APPROVED | owner approved | **Limitation:** the writer list is a hand-kept table; a new in-place CLI writer must be added |
| A-05 `paint_tiles` bounds | P1/P2 | mesh-creator-safety (Sonnet) | MERGED + VERIFIED | #546 → `4512aec8` | `68ad13b0` → `b750bbbf` | whole batch validated before any write: non-negative ints inside the map (1024 cap when dimensions unknown), ≤10,000 ops, layer a non-empty string, ≤8 new layers per batch; mutants 4/4 caught | round 1 left growth through `layer` → CHANGES REQUIRED → APPROVED | owner approved | `"3"`/`3.0` now refused (intended) |
| ACC-2 creator-workflow acceptance rerun | P1 | master | **INCOMPLETE (test-side), no product defect found** | evidence `D:\Games\Mesh-462-acceptance\rerun-2026-11-21` (`run1`-`run3`) | runs 1-2 `4512aec8`, run 3 `052cf097` (detached worktree `D:\Games\Mesh-acc`) | same 33-step scenario and criteria as the 2026-11-06 PASS at `59f171b5`. Run 1: **A4 FAIL** (bare `base_revision`, retired by R1 #518) → owner-approved adaptation (14 lines). Run 2: 24/24 then **C1 FAIL** (C1 wanted an empty `.mesh/`; R2 #517 keeps `.mesh/owner.lock` by design). Owner approved the C1 correction (session record gone, OS lock free, another process acquires and releases, `owner.lock` may stay; `c1-adaptation.diff`). Run 3: **32/33, C1 PASS, F1 FAIL**: F1 flags every hidden file and found exactly `.mesh/owner.lock` (same R2 cause); F1's later checks (orphan maps, project as last saved) did not run. Not rerun. Master's miss: the other hidden-file check should have been found before run 3 | | owner | decide: let F1 allow exactly `.mesh/owner.lock` and run once more from the start |
| B-05b other entity removal paths | P2 | mesh-gameplay-reliability (Sonnet) | MERGED + VERIFIED | #550 → `052cf097` | `4512aec8` → `6d911e31` | despawn op, authoring delete and editor delete now call `_end_behaviours` after removal; 6 tests; mutant (store call removed) → 2 fail | APPROVED | owner approved | |
| B-06 RNG stream seeds | P2 | mesh-gameplay-reliability (Sonnet) | READY FOR REVIEW (refreshed) | #549 | `4512aec8` → `cbb7fa66`; refreshed by merging `9341bfdd` (with T-02) → `2a1afbc0` | `sha256(f"{seed}:{name}")` replaces the salted `hash()`; subprocess test across `PYTHONHASHSEED`; first head's CI failed only on the T-02 timing test (kept above) | APPROVED (`cbb7fa66`) | owner | approve the merge once `2a1afbc0` CI + Extended pass at attempt 1 |
| T-02 bridge retry tests: short deadline kept for the retry | test infra | master (Sonnet independent review) | MERGED + VERIFIED | #551 → `9341bfdd` | `052cf097` → `c803ede9` | test-only: both "timed out, then sent again" tests set a normal 30 s deadline before the retry; cancellation assertions unchanged; no other test in the file has the flaw (review) | APPROVED (independent review) | owner approved | |
| U-01 unresolved-record accumulation | P2 | (unassigned) | MEASURED (GAME-1) | | | unresolved records bounded by deduplication (ambiguous twins plateau at 4 after 2 cycles; no-change cycles 0); the only unbounded growth was F-1, fixed by B-09; nothing discarded | | owner | keep tracked; revisit if real games show growth |

## Follow-ups noted by reviews (not assigned)

- **F1 (A-00, P2):** an `OSError` while `finish_backup` fingerprints a file leaves the plan written with no manifest
  (undo then refuses, safely) and, on the error path, replaces the plan's own error.
- **F2 (A-00, informational):** `_unverified` accepts `{"exists": 0}` as absent; require `record["exists"] is False`.
- **A-01, low:** no test fails without the link check on Python 3.13; Windows reserved names aren't refused.
- **#524 review, low:** `engine/json_io.write_text_atomic` writes `<target>.tmp` unchecked; exclusive temporary file.
- **B-01b, informational:** twins pair by order (positional if the room file was reordered since the save).
- **B-01, informational:** expired projectile records accumulate in `saved_entities.unresolved` (deduplicated) until
  they bind or are edited out; four tests in `test_save_entity_quest_state.py` keep their v2 names while asserting v3.
- **A-05, low:** the Studio-project `apply_ops` path (`engine/mcp_server/tools.py` `_studio_changes`) calls `int()` on
  paint cells and raises on non-numeric input before any write; `project_ops.paint_tiles` already ignores out-of-map cells.
- **A-04, informational:** `edit-scene` printed `Unknown action type: update_scene_settings` on a blank project (it may
  change nothing); some `new-*` commands fail on a fresh blank project for unrelated reasons.
- **ACC-2 environment:** the rerun forces `PYGLET_AUDIO=silent` (the exported game starts at full volume with fresh player
  settings); otherwise the 2026-11-06 environment.
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
| GAME-1 | Sonnet 5.5 | 61 | ~155k | #540 |
| B-09 rounds 1 + 2 (resumed) | Sonnet 5.5 | 53 | ~303k | #541 |
| A-03 rounds 1 + 2, B-05 rounds 1 + 2 | Sonnet 5.5 ×2 | (not recorded) | | #544, #543 |
| A-05 rounds 1 + 2 | Sonnet 5.5 | 39 | ~93k | #546 |
| A-04 rounds 1 + 2 | Sonnet 5.5 | 145 | ~202k | #547 |
| B-05b, B-06 | Sonnet 5.5 ×2 | (not recorded) | | #550, #549 |
| T-02 independent review | Sonnet 5.5 | 2 | ~70k | APPROVE on #551 |

## Worktrees in use

| Worktree | Holds |
|---|---|
| `D:\Games\Mesh-B-05b`, `D:\Games\Mesh-T-02` | merged work (#550, #551): removable after verification, with owner OK |
| `D:\Games\Mesh-B-06` | B-06 (#549, open) |
| `D:\Games\Mesh-acc` | ACC-2 (detached at `052cf097`) |
| `D:\Games\Mesh-board` | this board update |
| `D:\Games\Mesh-A-04`, `D:\Games\Mesh-A-05` | merged work (#547, #546): removable after verification, with owner OK |

Removed 2026-11-21 (owner-authorised; each clean, on its merged head, no unmerged commits; branches kept): `Mesh-B-02`,
`Mesh-GAME-1`, `Mesh-B-09`, `Mesh-A-03`, `Mesh-B-05`.
