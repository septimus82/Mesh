# S1-0 checkpoint: owner decisions (2026-11-25)

The owner approved S1 stabilization at the S1-0 checkpoint. The decisions below are recorded from the owner's message, and they bind every S1 PR. The options each one refers to are in [14_owner_decision_brief.md](14_owner_decision_brief.md).

## Decisions

| # | Decision |
|---|---|
| D1 | **A.** S1-1 to S1-5 are exit-required; S1-6 and S1-7 are best-effort. **#643** (missing HUD health panel) moves into **S1-3**. **#390** is deferred and recorded explicitly as unresolved save-data behaviour. |
| D2 | The recommended severities: #623 P1, #654 P1, #653 P2, #624 B P2/P3, #621 P2, #620 P1. For a Shopkeeper with Dialogue, the shop **opens after the conversation completes**; an explicit choice-driven option stays possible for future authoring. |
| D3 | **A.** Repair the legacy editor's file operations, refusing unsafe operations as the fallback. Keep the legacy editor unavailable in game launches. Retire it only after its remaining capabilities have been migrated to Studio. |
| D4 | **A.** Shipped games may display read-only diagnostic overlays. Debug battles, cheats, breeding shortcuts, file-writing tools and other state-changing debug actions require an explicitly authorized developer launch, with no export-accessible privilege escalation. `python main.py` is a normal game launch; developers use `mesh play` or explicitly enabled developer tooling. |
| D5 | **A.** One project-root resolver. Older CWD-relative saves get narrowly scoped, read-only compatibility. Nothing is ever written back to an ambiguous legacy location. |
| D6 | **A.** Per-entity persistent facts in room memory, preserving old-save loading and stable entity identities, with explicit save-compatibility tests. |
| D7 | **A.** New projects get a small scaffolded items database, and a missing database degrades gracefully. A full inventory must not silently consume rewards or currency. Obsolete templates are retired only after checking references and preserving any useful examples. |
| D8 | **A.** Keep #629 as historical audit evidence, provided its contents are safe for public distribution. |
| D9 | **R4 approved**, with proof that the merge and PR trees are identical. **R2** needs measurements before it is switched on. **R3** is optional. **R1's** failing fast-tier timing gate is not removed unless an equivalent enforceable replacement is approved. |
| D10 | **A.** Flaky tests are quarantined with a date, a linked issue and an expiry, and keep running in report-only mode. No silent retries. |
| D11 | **Contain** all five duplicate-runtime areas. No large subsystem mergers during S1. |
| D12 | **A.** `mesh doctor` warns about existing `hp: 1.0` data and offers an opt-in correction; nothing is silently rewritten. Replay golden changes need case-by-case review and evidence. |
| D13 | **A.** One hands-on Studio GUI acceptance at the S1 exit checkpoint. No visible desktop automation without the owner's explicit permission for that session. |
| D14 | **A.** Keep the documented load-time entity semantics, warn creators about incorrect usage, and fix the sample content. Add sample walls only if a supported showcase needs them. |
| D15 | **Option A in principle.** See below. |

## D15: username exposure, what was done and what remains retrievable

**What was done:**
- **No PR from the investigation branch.** No pull request has been, or will be, opened from `docs/s1-0-investigation`. That history contains commit `035d0280`, which briefly held the owner's Windows username inside temp-file paths in copied tool output.
- **Clean publication.** These documents are published from a new branch, `docs/s1-stabilization-plan`, created from the integration tip. It holds only the reviewed, clean `docs/s1/` tree, plus this file, and its history never contained the exposing commit.
- **Scrub PR.** A separate focused PR scrubs the six pre-existing tracked files that contain the username (listed in [10_health_report.md](10_health_report.md) §8).
- **Clean evidence.** The audit evidence is kept without personal machine paths.
- **History untouched.** No integration or `main` history is rewritten or force-pushed.

**What remains retrievable** (until the owner separately approves deleting the branch or contacting GitHub Support):
- **The investigation branch.** `docs/s1-0-investigation` still exists on the public origin, and its commit `035d0280` shows the username to anyone who browses it.
- **Older history of the six files.** After the scrub PR merges, earlier commits on `redesign/visual-editor` (and on `main`, for the three files that are also there) still contain the username in those files. Only a history rewrite, which is not authorized, would remove it.
- **Forks and clones.** Anyone who forked or cloned the repository while the commits were reachable keeps a copy. Nothing on our side can change that.
- **Cached commits.** GitHub can keep serving a commit by its SHA even after a branch is deleted or force-pushed, until GitHub Support purges it. Search engines and archive services may also have cached pages.
