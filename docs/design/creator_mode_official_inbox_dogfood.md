# Creator Mode Official Inbox Dogfood (CREATOR-1y)

## Summary

CREATOR-1y records manual GUI dogfood intended to prove that proposals **staged from Creator Mode** are reviewed and mutated **only** through the official **AI Proposals** dock (`ProposalInbox` → `live_bridge` → `EditorLiveOpsController`).

This document does **not** implement Creator Mode accept/reject/focus/open. It is documentation-only.

## Session metadata

| Field | Value |
|-------|-------|
| Date | 2026-07-03 |
| Branch | `docs/creator-1y-official-inbox-dogfood` |
| Mesh entry | `py -3.13 main.py --edit` |
| Editor bindings | **F4** = editor toggle, **Shift+F5** = Creator Mode toggle |
| Operator | Agent session (automated environment) |

## Launch smoke

| Check | Result | Notes |
|-------|--------|-------|
| Mesh starts normally | **PASS** | `py -3.13 main.py --edit` opened 1280×720 window, editor mode enabled, live bridge active |
| Clean shutdown after launch smoke | **PASS** | Background editor process stopped after launch verification |

## Interactive GUI dogfood checklist

**Status: INCOMPLETE — requires human operator.**

The agent environment can launch the native Arcade editor but **cannot drive** F4 / Shift+F5, entity selection, Creator Mode overlay clicks, or AI Proposals dock Accept/Reject buttons on the native window. Steps 4–20 below were **not executed interactively** in this session.

A human operator must re-run this checklist locally and update the **Human sign-off** section before CREATOR-1z (focus/open readiness) proceeds.

| Step | Action | Result | Notes |
|------|--------|--------|-------|
| 1 | Start Mesh normally | **PASS** | See launch smoke |
| 2 | Press **F4** to enter editor | **NOT RUN** | Native key input not automatable from agent |
| 3 | Press **Shift+F5** to enter Creator Mode | **NOT RUN** | — |
| 4 | Select a door | **NOT RUN** | — |
| 5 | Stage a door proposal from Creator Mode | **NOT RUN** | — |
| 6 | Confirm Creator Mode bottom panel: count, row, `Review: Use AI Proposals`, detail line | **NOT RUN** | Expected shape documented below |
| 7 | Open official **AI Proposals** dock/tab | **NOT RUN** | — |
| 8 | Confirm same proposal id/summary in AI Proposals | **NOT RUN** | — |
| 9 | Accept through official AI Proposals (not Creator Mode) | **NOT RUN** | — |
| 10 | Verify scene changes only after accept | **NOT RUN** | — |
| 11 | Verify undo removes accepted change | **NOT RUN** | — |
| 12 | Verify redo reapplies change (if available) | **NOT RUN** | — |
| 13 | Stage another proposal | **NOT RUN** | — |
| 14 | Reject through official AI Proposals | **NOT RUN** | — |
| 15 | Verify reject causes no scene mutation | **NOT RUN** | — |
| 16 | Verify reject does not create undo entry | **NOT RUN** | — |
| 17 | Stage another proposal | **NOT RUN** | — |
| 18 | Mutate scene manually before accepting | **NOT RUN** | — |
| 19 | Try accepting stale proposal | **NOT RUN** | — |
| 20 | Verify stale accept fails closed with no mutation | **NOT RUN** | — |
| 21 | Confirm no scene/content JSON committed unless intentionally saved | **PASS** | No dogfood-driven scene/content writes in this session; see dirty-file status |

### Expected Creator Mode display shape (when GUI is run)

After staging a door with SceneExit params, the bottom panel should show roughly:

```text
1 proposal waiting for review
{proposal_id} - Set SceneExit params on {door_entity_id}
Review: Use AI Proposals
Details: Affects {door_entity_id} - Dry-run OK - W0/E0
```

- `proposal_id`: hex id from `live_bridge.stage_pending_proposal` (e.g. 32-char uuid hex)
- `preview_summary`: from dry-run, typically `Set SceneExit params on …`
- Creator Mode must **not** show Accept/Reject buttons

### Expected AI Proposals dock shape

- Tab: **AI Proposals** (right dock)
- Header: `AI Proposals (N)`
- Same `proposal_id` and preview summary as Creator Mode row
- **Accept** / **Reject** buttons on the official overlay only

## Supplementary automated verification (official path)

These tests exercise the **same official ProposalInbox / bridge / live-ops path** that GUI dogfood must validate. They are **not** a substitute for interactive Creator Mode staging + dock review, but they passed in this session:

```text
py -3.13 -m pytest tests/test_cocreative_proposal_inbox.py \
  tests/test_cocreative_live_ops.py::test_accept_stale_proposal_is_blocked_without_mutation \
  tests/test_cocreative_live_bridge.py::test_live_accept_proposal_over_transport_blocks_stale_revision \
  -q -p no:cacheprovider

10 passed in 5.39s
```

| Behavior | Automated result | Relevant test coverage |
|----------|------------------|------------------------|
| Staging lists in inbox without mutation | **PASS** | `test_proposal_inbox_lists_two_staged_bridge_proposals_without_mutation` |
| Accept applies only via inbox; one `ApplyAIOpBatch` undo entry | **PASS** | `test_proposal_inbox_accept_applies_batch_as_one_undoable_command` |
| Undo removes accepted effects | **PASS** | same test (`controller.undo.undo()`) |
| Reject is non-mutating; no undo entry; revision unchanged | **PASS** | `test_proposal_inbox_reject_drops_without_mutation_or_undo` |
| Accept click routes through editor mouse router | **PASS** | `test_ai_proposals_accept_click_dispatches_through_editor_mouse_router` |
| Reject click routes through editor mouse router | **PASS** | `test_ai_proposals_reject_click_dispatches_through_editor_mouse_router` |
| Stale accept fails closed (controller) | **PASS** | `test_accept_stale_proposal_is_blocked_without_mutation` |
| Stale accept fails closed (bridge transport) | **PASS** | `test_live_accept_proposal_over_transport_blocks_stale_revision` |

**Gap:** automated tests stage via bridge/live-ops directly, not via Creator Mode **Shift+F5 → Stage Proposal** click. Human GUI dogfood must confirm Creator-staged rows appear in both surfaces with matching ids.

## Dirty file status after session

Dogfood did **not** intentionally modify scene/content JSON.

Pre-existing unrelated dirty/untracked files remained on disk (not introduced by CREATOR-1y):

- `engine/assets.py` (modified, unrelated)
- Various untracked assets/scenes from other work (`scenes/parallax_demo.json`, etc.)

No new scene/content JSON was committed for CREATOR-1y.

## Human sign-off (required before CREATOR-1z)

| Field | Status |
|-------|--------|
| Operator name | _pending_ |
| Date completed | _pending_ |
| All GUI steps 2–20 pass | _pending_ |
| Matching proposal id in Creator Mode + AI Proposals | _pending_ |
| Accept mutates only after official accept | _pending_ |
| Undo/redo verified | _pending_ |
| Reject non-mutating | _pending_ |
| Stale accept blocked | _pending_ |

## Gate recommendation

| Outcome | Recommendation |
|---------|----------------|
| **Current session** | **BLOCKED** for CREATOR-1z focus/open — interactive GUI checklist incomplete |
| **After human pass** | CREATOR-1z may begin read-only focus/open readiness (still no accept in Creator Mode) |
| **If human dogfood fails** | Fix official Proposal Inbox / bridge / live-ops path before more Creator Mode review UI |

## Scope confirmation

- Documentation only; no runtime code changes in CREATOR-1y.
- No Creator Mode accept/reject/focus/open added.
- No input routing, renderer, bridge, inbox, or live-ops changes.
