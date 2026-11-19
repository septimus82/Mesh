# Mesh Reliability Program — Master Plan & Multi-Agent Runbook

**Repository:** `septimus82/Mesh` · **Primary development branch:** `redesign/visual-editor`  
**Document created:** 2026-11-19 · **Status:** proposed operating plan, not an activated automation  
**Maintainer:** Master coordinator (human owner retains control of destructive/release decisions)

> **Purpose:** Make Mesh dependable as a game-creation and gameplay platform, especially against silent loss or corruption of creator projects and player saves. Continue game development once these core contracts are demonstrably safe. This file is a portable operating manual for new chats and agents, not a claim that any agent is already running unattended.

## 1. Source of truth and current checkpoint

At the beginning of **every** session or automated cycle, refresh `redesign/visual-editor`, open PRs, issues, and CI/Extended runs directly from GitHub. Never treat the snapshot below as current without checking. Chat history, agent memory and this document are secondary to actual commits and test evidence.

**Snapshot verified 2026-11-19:**

| Item | Verified condition | Link / ref |
|---|---|---|
| Integration | `ad91e28c665ae6adc22be4ce0b2c4e7d26e1817b` | `redesign/visual-editor` |
| R4 AI write ownership | merged | [PR #521](https://github.com/septimus82/Mesh/pull/521) |
| R5 MCP ownership | merged | [PR #522](https://github.com/septimus82/Mesh/pull/522) |
| Studio Ctrl+S nested-project protection | merged | [PR #523](https://github.com/septimus82/Mesh/pull/523) |
| Studio tileset import ownership | merged | [PR #524](https://github.com/septimus82/Mesh/pull/524) |
| Stale-content AI plan undo | draft PR at `5fd408d612ef7166a622e68e2dcd74349d0936d5`; CI 44517832117 and Extended 44517840518 passed at attempt 1; independent review **APPROVED** (non-blocking follow-ups F1/F2 tracked separately); merge awaits owner approval | [PR #525](https://github.com/septimus82/Mesh/pull/525) |
| Creator-integrity tracking | open | [Issue #462](https://github.com/septimus82/Mesh/issues/462) |
| Repository health | open | [Issue #422](https://github.com/septimus82/Mesh/issues/422) |
| Release golden digests | open | [Issue #359](https://github.com/septimus82/Mesh/issues/359) |
| Installed CLI gaps | open | [Issue #357](https://github.com/septimus82/Mesh/issues/357) |
| Main redesign integration | draft, do **not** merge casually into `main` | [PR #344](https://github.com/septimus82/Mesh/pull/344) |

**Never update the status of PR #525 to merged merely because its tests are green.** Inspect its review, head SHA, production changes, and final merge result first. The original `D:\Games\Mesh` checkout has been intentionally left untouched; agents must use isolated worktrees.

### Vocabulary for evidence

- `CLAIM`: an external audit made the claim; its production-path reachability is unverified.
- `SOURCE-CONFIRMED`: the current source contains the hazardous mechanism; an independent controlled runtime reproduction may still be needed.
- `REPRODUCED`: a disposable project or game demonstrates the defect against the real entry point.
- `IN PROGRESS`: a named branch/PR and worker own the task.
- `READY FOR REVIEW`: implementation and tests submitted; **not** authorization to merge.
- `APPROVED`: reviewer checked scope, evidence, regression tests and CI.
- `MERGED + VERIFIED`: intended merge tree and post-merge gates checked; only then close.

Use **separate fields** for severity, evidence level, and workflow state. An audit allegation is not automatically a confirmed P0/P1.

## 2. Non-negotiable reliability contracts

1. **Creator project safety:** an operation cannot destroy unrelated paths; it may only write destinations owned by its valid project lock. A refusal must preserve files and dirty Studio edits.
2. **Undo correctness:** a stale/partial/legacy backup never silently overwrites later creator edits. A conflict in any destination refuses the entire undo before writing.
3. **Persistence correctness:** each distinct runtime entity retains its own saved state; its primary tag and behavior state round-trip; save → close → reload produces the intended game state.
4. **Operation safety:** read-only operations cannot be registered as edits; malformed or extreme AI/CLI inputs cannot cause unbounded allocations or schema replacement.
5. **Gameplay correctness:** each logical kill and hit has the intended observable effects exactly once; event subscriptions are properly released; seeded simulations behave deterministically where promised.
6. **Release honesty:** required checks fail when inputs are missing, rather than reporting green while checking zero cases. Installed-wheel paths are tested separately from source-checkout paths.
7. **Test evidence:** every meaningful fix includes a pre-fix reproduction, an after-fix pass, and a regression test through the production entry point. CI green alone is insufficient.
8. **Bounded changes:** one issue per PR when practical, no opportunistic refactors, and no unreviewed changes to approved commits.

## 3. Two implementation agents and one master

```text
                     OWNER / MASTER COORDINATOR
               (GitHub issues + this runbook)
                       /            \
             issue + acceptance  issue + acceptance
                    /                  \
        AGENT A — Creator Safety   AGENT B — Gameplay Reliability
        isolated worktree A       isolated worktree B
                    \                  /
              PR + evidence       PR + evidence
                       \            /
                       MASTER REVIEW
                  tests, diff, CI, contracts
                          |
                approve or return precise fixes
                          |
               sequential merge + post-merge CI
                          |
               issue/status updated; next tasks
```

**Master coordinator:** Owns assignment, conflict checks, review, merge ordering, required CI/Extended, issue comments, and authoritative status updates. Does **not** equate an agent's self-reported `READY` with approval. Reviews the exact PR head and associated code; explicitly requests corrections in the same PR when necessary. Normally does not write production code while reviewing. Master can be a fresh ChatGPT session using the GitHub connector; no dependency on a particular conversation's context.

**Agent A — Creator safety:** CLI scaffolding and destructive `--force` operations; quest/content edits; authoring operation registry; old CLI writers and OS locks; tile bounds; creator save/undo surfaces. **No edits** to runtime save state, entity simulation, combat or event buses without reassignment.

**Agent B — Game runtime:** Save/runtime entity identity and tags; event/death/hit behavior, subscription teardown, deterministic RNG, ranged AI and gameplay smoke tests. **No edits** to authoring, CLI scaffolding or Studio save code without reassignment.

**Concurrency:** at most **one active production PR per worker** and **two active production PRs total**. A worker never commits to the integration branch. Do not schedule jobs that touch overlapping files, tests or shared data contracts concurrently. Check changed-file lists before dispatch. If overlap is discovered, pause the later PR, integrate the first, rebase and rerun regression gates, then continue. Master merges **sequentially**, not in parallel.

### Merge authority (safe initial mode)

- Workers **cannot** merge or force-push the integration branch.
- Master may propose, review, request a correction and approve a PR after evidence is verified.
- For **P0/P1, destructive operations, save-format migrations, branch deletion, releases or changes to `main`**, obtain explicit owner approval for the merge/action; do not configure unattended auto-merge by default.
- For bounded P2 fixes, master may be delegated merge authority later, **only after** the user deliberately enables that policy and with all gates still required.
- Master must stop if base SHA moved unexpectedly, trees differ, a required check fails, the PR has unreviewed changes, or any collision is found.

This supports a hands-off **review and correction loop**, while keeping the highest-risk mutations under human control. Full automatic dispatch and merge require an actual runner/agent integration and credentials; **this Markdown file alone does not launch background workers**.

## 4. Prioritized defect queue

The labels here reflect inspection of `redesign/visual-editor` on 2026-11-19. Validate on the newest SHA before starting. If an existing issue or PR already covers a task, link it rather than duplicating work.

### Lane A — Creator safety and data loss

| ID | Priority / evidence | Task and minimal acceptance criteria | State / dependencies |
|---|---|---|---|
| `A-00` | P1 / reproduced before fix | **Stale-content plan undo**: post-plan hashes; whole-manifest refusal on any later edit; safe legacy handling; repeated undo protection. | **PR #525 draft, ready for independent review claim; do not start a second implementation.** Review first. |
| `A-01` | **P0 candidate** / source-confirmed | **`mesh new --force` arbitrary deletion** in `mesh_cli/blank_project.py`: validate name and target **before** any delete; refuse `..`, absolute paths, separators, symlink/junction escapes and non-project existing folders; destructive negative tests use disposable paths. Cover both `new` and `new_project` aliases. | **Next Lane A task after A-00 review**, no dependency on Lane B |
| `A-02` | P1 / source-confirmed | **Quest list erasure** in `engine/ai_ops.py`: preserve valid list-form `quests.json`, or explicitly refuse unsupported formats; never replace an existing quest list with `{}`. Assert unrelated quests remain byte/semantic intact in supported cases. Real MCP/job path. | After A-01; same file ownership as A-05 |
| `A-03` | P1 / source-confirmed | **Read-only getters exposed as edits:** replace permissive reflection/denylist policy with a positive allowlist or equivalent provable edit contract. Cover `room_music`, `weather_sounds_of`, `hd2d_camera_of`, `hd2d_room_size`, `hd2d_sun_of`; protect all future getters. Verify edit path cannot substitute a room with getter output. | After A-02 if shared authoring tests |
| `A-04` | P1 / source-confirmed | **Legacy CLI writers bypass locks:** `new-npc`, `place-npc`, `edit-scene`, and discover additional write entrypoints in `mesh_cli/authoring.py`, `mesh_cli/scene/*`, `engine/tooling/scaffold.py`. Either route via canonical ownership or explicitly retire/refuse obsolete commands. Real two-process Studio lock tests and byte-for-byte refusals. | May be split by command family; coordinate with A-00 |
| `A-05` | P1/P2 / source-confirmed | **Unbounded/negative `paint_tiles` coordinates:** reject out-of-map coords, negative rows/columns, huge batches, unrealistic dimension/size growth; no partial write on invalid input. Real job/MCP tests and resource cap. | After A-02 (`engine/ai_ops.py` overlap) |
| `A-06` | P2 / audit claim | **MCP read confinement and any remaining old import paths**: determine actual external-read scope and policy, then test before fixing. | Later; don't bundle with destructive writes |
| `A-07` | P2 / prior independent review | **MCP stale routing and numeric light-index reference errors**: preserve same-batch `@N`, refuse stale route within lock. | Later; separate focused PRs |

**Initial order:** review A-00; implement A-01; then A-02/A-03; then A-04/A-05. **A-01 is urgent even if A-00 is awaiting CI**—but use a fresh separate worktree and avoid touching the undo PR.

### Lane B — Runtime and player-save reliability

| ID | Priority / evidence | Task and minimal acceptance criteria | State / dependencies |
|---|---|---|---|
| `B-01` | P1 / source-confirmed | **Non-unique entity save key:** `engine/save_runtime/entity_state.py` serializes/looks up by `mesh_name`. Two identically named entities must round-trip different HP, positions and state through the production SaveManager. Prefer stable IDs; design backward-compatible legacy-name migration and safe ambiguous legacy behavior. | **Lane B first task.** Potential schema migration: human approval before merge. |
| `B-02` | P1/P2 / source-confirmed | **Primary tag changes after load:** tags sorted for serialization and `state.tags[0]` assigned to primary. Persist primary separately or restore it unambiguously; preserve backward compatibility and verify `player` plus `friendly`. | After B-01 (same file) |
| `B-03` | P2 / partly confirmed | **Death/damage event semantics:** determine whether canonical + alias + legacy bus notifications are intentionally separate; reproduce a quest/counter double-count in a real game before change. Keep old legitimate subscribers working while enforcing one logical outcome. | After save tasks; coordinate event changes |
| `B-04` | P2 / likely | **Hit particles:** damage event handler reads object coordinates from a target-name payload. Reproduce using live GameWindow; fix contract/event routing without inventing a fake sprite. | After B-03 if event changes overlap |
| `B-05` | P2 / source-confirmed | **Behavior teardown:** four or more behaviours call nonexistent `bus.unsubscribe(subscription)` despite callback-style API. Exercise actual entity removal and event subscribers; ensure no lingering callbacks. | Can be independent if files disjoint |
| `B-06` | P2 / source-confirmed | **Named RNG streams** derive seeds from salted Python `hash((seed,name))`; use a stable, versioned seed derivation and preserve save/replay migration where relevant. Test across subprocesses with distinct `PYTHONHASHSEED`. | Separate PR, avoid changing game rules without evidence |
| `B-07` | P2 / likely | **`RangedAttackAI` player lookup:** shipped `Ashen_dungeon.json` references a behavior expecting `window.current_scene.entities`; determine production access via `scene_controller`; prove real-window behavior before/after. | Separate gameplay test |
| `B-08` | P2 / audit claims | **Physics tunneling, NaN/Infinity and other runtime input defects:** confirm against current runtime and prioritize on gameplay impact. | Later; no catch-all refactor |

**Initial order:** B-01, B-02, then B-03/B-04/B-05. B-06/B-07 can follow. Real-game tests, not only mocks, must anchor the correctness claims.

### Lane C — Release, installed product, and structural retirement (master schedules after A/B safety)

| ID | Priority | Item | Grounding / exit |
|---|---|---|---|
| `C-01` | Release blocker | **Required golden replay check passes with zero traces** | `engine/tooling/replay_goldens_command.py` returns 0 on missing or empty `traces/golden`. Make *required* mode fail closed; existing optional/no-golden command compatibility considered. Also reconcile [#359](https://github.com/septimus82/Mesh/issues/359). |
| `C-02` | Release blocker | **Release Draft ref/tag logic** | Fable's claim that `gh release create` cannot create a missing tag is **incorrect**. Actual risk: workflow's `target_ref` may differ from the tag's implicit creation ref (default `main`). Bind tag, artifact and reviewed tree to one target. |
| `C-03` | P2 | **`mesh check` fresh-scaffold world path** | `engine/tooling/check.py` defaults `worlds/main_world.json`; starter scaffolds `packs/core_regions/worlds/main.json`. Installed-project smoke test. |
| `C-04` | P2 / issue exists | **Pip-installed CLI commands import unpackaged `tooling/`** | [#357](https://github.com/septimus82/Mesh/issues/357): test isolated wheel in clean environment for actual advertised commands; either bundle supported functionality or fail with honest guidance. |
| `C-05` | Pre-release | **Main branch/release promotion** | `main` is older; [#344](https://github.com/septimus82/Mesh/pull/344) remains draft. Do not promote until creator and runtime contracts and release gates pass. |
| `C-06` | Maintainability | **Retire duplicate subsystems** | Inventory callsites, plugins, tests, installed-wheel entry points and old project compatibility for overlapping event buses, quest managers, scene writers and movement paths. Remove only with proof of replacement. Track [#392](https://github.com/septimus82/Mesh/issues/392). |
| `C-07` | Housekeeping | **Remote branch cleanup** | ~345 branches observed on 2026-11-19. Inventory merged/unique/active/evidence branches and local worktree references. No mass deletion; keep `main`, `redesign/visual-editor`, networking experiments and unique review evidence unless owner authorizes removal. |

## 5. Permanent creator/game acceptance scenarios

These are **end-to-end product contracts**, independent of whether implementation-level unit tests are green:

**Creator sequence CREAT-1:** Scaffold a game in an external disposable directory → open Studio → add room/NPC/map/tile → save → close → reopen → inspect file hashes and model → add AI operations → save newer human work → attempt stale AI undo → refuse, no file changes → export/open in installed wheel.

**Creator sequence CREAT-2:** Two real Studio processes, outer project references nested project room → child Studio has saved and unsaved edits → outer Ctrl+S, CLI and MCP attempts → each unauthorized writer refuses, nested room byte-identical, both editors keep their own dirty work.

**Creator sequence CREAT-3:** Attempt `mesh new --force` with traversal/absolute path, existing non-project directory, symlink/junction, nested valid project → cannot delete unrelated data. All tests use unique disposable directories and intentionally placed marker files.

**Gameplay sequence GAME-1:** Two same-name slimes, differing HP and position, plus player with multiple tags → save and close → relaunch → ensure each slime has its own state, player stays the player, quests/counters and inventory preserved.

**Gameplay sequence GAME-2:** Fight a real ranged enemy, take and deal damage, kill an enemy, observe effects, rewards and event counts, remove entities, save/reload, repeat. Assert no duplicate rewards or leaked subscriptions.

**Release sequence SHIP-1:** Install a built wheel into a clean environment outside the repository → `mesh new` → `mesh check`, `play`, `edit`, `validate` and selected advertised export/replay commands → fail required goldens when fixtures absent → verify release artifacts and tag point to the same reviewed revision.

## 6. PR and evidence contract — every worker follows this

**Before work:** establish current integration SHA; link an existing GitHub issue or create one only when authorized; prepare an isolated worktree; reproduce defect on base; capture minimal non-sensitive evidence. No modification to the user's `D:\Games\Mesh` checkout.

**PR requirements:**

- `Task ID`, scope, base SHA, head SHA, exact changed-file list and intended invariant.
- Before/after reproduction, including actual CLI command or real-window scenario as appropriate.
- Permanent failing-on-base test and passing-on-head test; byte-identical refusal assertions for data loss.
- Targeted suite, relevant adjacent regression suite, Ruff/mypy/import/exception policies.
- CI and Extended **first attempts**, with links, attempts and all failures preserved (no silent reruns).
- Explicit compatibility notes for old projects, persisted saves, and installed-wheel path where relevant.
- Remaining limitations, clear `READY FOR INDEPENDENT REVIEW` state; no self-merge.

**Worker report skeleton (submit in PR body/comment; don't rewrite this master file from a worker branch):**

```markdown
TASK: A-01
PR: <link> (draft)
BASE: <full SHA>
HEAD: <full SHA>
FILES: <exact paths>
BEFORE: <repro + observed files / exit codes>
AFTER: <same repro + preserved contents / exit codes>
TESTS: <targeted + cross-system + any skips>
CI: <run URL, attempt, result>
EXTENDED: <run URL, attempt, result>
LIMITATIONS: <facts, not speculation>
VERDICT: READY FOR INDEPENDENT REVIEW (NOT MERGED)
```

## 7. Master loop — review, correction, approval, merge

1. **Refresh:** read current `redesign/visual-editor` SHA, active PRs, relevant issues and their CI status. Reconcile against this file. If a task is already an open PR, don't assign it again.
2. **Pick next:** assign the highest-priority unblocked task to each idle lane. Check **changed-file overlap** against other active PR and planned changes.
3. **Dispatch:** send the worker a bounded issue-specific prompt with exact base SHA, ownership rules, regression criteria and `stop before merge` instruction.
4. **Receive report:** require PR with exact head SHA, reproductions and tests. Missing evidence means `CHANGES REQUIRED`, not an assumption of success.
5. **Review:** inspect actual changed code and critical call paths, not only test summaries. Validate adversarial examples and read failure logs. Check compatibility and declared scope.
6. **Decision:** `APPROVE` or `CHANGES REQUIRED`. If changes needed, send the **same worker** a precise list with expected reproductions. Do not launch a competing agent against that branch.
7. **Owner gate:** for P0/P1, destructive/migration or other reserved operations, request explicit human merge approval. For pre-authorized low-risk work, master may merge under defined policy.
8. **Integrate serially:** confirm reviewed head unchanged, approved base/tree, required CI/Extended passed; merge one PR; confirm tree and push; run/check post-merge CI/Extended on actual integration head. Never ignore a failed run or claim a cancelled run passed.
9. **Update:** close or annotate issue with evidence links; update the master file or its task section **only from the master**; assign next job. Keep report artifacts and reproduction tests in repo, not only temporary `/tmp` folders.
10. **Stop on anomaly:** head drift, unrelated changes, changed ownership, missing gate, release risk or conflicting worktrees => stop that merge and request owner decision.

### Suggested task labels (GitHub issues)

`reliability`, `lane:A` / `lane:B` / `lane:C`, `evidence:claim` / `evidence:source` / `evidence:reproduced`, `state:queued` / `state:implementing` / `state:review` / `state:approved` / `state:merged`, `risk:creator-data`, `risk:save-schema`, `needs-human-merge`.

The master should maintain issue state and PR links as the **live queue**. A checked-in Markdown file is the stable policy and human-readable snapshot, not a second competing issue database.

## 8. How to implement the automated pipeline (staged)

**Stage 0 — Now, usable without infrastructure:** two agents work in isolated Git worktrees; a master (one designated chat/CLI agent) manages GitHub tasks, PR reviews and prompts. Workers post immutable head SHAs, reports and evidence. The user need only ask the master for status or approve high-risk merges. The master can generate the next exact task brief from this document and GitHub, even after chat rollover.

**Stage 1 — Automated state tracking:** configure GitHub issue/PR labels and templates; let GitHub Actions report CI/Extended, and add a small manager workflow/script that detects a `READY FOR REVIEW` PR and produces a review checklist/status report. Keep all credentials in GitHub secrets/managed agent authorization. No unattended merges yet.

**Stage 2 — Agent dispatch (requires connected/running agents, not just a workflow):** a controller dispatches at most two tasks to separate Claude Code/Codex worker processes in different worktrees. Each worker reads an issue-specific prompt, edits its branch, runs tests and opens/updates a draft PR. Manager reacts to PR updates, evaluates checks and emits a specific fix request or approval. Protect rate limits, concurrency, accidental triggering and token budgets. Store logs and summaries on the PR or workflow artifact.

**Stage 3 — Delegated bounded merges (opt-in):** only after Stage 2 is reliable, permit master-controlled merges for explicitly approved low-risk task classes. High-risk tasks retain owner approval. Never auto-delete old branches, change `main`, delete project folders, or create releases merely because a status label changed.

A controller cannot be created by this file alone. To actually run automatically, choose **where the master and two worker processes live**, establish repo credentials and tool permissions, and implement the dispatch and review workflow. Do that as a separate infrastructure change after the reliability backlog is under control; do not block A-01/B-01 waiting for the automation.

## 9. Branch and legacy code cleanup policy

- **Keep:** `main`, `redesign/visual-editor`, all open PR heads, active experiment/networking branches, unreplaced review/evidence branches with unique commits, and any branch held by a worktree or named in an issue.
- **Candidate for removal only after verification:** merged feature/fix branches that are completely ancestors of integration and have no unique evidence/worktree dependency.
- **Never delete by name pattern alone.** Compare histories, PR association, tags, issues, worktrees and unmerged commits. Produce an owner-review CSV/table first. Batch deletes only with explicit consent.
- **Never delete old engine modules by age or duplicate-sounding name.** Inventory imports, runtime loads, dynamic reflection, serialized references, existing games, tests, plugin hooks and wheel entry points. Migrate users/tests first; delete behind a scoped PR with explicit backward-compatibility results.

## 10. New-session bootstrap prompt

Copy this into any future master chat (or supply it to the master agent):

```text
You are Mesh Reliability Master for septimus82/Mesh.
Read docs/plans/MESH_RELIABILITY_MASTER_PLAN.md from redesign/visual-editor
(or the attached MESH_RELIABILITY_MASTER_PLAN.md until installed).
Do not rely on previous chat context for current PR, branch or CI status.
Query GitHub for current integration SHA, active PRs, issues and checks.
Reconcile the task queue; never duplicate active PR work.
At most two implementation workers, with disjoint files and isolated worktrees:
Lane A creator/file safety; Lane B runtime/gameplay saves.
Workers submit PRs and evidence; you independently review, ask for fixes,
or recommend approval. No unreviewed auto-merges. Owner approval is required
for P0/P1, destructive/migration changes, branch deletion, main and release.
Report: current SHA, active work in each lane, blockers, next safe action,
and specific brief(s). Preserve first-attempt CI evidence.
Do not edit D:\Games\Mesh or delete branches without explicit authorization.
```

## 11. Suggested first actions

1. **PR #525 is reviewed**: independent review APPROVED at `5fd408d6` (legacy, partial-failure and mixed-manifest cases challenged), CI and Extended green at attempt 1. Its merge needs owner approval; follow-ups F1/F2 are tracked separately and not added to #525. Don't reopen the same task on another worker.
2. **Lane A starts A-01** after checking #525's changed files (it edits plan execution, not scaffolding): harden `mesh new --force` on a separate worktree. No direct experiments on meaningful user data.
3. **Lane B starts B-01** on a separate worktree: stable entity state persistence across save/reload; design legacy migration before editing saved-state schema.
4. **Master keeps the queue, review decisions, merge SHAs and evidence in GitHub**, then updates this Markdown after approved integration milestones. For #521/#522 remediation B, #523, #524 and #525, the reproduction and fault-injection scripts are committed under `docs/reviews/*_evidence/` (`*.py.txt`; #523's reproduction is its permanent real-window test). Whether scripts from earlier sessions' temporary scratchpad folders still exist is not verified: reproduce from the repository, never from ephemeral folders.

**Success criterion:** Mesh is not merely impressive on paper. The creator and gameplay acceptance sequences succeed repeatedly from a fresh installed build, without hidden data loss, while the master can account for every change from GitHub after any chat reset.