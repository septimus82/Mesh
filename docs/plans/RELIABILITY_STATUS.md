# Mesh reliability: status board

Maintained by the master only (workers report in their PRs). GitHub is the source of truth: a fresh master session
rechecks every row (`RELIABILITY_COORDINATION.md` §5) before acting. IDs and priorities: `MESH_RELIABILITY_MASTER_PLAN.md`.

**As of 2026-11-22 — Ember Hollow round 1 done, its defects fixed; round 2 in progress.** Integration `redesign/visual-editor` =
`df656ef879c7309b574208883448d51e2bd24592` (post-merge CI 44962995486 ✓ a1, Extended 44962995489 ✓ a1). This board lands with its own PR
(`gh pr list --head docs/reliability-board-slice-r1`). Review phase: #569 (`8a79adcf`). Cycle 10 closed with #565 (`1bd4aad9`).

**Ember Hollow round 1** (project `D:\Games\Mesh-slice\EmberHollow`, engine `fed442a5`, built only through MCP/authoring
ops and `mesh` commands; report `D:\Games\Mesh-slice\evidence\REPORT.md`): A validate PASS; B AI playtest PARTIAL (the AI
playtest had no attack, so the quest only completed with attack keys injected in-process, and the driver was a steering
script, not a live AI — not counted as a pass); C fresh-process persistence PASS; D exported build PASS. Five defects found
and fixed below (SL-1..SL-5); six minor items recorded. Round 2 (engine `df656ef8`): content corrected (rat tags, contact
damage above defence) and B re-run with the AI deciding every action, no script, no injected keys.
**Queued after Ember Hollow (owner):** Astra audit follow-up — `mesh new --force` nested-project preflight, future-schema
slot overwrite refusal, SoundEmitter teardown, diagnostic sidecars as save slots, replay-golden investigation.

**Independent review of `e390ef6e` (2 fresh reviewers, 39 production files `ad91e28c..e390ef6e`): no blockers.**
Three SERIOUS findings, each reproduced and fixed below (RV-1..RV-3). MINOR, recorded only: `died` no longer carries an
`entity` key (no reader); the atomic-write temp name is ~24 chars longer (MAX_PATH edge); non-int paint values now refused
(intended); same-key entities can swap unsynced fields across layers (not a regression).
**Ember Hollow vertical slice (owner brief):** being built on `fed442a5` through the AI authoring / MCP path only (no JSON
edits, no engine changes); acceptance A validate, B AI playtest, C fresh-process persistence, D exported build.

**Owner decisions closing cycle 10 (final):** frame-time cap DEFERRED (not implemented); A-07 light references → refuse
(A-07b, #564, merged); cleanup of the 15 merged worktrees done. **Next phase (owner):** independent review of the verified
tip `e390ef6e` → fix genuine blockers it finds → a small playable vertical slice built with Mesh's existing tools. No new
reliability tasks or broad audits; the lanes stay idle until the review or the slice gives concrete work.

**Standing authority (owner, 2026-11-21):** the master merges focused, independently approved fixes whose exact head passed
CI + Extended and whose merge tree equals the reviewed change, and runs failure recovery, without asking. Escalation only for
destructive/incompatible data changes, new save-format migrations or major architecture, gate waivers, unresolved review
disagreement, or two failed correction rounds. Cycle 10 merges below were made under it, one at a time, each verified.

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
| #552 status board (cycle 9) | `08f2ce0f4550d0988b2792353cb9fa3916114642` | `84e431cf` (= tip + exactly #552's diff) | 44882250376 ✓ a1 | 44882250370 ✓ a1 |
| #549 B-06 stable RNG stream seeds | `8a5ce09e6dcb78c9d160b429ce00c6e1c4e6263c` | `3d18702b` (= tip + exactly the reviewed `cbb7fa66` change; head `2a1afbc0` after the T-02 refresh) | 44884740592 ✓ a1 | 44884740664 ✓ a1 |
| #553 B-07 RangedAttackAI finds the player | `f640dbd436d96126abde7a8b3af50de79532a9f8` | `0cbd4908` (head `f0d19532`) | 44887817923 ✓ a1 | 44887817940 ✓ a1 |
| #554 A-00 F1/F2 plan manifest | `23bdb0eaddb497ab182d6e8e2113b8d4a19cf292` | `af31916e` (head `a5778bf7`) | 44890518911 ✓ a1 | 44890518976 ✓ a1 |
| #555 B-04 hit particles | `5f7ea5a8e4a37a079ac4ac2f395e3f5b6f29e9c6` | `f6287854` (head `ab318ef8`) | 44892887087 ✓ a1 | 44892887096 ✓ a1 |
| #557 B-04b collect particles | `2e5e7ffb586dccfb467d23a0edd8bb0afbbaef28` | `80eab02a` (head `c7aded1d`; same changed lines, hunk offset +1 after #555) | 44895536721 ✓ a1 | 44895536574 ✓ a1 |
| #556 A-07 light `@N` references | `cbd1bf0506ba1dc40969e618ce027b9c0d04d262` | `63d2487d` (head `df4630eb`) | 44897936891 ✓ a1 | 44897936939 ✓ a1 |
| #559 B-03 one death counts once | `bab1e086bdcb3e6b80175b9b95924ac20e39ec2b` | `8cdc5891` (head `5b1703c1`) | 44900345727 ✓ a1 | 44900345739 ✓ a1 |
| #558 A-08 exclusive atomic-write temp | `3cb747f91e515197f1b9f5142108a5eab81b1949` | `132f17c2` (head `fc903887`) | 44902650038 ✓ a1 | 44902650100 ✓ a1 |
| #560 T-03 lifecycle fixture leak | `5e805371e994bd3a428ffedde284547d426f1cd5` | `7c33e1e0` (head `3b34ef3e`) | 44905181639 ✓ a1 | 44905181634 ✓ a1 |
| #561 B-08 tunneling + non-finite moves | `5e7e3b1971b77f531f6f5080403fd17e54851788` | `5778cb8d` (head `ae723541`) | 44908222390 ✓ a1 | 44908222335 ✓ a1 |
| #562 A-05b Studio paint validation | `9e501f8809d0be891a631a511e9784e70ea60e6c` | `a6903449` (head `504776ee`) | 44911286304 ✓ a1 | 44911286239 ✓ a1 |
| #563 status board (cycle 10) | `e390ef6e10e8f68aa0c0f2e25678a2d21a973da5` | `b5b2b6ef` (= tip + exactly #563's diff) | 44915720973 ✓ a1 | 44915720999 ✓ a1 |
| #564 A-07b a batch can't shift a light it added | `6366e2cc02e358321456088af8a94a109c0c31f9` | `218d6769` (head `3eb56996`) | 44922788419 ✓ a1 | 44922788400 ✓ a1 |
| #565 status board (close cycle 10) | `1bd4aad9968cd46a90fb792057f229928cea8ad2` | `bc1521bd` (= tip + exactly #565's diff) | 44929496302 ✓ a1 | 44929496316 ✓ a1 |
| #566 RV-1 carried record retried only in its own room | `dc6b0a257b2c973123ec316b63b07da932dc7752` | `2dfa155f` (head `3c6791b5`) | 44932235458 ✓ a1 | 44932235446 ✓ a1 |
| #567 RV-2 authored id-less prefab never dropped | `71e1e5aa1bd8af78eddcc7cade25b8c090ff24bb` | `c1e22105` (head `690f38aa`) | 44934927988 ✓ a1 | 44934927965 ✓ a1 |
| #568 RV-3 `mesh new --force` owns before deleting | `fed442a5c55f1ad374a8d9ec40df4b40ac529e73` | `9741bce3` (head `a1e9aabc`) | 44937909206 ✓ a1 | 44937909101 ✓ a1 |
| #569 status board (review phase) | `8a79adcf41e4759d75f1dfab302f76b687a57bef` | `734d0937` (= tip + exactly #569's diff) | 44944554010 ✓ a1 | 44944554105 ✓ a1 |
| #570 SL-4 `set_entity_fields` via authoring | `451eca7cf547109d9eb2113933ebe7c34e069bdb` | `d41efe8a` (head `93102d56`) | 44948891259 ✓ a1 | 44948891185 ✓ a1 |
| #572 SL-2 one quest event, one listener reaction | `f03476a888091712c7fda6403e3813acea30321d` | `2ef2238d` (head `29dde80e`) | 44951944521 ✓ a1 | 44951944578 ✓ a1 |
| #574 SL-5 AI playtesting can attack | `32b838b9b07a2a16b35c157689ed57a029820aba` | `0f4e603a` (head `2dbfdfb4`) | 44955048707 ✓ a1 | 44955048866 ✓ a1 |
| #571 SL-1 DamageOnTouch reduces Health | `de6b84c8f2edc05773eba7d87401551237761a17` | `43d85a82` (head `98fc904c`) | 44958263858 ✓ a1 | 44958263876 **✗ a1**, ✓ a2 (see below) |
| #573 SL-3 explicit `auto_start: false` waits | `df656ef879c7309b574208883448d51e2bd24592` | `3215333d` (head `4d25c172`) | 44962995486 ✓ a1 | 44962995489 ✓ a1 |

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
#558 `2b14a8ab` (CI cancelled, superseded by review round 2) and `76666227` (CI cancelled, superseded). #560 `2f5a334b` (CI
cancelled, superseded by review round 2). #564 `7dedd034` (CI cancelled, superseded by review round 2). #571 `71ee20ca` (CI 44944215643 ✗ a1: mypy gate, the `SceneController` stub lacked the new `emit` keyword; fixed in round 2;
its Extended cancelled, superseded). #573 `ac708341` (CI 44944711054 ✗ a1: tier-marker ratchet, new tests unmarked; fixed in
round 2; its Extended 44944823086 ✓, superseded). Only final heads passed at attempt 1.

**Post-merge Extended 44958263876 on `de6b84c8` (#571) FAILED at attempt 1** — one Windows gpu test,
`tests/test_mesh_net_gpu.py::test_two_characters_persist_through_a_server_restart` (15 s `_state` wait "sigil taken" timed
out). Evidence it is environmental, not #571: `mesh_net` / `tooling.net_world_probe` never use DamageOnTouch or `on_damage`
(SL-1's only code paths); #571's own PR-head Extended 44947199016 passed the gpu lane; the exact test passed 3/3 locally at
`de6b84c8` (42.5 s, 37.0 s, 37.0 s). One `--failed` rerun → attempt 2 ✓. Attempt 1 is not counted as green. Follow-up T-04.

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
| ACC-2 creator-workflow acceptance rerun | P1 | master | **PASSED (33/33)** | evidence `D:\Games\Mesh-462-acceptance\rerun-2026-11-21` (`run1`-`run4`) | run 4 at `9341bfdd` | same 33-step scenario and criteria as the 2026-11-06 PASS at `59f171b5`. Runs 1-3 stopped on test-side issues only (A4 bare `base_revision` retired by R1; C1 and then F1 expecting no `.mesh/owner.lock`, which R2 keeps). Three recorded harness adaptations (`harness-adaptation.diff`, `c1-adaptation.diff`, `f1-adaptation.diff`; C1 owner-approved, F1 the same rule under the standing authority). Run 4: **33/33 PASS**, C1 proves the lock free from another process. No product defect | APPROVED | | |
| B-05b other entity removal paths | P2 | mesh-gameplay-reliability (Sonnet) | MERGED + VERIFIED | #550 → `052cf097` | `4512aec8` → `6d911e31` | despawn op, authoring delete and editor delete now call `_end_behaviours` after removal; 6 tests; mutant (store call removed) → 2 fail | APPROVED | owner approved | |
| B-06 RNG stream seeds | P2 | mesh-gameplay-reliability (Sonnet) | MERGED + VERIFIED | #549 → `8a5ce09e` | `4512aec8` → `cbb7fa66`, refreshed `2a1afbc0` | `sha256(f"{seed}:{name}")` replaces the salted `hash()`; first head's CI failed only on the T-02 timing test (kept above); refreshed head green a1 | APPROVED | owner approved T-02 route | |
| T-02 bridge retry tests: short deadline kept for the retry | test infra | master (Sonnet independent review) | MERGED + VERIFIED | #551 → `9341bfdd` | `052cf097` → `c803ede9` | test-only: both "timed out, then sent again" tests set a normal 30 s deadline before the retry; cancellation assertions unchanged; no other test in the file has the flaw (review) | APPROVED (independent review) | owner approved | |
| B-07 RangedAttackAI player lookup | P2 | gameplay (Sonnet) | MERGED + VERIFIED | #553 → `f640dbd4` | `9341bfdd` → `f0d19532` | confirmed: `GameWindow` has no `current_scene`, archer never fired; now `scene_controller._find_player_sprite()`; GPU test ran on Linux + Windows; mutant fails | APPROVED | master (standing authority) | |
| A-00 F1/F2 plan manifest | P2 | creator-safety (Sonnet) | MERGED + VERIFIED | #554 → `23bdb0ea` | `9341bfdd` → `a5778bf7` | a stopped plan's own error is never masked by a manifest-write failure (undo refuses the manifest-less backup); `{"exists": 0}` no longer passes as absent; mutant fails | APPROVED | master (standing authority) | |
| B-04 hit particles | P2 | gameplay (Sonnet) | MERGED + VERIFIED | #555 → `5f7ea5a8` | `08f2ce0f` → `ab318ef8` | confirmed: handler read `.center_x` off the target's name string (bus swallowed the error); resolves by `find_sprite_by_name`; contract unchanged | APPROVED | master (standing authority) | |
| B-04b collect particles | P2 | gameplay (Sonnet) | MERGED + VERIFIED | #557 → `2e5e7ffb` | `08f2ce0f` → `c7aded1d` | confirmed: handler read a `collectible` key never sent; uses the payload's `position` | APPROVED | master (standing authority) | |
| A-07 MCP route / light references | P2 | creator-safety (Sonnet) | MERGED + VERIFIED | #556 → `cbd1bf05` | `08f2ce0f` → `df4630eb` | stale route REFUTED (ownership taken before writing; existing two-process tests); light index CONFIRMED: settings of a second added light landed on the first; now `@<change>` | APPROVED | master (standing authority) | |
| B-03 death counted twice | P2 | gameplay (Sonnet) | MERGED + VERIFIED | #559 → `bab1e086` | `08f2ce0f` → `5b1703c1` | reproduced: a live window has no separate gameplay bus, so Health's two `died` emits reached the same subscribers (cellar quest counted 2 per kill); one `died` per bus now | APPROVED | master (standing authority) | |
| A-08 atomic-write temp file | low | creator-safety (Sonnet) | MERGED + VERIFIED | #558 → `3cb747f9` | `08f2ce0f` → `fc903887` | exclusive unique temp (`"x"`), mode kept; round 1 left six leftover-temp asserts vacuous → round 2 fixed and proved they bite | APPROVED | master (standing authority) | |
| T-03 lifecycle fixture leak | test infra | gameplay (Sonnet) | MERGED + VERIFIED | #560 → `5e805371` | `08f2ce0f` → `3b34ef3e` | module fixture left `MESH_REPO_ROOT` pinned to a dead project (local `MESH_GL_SMOKE` runs only); round 2 restores a preset value | APPROVED | master (standing authority) | |
| B-08 tunneling and non-finite moves | P2 | gameplay (Sonnet) | MERGED + VERIFIED | #561 → `5e7e3b19` | `8a5ce09e` → `ae723541` | confirmed both movers skip thin walls on fast/hitched moves; half-size substeps (cap 256) and a non-finite guard; small moves unchanged; per-mechanism mutants fail | APPROVED | master (standing authority) | |
| A-05b Studio paint validation | low | creator-safety (Sonnet) | MERGED + VERIFIED | #562 → `9e501f88` | `cbd1bf05` → `504776ee` | shared `validate_paint_ops`; the Studio path refuses what the direct path refuses (missing layer no longer becomes `"None"`) | APPROVED | master (standing authority) | |
| A-07b light `@N` shift (owner decision) | P2 | creator-safety (Sonnet) | MERGED + VERIFIED | #564 → `6366e2cc` | `e390ef6e` → `3eb56996` | in one batch a `remove_light` at or below a light that batch added is refused (whole batch, files unchanged), via `authoring.apply` and MCP; mutant fails. Round 2 added a non-int index guard; my round-1 concern proved unfounded (already converted to `ChangeError`) | APPROVED | master (standing authority) | |
| RV-1 carried unresolved record bound in another room | SERIOUS | gameplay (Sonnet) | MERGED + VERIFIED | #566 → `dc6b0a25` | `6366e2cc` → `3c6791b5` | review repro: room A's carried record bound to a same-id entity added to room B and was dropped from `unresolved`; retry now only in the entry's own room (`_same_room`); mutant fails | APPROVED | master (standing authority) | |
| RV-2 authored id-less prefab entity dropped from save | SERIOUS | gameplay (Sonnet) | MERGED + VERIFIED | #567 → `71e1e5aa` | `6366e2cc` → `690f38aa` | review repro: raw-room key `(None, prefab)` vs resolved `(Name, prefab)` made authored prefab objects look save-only; one shared key (`prefab_id`); B-09's runtime-entity drop kept; mutant fails | APPROVED | master (standing authority) | |
| RV-3 `mesh new --force` deleted an owned project | SERIOUS | creator-safety (Sonnet) | MERGED + VERIFIED | #568 → `fed442a5` | `6366e2cc` → `a1e9aabc` | pre-existing, missed by A-04: rmtree without ownership; now owns first (refuses if Studio/another process owns), deletes all but the lock, releases, removes the rest; real two-process test; mutant fails | APPROVED | master (standing authority) | |
| SL-1 DamageOnTouch never reduced Health | engine (slice) | gameplay (Sonnet) | MERGED + VERIFIED | #571 → `de6b84c8` | `fed442a5` → `98fc904c` | DamageOnTouch only emitted `damage_applied`; now applies through `Health.apply_damage` (Hitbox/Projectile pattern), one event per hit, `on_damage(..., emit=False)` keeps anim/log; round 1 failed the mypy gate (stub) | APPROVED (round 2) | master (standing authority) | |
| SL-2 SetGameStateOnEvent reacted twice | engine (slice) | gameplay (Sonnet) | MERGED + VERIFIED | #572 → `f03476a8` | `fed442a5` → `29dde80e` | bus subscription AND per-frame delivery both handed it each event (counters doubled); bus only now | APPROVED | master (standing authority) | |
| SL-3 quest `auto_start: false` ignored | engine (slice) | gameplay (Sonnet) | MERGED + VERIFIED | #573 → `df656ef8` | `fed442a5` → `4d25c172` | 26 shipped quests omit `auto_start` and rely on the implicit start → worker escalated; master chose the compatible option: tri-state, only explicit `false` waits (absent unchanged), docs updated; round 1 failed the tier-marker ratchet | APPROVED (round 2) | master (standing authority) | |
| SL-4 `set_entity_fields` unusable via authoring | authoring (slice) | creator-safety (Sonnet) | MERGED + VERIFIED | #570 → `451eca7c` | `fed442a5` → `93102d56` | the only `**kwargs` op was bound as one `fields` param; `_bind` now spreads an object; op guards unchanged | APPROVED | master (standing authority) | |
| SL-5 AI playtesting had no attack | AI-playtest tool (slice) | creator-safety (Sonnet) | MERGED + VERIFIED | #574 → `32b838b9` | `fed442a5` → `2dbfdfb4` | `attack` taps the game's own binding via the same driver and permission as `interact`; refused in dialogue | APPROVED | master (standing authority) | |
| U-01 unresolved-record accumulation | P2 | (unassigned) | MEASURED (GAME-1) | | | unresolved records bounded by deduplication (ambiguous twins plateau at 4 after 2 cycles; no-change cycles 0); the only unbounded growth was F-1, fixed by B-09; nothing discarded | | owner | keep tracked; revisit if real games show growth |

## Follow-ups noted by reviews (not assigned)

- **A-01, low:** no test fails without the link check on Python 3.13; Windows reserved names aren't refused.
- **B-01b, informational:** twins pair by order (positional if the room file was reordered since the save).
- **B-01, informational:** expired projectile records accumulate in `saved_entities.unresolved` (deduplicated) until
  they bind or are edited out; four tests in `test_save_entity_quest_state.py` keep their v2 names while asserting v3.
- **A-04, informational:** `edit-scene` printed `Unknown action type: update_scene_settings` on a blank project (it may
  change nothing); some `new-*` commands fail on a fresh blank project for unrelated reasons.
- **ACC-2 environment:** the rerun forces `PYGLET_AUDIO=silent` (the exported game starts at full volume with fresh player
  settings); otherwise the 2026-11-06 environment.
- **B-08, policy (owner: DEFERRED):** `on_update` passes `delta_time` uncapped; a cap would change game time for every timer. Moves past
  256 half-size pieces in one frame can still tunnel. NaN `x`/`y` in hand-written scene JSON is accepted by `float()`.
- **B-07, low:** `RangedAttackAI.last_attack_time` uses `time.time()` and is never reset on a scene change.
- **T-03, low:** conftest's function-scoped launch-root undo can't see a module-scoped fixture's pin.
- **A-05b, informational:** an `apply_ops` refusal response has no `authoring` key.
- **CI evidence gap:** the Ubuntu `pytest` job writes no junit, so per-test results there can't be shown (A-08's POSIX-only tests).
- **RV-3 follow-up, low:** `mesh_cli/new_game.py` has its own `--force` file-overwrite path, not checked for ownership.
- **T-04, test reliability:** `test_mesh_net_gpu.py::test_two_characters_persist_through_a_server_restart`'s 15 s "sigil taken"
  wait timed out once on Windows CI (post-merge 44958263876 a1); track, don't weaken.
- **Ember Hollow minor findings (round 1):** no quest op in authoring ops and `add_quest_definition` fails without
  `quests.json`; `apply-plan --ai-safe` error names `plan.meta.touches` (reads `inputs.meta.touches`); validator false
  alarms (Cellar "unreachable", `ai-audit` transitions/tags/quest triggers); MCP `validate_scene` without a path skips;
  change summary calls an event listener "zone entered"; `mesh new-quest --target` treated as a file path (code reading).
  Friction: no op renames a room or sets the start room; `add_room` is 2D only; AI playtest `nearby` has no HP.
- **RV-1 note:** a carried entry without a `scene_path` (none are written today) would still retry in any room.
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
| A-00 F1/F2 | Sonnet 5.5 | 16 | ~85k | #554 |
| B-07 | Sonnet 5.5 | 16 | ~88k | #553 |
| B-04, B-04b (resumed) | Sonnet 5.5 | 20 | ~93k | #555, #557 |
| A-07 | Sonnet 5.5 | 20 | ~102k | #556 |
| A-08 rounds 1 + 2 | Sonnet 5.5 | 34 | ~101k | #558 |
| B-03, T-03 rounds 1 + 2 (resumed) | Sonnet 5.5 | 16 | ~128k | #559, #560 |
| B-08 | Sonnet 5.5 | 32 | ~111k | #561 |
| A-05b | Sonnet 5.5 | 10 | ~82k | #562 |
| A-07b rounds 1 + 2 (resumed) | Sonnet 5.5 | 38 | ~89k | #564 |
| Independent review, save/persistence | Opus 5.5 | 53 | ~190k | 2 SERIOUS, 1 MINOR |
| Independent review, creator + gameplay | Opus 5.5 | 58 | ~168k | no blockers, 1 SERIOUS (pre-existing), 3 MINOR |
| RV-1 | Sonnet 5.5 | 17 | ~91k | #566 |
| RV-2 | Sonnet 5.5 | 15 | ~89k | #567 |
| RV-3 | Sonnet 5.5 | 64 | ~111k | #568 |
| Ember Hollow round 1 (creator) | Opus 5.5 | 166 | ~375k | project, export, evidence, 11 findings |
| SL-1 rounds 1 + 2 | Sonnet 5.5 | 20 | ~92k | #571 |
| SL-2 | Sonnet 5.5 | 30 | ~106k | #572 |
| SL-3 (escalation, option 1, round 2) | Sonnet 5.5 | 23 | ~108k | #573 |
| SL-4 | Sonnet 5.5 | 18 | ~85k | #570 |
| SL-5 | Sonnet 5.5 | 32 | ~110k | #574 |

## Worktrees in use

| Worktree | Holds |
|---|---|
| `D:\Games\Mesh-A-07b`, `D:\Games\Mesh-RV1`, `D:\Games\Mesh-RV2`, `D:\Games\Mesh-RV3` | merged work (#564, #566-#568): removable after verification, with owner OK |
| `D:\Games\Mesh-review` | the review's detached checkout at `e390ef6e` |
| `D:\Games\Mesh-slice-engine`, `D:\Games\Mesh-slice-engine2` | Ember Hollow's pinned engine checkouts: round 1 at `fed442a5`, round 2 at `df656ef8` (read-only) |
| `D:\Games\Mesh-SL1`, `D:\Games\Mesh-SL2`, `D:\Games\Mesh-SL3`, `D:\Games\Mesh-SL4`, `D:\Games\Mesh-SL5` | merged work (#570-#574): removable after verification, with owner OK |
| `D:\Games\Mesh-acc` | ACC-2 (detached at `9341bfdd`) |
| `D:\Games\Mesh-board` | this board update |

Removed 2026-11-21 (owner-authorised; each clean, on its merged head, no unmerged commits; branches kept): `Mesh-B-02`,
`Mesh-GAME-1`, `Mesh-B-09`, `Mesh-A-03`, `Mesh-B-05`. Removed 2026-11-21 (owner-approved; same checks: clean, fully merged into
`e390ef6e`, no unique commits, no active worker; branches kept): `Mesh-A-04`, `Mesh-A-05`, `Mesh-B-05b`, `Mesh-T-02`, `Mesh-B-06`,
`Mesh-B-07`, `Mesh-A-F12`, `Mesh-B-04`, `Mesh-B-04b`, `Mesh-A-07`, `Mesh-B-03`, `Mesh-A-08`, `Mesh-T-03`, `Mesh-B-08`, `Mesh-A-05b`.
