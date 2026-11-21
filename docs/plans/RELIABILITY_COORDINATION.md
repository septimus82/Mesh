# Mesh reliability: coordination runbook (master + two agents)

How the reliability programme is run day to day. Policy and the defect queue: `MESH_RELIABILITY_MASTER_PLAN.md`
(PR #526). Live state: `RELIABILITY_STATUS.md`. Evidence lives in PRs and `docs/reviews/`, not here.

## 1. Roles and model routing

| Role | Definition | Model | Scope | May |
|---|---|---|---|---|
| Master coordinator | the owner's Claude Code session | the session's model | assignment, review, CI checks, status board, merge proposals | review, request corrections, merge **only** with the owner's explicit approval for P0/P1, migrations, destructive changes |
| Agent A, `mesh-creator-safety` | `.claude/agents/mesh-creator-safety.md` | Sonnet | Studio persistence, CLI, MCP, authoring ops, plan backups/undo, ownership, scaffolding | edit its own branch in its own worktree, push it, open a draft PR |
| Agent B, `mesh-gameplay-reliability` | `.claude/agents/mesh-gameplay-reliability.md` | Sonnet | runtime save/load, entity identity, tags, behaviours, combat events, RNG determinism | same |
| `mesh-discovery` | `.claude/agents/mesh-discovery.md` | Haiku | bounded read-only lookups (does X exist, where) | read and search only (no Bash, no edits) |

Haiku never gets persistence or destructive work. Workers never merge, approve, force-push, rewrite history, delete
branches, change the default branch, or touch `D:\Games\Mesh`.

**Loading.** Claude Code loads project agents from `.claude/agents/` of the folder the session starts in. They work by
name (`subagent_type: mesh-creator-safety`) only in a session started in a checkout that contains these files (after
this PR merges, or a session started in its worktree). Until then the master starts a `general-purpose` agent with
`model: sonnet` (or `haiku`) and tells it to read and follow the definition file: same instructions, same routing.

## 2. Isolation

- One worktree and one branch per worker task, created by the master from the current integration tip:
  `git worktree add -b <lane>/<task-id>-<slug> D:\Games\Mesh-<task-id> <base SHA>`.
  (Probe worktrees `D:\Games\Mesh-agent-a` / `-agent-b` are detached at the base, for read-only work.)
- The worker's first step is `git rev-parse HEAD` == the brief's base and a clean `git status`; otherwise it stops.
- The master does **not** use the Agent tool's own `isolation: "worktree"`: that worktree comes from the session's
  checkout (`D:\Games\Mesh`, far behind the integration branch) and lives under that checkout's folder
  (`D:\Games\Mesh\.claude\worktrees\`), which the owner's checkout rule forbids.
- At most one active production PR per worker, two in total, with disjoint changed files (master checks
  `gh pr diff --name-only` of every open PR before dispatch).

## 3. Dispatch brief (master to worker)

```text
TASK: <id> (<priority>)   AGENT: <name>   MODEL: sonnet
WORKTREE: D:\Games\Mesh-<id>   BRANCH: <lane>/<id>-<slug>   BASE: <full SHA>
DEFECT: <one paragraph; evidence level; exact files/lines already located>
IN SCOPE: <files>   OUT OF SCOPE: <files / other lane / named deferrals>
ACCEPTANCE: <reproduction to show on base; permanent tests; refusal byte-identity; compatibility>
VALIDATE: <targeted suites + adjacent suites + gates>
STOP AT: READY FOR INDEPENDENT REVIEW. No merge.
```

The master passes located file:line evidence from discovery so the worker doesn't rescan the repository.

## 4. Master review checklist (per worker report)

1. PR head equals the reported HEAD; base equals the brief's base or the current tip (no surprise drift).
2. `gh pr diff --name-only`: only in-scope files.
3. Read the production diff and the critical call path; do not rely on the report.
4. Reproduction evidence present for base and head; regression test fails on base (worker shows it).
5. CI and Extended first attempts on that exact head (`gh run list --commit <head>`; attempts preserved).
6. Verdict: `APPROVE` or `CHANGES REQUIRED` with a precise correction list sent to the **same** worker.
7. Owner approval for P0/P1, migrations, destructive changes. Then one merge at a time: head unchanged,
   `git merge-tree --write-tree <tip> <head>` equals the reviewed tree, merge, check the merged tree, watch
   post-merge CI and Extended on the new tip, update the status board.

## 5. A fresh master session (no chat history)

1. Read `docs/plans/RELIABILITY_STATUS.md` and this runbook (from `redesign/visual-editor`, or the newest open
   `docs/reliability-*` PR branch if not merged yet).
2. `git fetch`; `gh pr list --state open`; for each board row with a PR: `gh pr view <n> --json state,isDraft,headRefOid`
   and `gh run list --commit <head>`; compare with the board. GitHub wins over the board; fix the board.
3. Check worktrees (`git worktree list`) against the board's worktree column; never delete one without the owner.
4. Report: integration SHA, each lane's active task and state, blockers, the next safe action, and any brief to send.

## 6. Usage controls

- Master reviews and decides; workers implement. The master does not re-implement or re-run a worker's full suites:
  it reuses the PR's CI/Extended evidence on the exact head and runs only targeted checks where review needs them.
- Discovery first (Haiku, read-only), then one bounded Sonnet task with the located evidence in its brief.
- No nested agent chains (workers don't spawn agents), no repository-wide rescans per task, no local duplicate of a CI
  run already green on the same head, small PRs.
- Each report names the model that ran it (self-reported from the agent's system prompt; the Agent tool reports token
  counts, not the model, so routing is verified by the model's own statement plus the explicit `model:` setting).

## 7. Automation boundary

**Implemented (Stage 0):** reusable subagent definitions run under one active master session. Nothing runs when no
session is open; no background services, schedules or unattended merges exist.

**Not implemented: an unattended controller.** Minimal safe design, for a later owner decision:

- **Where:** a GitHub Actions workflow (`workflow_dispatch` plus a label trigger such as `agent:dispatch`), running
  Claude Code headless (`claude -p` with a fixed prompt, `--max-turns`, an allowed-tools list, the agent definitions
  from the repository) on a runner with a fresh checkout. A job per task, so isolation is the runner itself.
- **State in:** the issue or PR the label is on, `RELIABILITY_STATUS.md`, `gh` with a fine-grained token scoped to this
  repository (contents: write on non-protected branches, pull-requests: write, actions: read). No merge rights.
- **State out:** the worker's report as a PR comment, the PR itself (draft), labels for state
  (`state:review`, `state:changes-required`).
- **Guards:** branch protection on `redesign/visual-editor` and `main` (the token can't push them), a concurrency
  group per lane (one job per lane), a monthly budget cap on the API key, a job timeout, and owner-only labels to
  dispatch. Merges stay manual.
- **Needed from the owner:** an Anthropic API key or Claude Code GitHub app authorization as a repository secret, the
  token, branch-protection settings, and agreement on which task classes may be dispatched without a live master.
