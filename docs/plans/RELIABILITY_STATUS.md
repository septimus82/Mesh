# Mesh reliability: status board

Maintained by the master only (workers report in their PRs). GitHub is the source of truth: a fresh master session
rechecks every row (`RELIABILITY_COORDINATION.md` §5) before acting. IDs and priorities: `MESH_RELIABILITY_MASTER_PLAN.md`.

**As of 2026-11-19 (cycle 2).** Integration `redesign/visual-editor` = `b095ecd4a1bed9ba0f9d76f4bbd31ea56fa26e3f`
(post-merge CI 44564645751 and Extended 44564645911 green, attempt 1). Integrated in cycle 1, each with tree identity
and post-merge gates checked: #525 → `d2dee7cf`, #529 → `190f5349`, #526 → `7307a48f`, #527 → `b095ecd4`.

States: `QUEUED` · `DISCOVERED` (source located, not reproduced) · `IN PROGRESS` · `READY FOR REVIEW` · `APPROVED`
(master) · `MERGED + VERIFIED`. Approval: `OWNER` = the owner must approve the merge.

| ID | Pri | Agent (model) | State | Branch / PR | Base → head | Evidence | Master verdict | Approval | Next action |
|---|---|---|---|---|---|---|---|---|---|
| A-02 quest list erasure | P1 | mesh-creator-safety (Sonnet) | APPROVED | `fix/a02-quest-list-erasure` / #530 (draft) | `b095ecd4` → `62af786b` | reproduced (list of 2 quests replaced by `{"c": …}` via `apply_job` and MCP); fixed in `engine/ai_ops.py` (list stays a list, dict unchanged, malformed refused byte-identical; edit/delete gain list support); 64 tests (20 fail on base); 5/5 faults; CI 44576471695 ✓ a1, Extended 44576462905 ✓ a1 | **APPROVE** | OWNER | merge on owner approval |
| B-01b duplicate-id scene snapshot | P1 | mesh-gameplay-reliability (Sonnet) | APPROVED (after one correction) | `fix/b01b-duplicate-id-snapshot` / #531 (draft) | `b095ecd4` → `77d72f5c` | reproduced (twins: first one's move lost in the snapshot; after reload both got the second twin's tags); snapshot claim rule in `persistence.py` + order pairing in `saved_world.compose`; real hidden-window round trip now keeps each twin's position and tags; goldens prove unique-id scenes identical to the base; 23 default-lane + 1 GPU test; 8/8 faults; final head CI 44580262193 ✓ a1, Extended 44580263301 ✓ a1. **Earlier heads (kept):** `a51c9e86` CI 44577439782 ✗ and Extended 44577435395 ✗ (ruff gate: an evidence `.py` file and a long line); `06c48cda` CI 44580098831 cancelled (superseded) | round 1 **CHANGES REQUIRED** (load side `compose` still merged twins); round 2 **APPROVE** | OWNER | merge on owner approval; lands before B-01 |
| B-01 entity save identity (v3 migration) | P1 | (design: Sonnet; rev 3: master) | DESIGN READY (owner decisions applied) | `design/b01-entity-save-identity` / #528 (draft, docs only) | `ad91e28c` → `99e1768e` | rev 3: Q2 provably-unique legacy binding, Q7 manual recovery, Q8 verified `.v2.bak` or no overwrite, Q9 B-01b first, unresolved records carried by every save (T23, T31-T36) | design complete | OWNER (implementation of the migration not authorised) | after B-01b merges: owner decides on implementation |
| B-02 primary tag after load | P1/P2 | mesh-gameplay-reliability | DISCOVERED | after B-01 (same file) | | `entity_state.py:309` sorted tags, `:413` `mesh_tag = state.tags[0]` | | OWNER | queue behind B-01 |
| A-02b dict-form quests without `"id"` never load | P2 | (unassigned) | DISCOVERED | | | A-02 review: `engine/quests.py:61-73` ignores dict keys and keeps only entries with their own `"id"`; `add_quest_definition` in dict form doesn't add one | | owner | candidate next Lane A task (small) |

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
- **B-01b, informational:** pairing of saved twins with authored twins is by order (deterministic; positional if the
  room file was reordered since the save). Behaviour state of twins is still name-keyed until B-01.
- **Process:** a worker reported "ruff ok" while its pushed head failed the ruff gate in CI (B-01b round 1). Workers
  must run the gates on the exact commit they push, after the last change.

## Task log (models and usage, as reported by the Agent tool)

| Task | Model | Tool calls | Tokens | Output |
|---|---|---|---|---|
| cycle 1: A-01 probe, B-01/B-02 probe, plan lookup, #525 review, A-01, B-01 design + rev 2 | Sonnet 5.5 ×6, Haiku 5.5 ×1 | 136 | ~725k | #529 merged, #528, review verdicts |
| A-02 implementation | Sonnet 5.5 | 19 | ~94k | #530 |
| B-01b round 1 | Sonnet 5.5 | 41 | ~125k | #531 `a51c9e86` |
| B-01b round 2 (correction, same agent) | Sonnet 5.5 | 66 | ~149k | #531 `77d72f5c` |
| B-01 design rev 3 | master (no agent) | | | #528 `99e1768e` |

## Worktrees in use

| Worktree | Holds |
|---|---|
| `D:\Games\Mesh-A-02` | #530 |
| `D:\Games\Mesh-B-01b` | #531 |
| `D:\Games\Mesh-B-01` | #528 |
| `D:\Games\Mesh-board` | this board update |
| `D:\Games\Mesh-relmaster` | #527's branch (merged): removable with the owner's OK |

Removed in cycle 2 (each clean and fully merged first): `Mesh-staleundo`, `Mesh-A-01`, `Mesh-plan526`, `Mesh-agent-a`,
`Mesh-agent-b`. Their branches are kept.
