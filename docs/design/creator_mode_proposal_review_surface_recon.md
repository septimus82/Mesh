# Creator Mode Proposal Review Surface Recon

## Summary

CREATOR-1v decides where future Creator Mode proposal **review** should live in the UI. It is documentation-only: no accept/reject/apply, no buttons, no clickable actions, no input routing, no renderer changes, and no runtime code changes.

**Recommendation:** adopt a **hybrid handoff** model. Creator Mode keeps compact read-only proposal context; official mutation stays in the existing **AI Proposals** dock (`ProposalInbox` + `ProposalInboxOverlay`). Do **not** keep expanding the Creator Mode bottom panel.

See also [creator_mode_proposal_accept_recon.md](./creator_mode_proposal_accept_recon.md) for the official accept/apply mutation path (CREATOR-1p).

---

## 1. Current Creator Mode Proposal Display

As of CREATOR-1u, Creator Mode shows staged proposal information in the **bottom panel** (`Things to Fix` region). All of it is read-only text with **no `action_id` and no hitboxes** except the separate door **Stage Proposal** action in the right panel.

### Data sources

`CreatorModeController.build_snapshot()` performs one shared bridge read via `build_creator_proposal_status(self._proposal_bridge())`, then derives:

| Model | Module | Purpose |
|-------|--------|---------|
| `CreatorProposalStatusModel` | `creator_proposal_status.py` | Count + row list |
| `CreatorProposalAcceptReadinessModel` | `creator_proposal_accept_readiness.py` | Display-only Accept/Reject readiness per row |
| `CreatorProposalReviewDetailsModel` | `creator_proposal_review_details.py` | Dry-run / affected-id detail per row |

Bridge access is duck-typed: `getattr(bridge, "list_pending_proposals", None)()`. Creator Mode does **not** import `live_session_bridge`, `proposal_inbox`, or `editor_live_ops_controller`.

### What the bottom panel renders (top to bottom)

1. **Panel title:** `Things to Fix`
2. **Pending count summary** — e.g. `No staged proposals.`, `1 proposal waiting for review`, `3 proposals waiting for review`, or `Proposal review status unavailable.`
3. **Up to 3 pending proposal rows** (`MAX_RENDERED_PROPOSAL_ROWS = 3` in `creator_overlay_renderer.py`):
   - **Row line:** `{proposal_id} - {preview_summary}`
   - **Review readiness line:** `Review: Accept ready / Reject ready` (or `disabled` + reason)
   - **Compact detail line:** `Details: Affects {ids} - Dry-run {OK|Failed|Unknown} - W{n}/E{n}`
4. **Overflow hint** when `pending_count > 3`: `...and {n} more`
5. **Inspector warnings** (up to 2 lines), or default `No problems shown in Creator Mode.`

Each rendered proposal row can consume **up to three lines** (~45 px vertical step). Three proposals plus summary, title, and warnings can exceed usable space quickly.

### Bottom panel height behavior

In `creator_overlay_renderer.py`:

```text
bottom_h = min(220.0, max(132.0, win_h * 0.30))
```

At **720p** (`win_h = 720`):

- `720 * 0.30 = 216`
- `bottom_h = 216 px` → **~30% of window height**

The bottom panel grew from earlier ~28% caps (~92–132 px on 720p in CREATOR-1n) specifically to accommodate proposal rows, review readiness, and detail lines. Center viewport height shrinks accordingly.

### Existing concern

The bottom panel is doing too much:

- It was originally a lightweight “things to fix” strip.
- It now stacks count, multi-row proposal list, pseudo accept/reject readiness, dry-run detail, overflow text, and inspector warnings.
- It is the wrong density for meaningful review and the wrong place to add future accept/reject **click** targets (cramped, easy to mis-click, competes with warnings).
- Further expansion (Option A) will keep stealing center viewport and still cap at three visible rows.

Right panel space is already consumed by inspector fields and the door plan panel (including the one real clickable action: **Stage Proposal**).

---

## 2. Current Official Proposal Review Path

Creator Mode is **not** the official review surface today. The official path is the editor **AI Proposals** right-dock tab.

### ProposalInbox role

`engine/editor/proposal_inbox.py` — main-thread model attached to the editor controller:

- `list_pending()` → `editor.live_bridge.list_pending_proposals()`
- `accept(proposal_id)` → `editor.live_bridge.accept_pending_proposal(proposal_id)`
- `reject(proposal_id)` → `editor.live_bridge.reject_pending_proposal(proposal_id)`
- Returns `no_live_session` when bridge methods are missing

Same proposal store Creator Mode reads for display; inbox owns **review actions**.

### Bridge routing

`engine/editor/live_session_bridge.py`:

- Stages proposals in private `_proposals` via `stage_pending_proposal(ops)`
- Lists GUI-safe rows via `list_pending_proposals()`
- Accept/reject by id via `accept_pending_proposal` / `reject_pending_proposal`
- HTTP transport (`/live/stage_proposal`, `/live/accept_proposal`, `/live/reject_proposal`) enqueues onto the editor main thread

Creator Mode staging (door workflow) and Creator Mode status reads use the same bridge object (`editor.live_bridge`) but Creator Mode does not call accept/reject.

### UI routing

`engine/ui_overlays/proposal_inbox_overlay.py` — **AI Proposals** dock tab:

- Registered in `RIGHT_DOCK_TABS` as `"AI Proposals"`
- Draws when `dock.right_tab == "AI Proposals"`
- Lists pending proposals with preview text
- **Accept** and **Reject** buttons with hitboxes; clicks route through `controller.handle_mouse_click` (existing editor input router)
- Tests in `tests/test_cocreative_proposal_inbox.py` verify accept/reject click dispatch

### Live ops controller + revision guard

`engine/editor/editor_live_ops_controller.py`:

- **Stage:** dry-run batch, capture `base_revision = editor.content_revision`, return `LiveOpProposal`
- **Accept:** require dry-run ok; compare `proposal.base_revision` to current `content_revision` — stale proposals fail closed with no mutation
- **Apply:** each live op with `push_undo=False`, then one `ApplyAIOpBatch` parent command via `editor._push_command()`
- **Reject:** drop proposal reference; no scene mutation

Tests (`test_cocreative_live_ops.py`, `test_cocreative_live_bridge.py`) verify stale accept is blocked without mutation.

### ApplyAIOpBatch undo semantics

- One accepted proposal → **one** undo stack entry of type `ApplyAIOpBatch`
- Children hold per-op commands; undo reverts children in reverse order
- Reject does not push undo entries and does not change `content_revision`
- Verified in `tests/test_cocreative_proposal_inbox.py` (accept applies + undo; reject leaves scene and revision unchanged)

### Why this path is safer than a Creator Mode-owned accept path

| Risk if Creator Mode adds its own accept | Official inbox path |
|------------------------------------------|---------------------|
| Second mutation route bypassing revision guard | Single path through `EditorLiveOpsController.accept_proposal()` |
| Duplicate proposal store or id handling | Bridge `_proposals` is canonical |
| Accept during render/snapshot/build | Inbox accepts only on explicit user click in dock |
| Wrong undo batch shape | Existing `ApplyAIOpBatch` contract tested |
| Input routing fork in Creator overlay | Editor mouse router + dock overlay already wired |
| Creator Mode shell tied to command dispatch | Creator Mode stays read-only + staging only |

**Creator Mode should not implement a parallel accept/reject/apply trigger.** Any future affordance should hand off to this path.

---

## 3. Surface Options Compared

### Option A — Keep expanding the bottom panel

Add more rows, richer detail, or future accept/reject labels/buttons in the Creator Mode bottom strip.

| Pros | Cons |
|------|------|
| Immediate visibility while in Creator Mode | Already ~30% of 720p; crowds out map/tools viewport |
| No navigation or tab switch | Poor information hierarchy for review |
| Builds on existing CREATOR-1n–1u work | Three-row cap hides backlog; overflow is easy to miss |
| | Accept/reject buttons in a dense text stack → mis-click risk |
| | Duplicates AI Proposals dock responsibilities |
| | Encourages a second review UI with different layout/behavior |

**Assessment:** workable for **summary only**; bad target for mutation or deep review.

### Option B — Selected proposal detail panel inside Creator Mode

Dedicated Creator Mode region (e.g. right panel subsection or modal-style focus) showing one selected proposal with full detail and future actions.

| Pros | Cons |
|------|------|
| One proposal shown clearly | Duplicates inbox list + detail concepts |
| Keeps user inside Creator Mode shell | Requires **selection model + input** not yet designed |
| Room for dry-run warnings before action | Becomes a **second official review UI** unless carefully scoped read-only |
| | Still needs accept routing to bridge/inbox — extra wiring for little gain |
| | Right panel already competes with door plan + inspector |

**Assessment:** reasonable for **read-only detail of one row** only if selection is lightweight; poor as the primary accept surface.

### Option C — Hand off / focus existing Proposal Inbox (AI Proposals dock)

Creator Mode stages and summarizes; user switches to (or is focused on) **AI Proposals** to accept/reject.

| Pros | Cons |
|------|------|
| Uses official review path end-to-end | Tab switch may feel less “Creator Mode native” |
| No duplicated accept/reject UI | Requires focus/open integration (not built yet) |
| Clear ownership: inbox mutates, Creator Mode informs | User must discover the dock tab |
| Safer mutation + undo semantics for free | |
| Already has buttons, tests, and stale guard | |

**Assessment:** best **mutation** surface. Creator Mode should not replicate it.

### Option D — Hybrid (recommended)

Creator Mode: compact read-only status + short row context (current CREATOR-1n–1u scope, **frozen or slightly trimmed**, not expanded).

Future: display-only handoff hint such as **“Review in Proposal Inbox”** (or focus AI Proposals tab) — **no accept in Creator Mode**.

| Pros | Cons |
|------|------|
| Friendly context at staging time | Needs focus/open affordance in a later slice |
| Official inbox owns accept/reject | Two surfaces to keep in sync (same bridge read — already shared) |
| Avoids bottom-panel sprawl | Handoff click is future input work (explicitly not CREATOR-1v) |
| Aligns with CREATOR-1p accept recon | |
| Staging + “what’s waiting” visible; review where it’s safe | |

**Assessment:** best balance of Creator Mode UX and safety.

---

## 4. Recommendation

**Adopt Option D — hybrid handoff.**

Concrete policy:

1. **Creator Mode** continues to show compact read-only proposal status (count, up to three short rows, readiness/detail **as text only**).
2. **Do not** keep expanding the bottom panel with more lines, buttons, or per-row click targets.
3. **Do not** add Creator Mode Accept/Reject buttons before handoff exists and official-path dogfood is complete.
4. **All mutation** (accept/reject/apply) goes through **ProposalInbox** → **live bridge** → **EditorLiveOpsController** → **ApplyAIOpBatch**.
5. Next implementation slice should be **read-only handoff prep**, not accept.

If bottom panel content must change later, prefer **trimming** (e.g. drop redundant readiness line when handoff label exists) over **adding**.

---

## 5. Next Safe Implementation Slice

### Recommended: CREATOR-1w — Read-Only Proposal Inbox Handoff Model

**Status:** implemented (model-only).

**Goal:**

- Expose whether the official Proposal Inbox / AI Proposals dock is available and focusable (e.g. editor has `proposal_inbox`, dock tab `"AI Proposals"` registered).
- Expose a **display-only** label such as `Review in Proposal Inbox` (or `AI Proposals dock`) on the snapshot/overlay model.
- **No click yet**, no `action_id`, no hitbox, no input routing.
- **No** accept/reject/apply calls.
- Pure module(s) under `engine/editor/creator_mode/*` + tests; CREATOR-1w shipped **model-only** (no renderer line added; bottom panel height unchanged).

This is the first implementation slice of the hybrid handoff decision (Option D). It prepares UX copy and availability flags before any focus/open wiring (CREATOR-1x or later).

### CREATOR-1x — Display-Only Proposal Inbox Handoff Label

**Status:** implemented (display-only).

- Renders handoff as plain text by **replacing** the per-row `Review: Accept ready / Reject ready` line.
- Available handoff: `Review: Use AI Proposals`
- Unavailable handoff with pending proposals: `Review: AI Proposals unavailable - {reason}`
- No extra bottom-panel line; `bottom_h` unchanged; no click/focus/open behavior.
- Future inbox focus/open remains a separate slice after CREATOR-1x.

### CREATOR-1y — Official Inbox Dogfood With Creator-Staged Proposals

**Status:** documented; **interactive GUI checklist incomplete** (see `docs/design/creator_mode_official_inbox_dogfood.md`).

- Records the manual GUI dogfood procedure for Creator Mode staging → official AI Proposals accept/reject/stale guard.
- Launch smoke **PASS** (`main.py --edit`); steps 4–20 **NOT RUN** in agent session (native window not automatable).
- Supplementary automated inbox/live-ops tests **PASS** (10 tests); gap remains for Creator Mode click-path staging parity.
- **CREATOR-1z blocked** until a human operator completes the GUI checklist with all passes.
- If human dogfood fails, fix official Proposal Inbox path before more Creator Mode review UI.

### Alternative acceptable slice

**CREATOR-1w docs-only:** manual dogfood checklist run against the **official** AI Proposals inbox using Creator Mode–staged door proposals (no new code). Useful if team wants human verification before any handoff label lands.

### Explicitly not recommended next

- **Creator Mode Accept button** (clickable or display-only that implies imminent accept in bottom panel).
- **Bottom panel expansion** for fourth+ proposal rows or full dry-run dumps.
- **Creator Mode calling** `accept_pending_proposal` / `ProposalInbox.accept` from overlay code.

---

## 6. Future Dogfood Requirements (Before Any Creator Mode Accept/Reject Click)

Any PR that adds accept/reject **click** behavior anywhere in Creator Mode must first complete manual verification of the **official** path:

1. Start Mesh normally.
2. **F4** — enter editor.
3. **Shift+F5** — enter Creator Mode.
4. Select a door; **Stage Proposal** (Creator Mode click path).
5. Confirm proposal appears in Creator Mode bottom panel (count + row).
6. Open **AI Proposals** dock tab; confirm **same** `proposal_id` and preview summary.
7. **Accept** through official Proposal Inbox (not Creator Mode).
8. Verify scene changes **only after accept**; verify undo removes effects; verify redo if applicable.
9. Stage another proposal.
10. **Reject** through official Proposal Inbox; verify **no** scene mutation, **no** undo entry, `content_revision` unchanged.
11. Stage again; mutate scene manually; attempt accept — verify **stale** proposal fails without mutation.
12. Close cleanly; confirm **no** scene/content JSON committed unless intentionally saved.

Until this dogfood passes, do not add Creator Mode accept/reject click targets.

---

## 7. Files Inspected (Read-Only)

| File | Relevance |
|------|-----------|
| `engine/editor/proposal_inbox.py` | Official inbox model; accept/reject routing |
| `engine/editor/live_session_bridge.py` | Proposal store; list/stage/accept/reject API |
| `engine/editor/editor_live_ops_controller.py` | Revision guard; ApplyAIOpBatch creation |
| `engine/editor/creator_mode/creator_mode_controller.py` | Snapshot builds proposal status/readiness/details |
| `engine/editor/creator_mode/creator_state.py` | Snapshot fields for proposal models |
| `engine/editor/creator_mode/creator_overlay_renderer.py` | Bottom panel layout; 30% height; 3-row cap |
| `engine/ui_overlays/proposal_inbox_overlay.py` | AI Proposals dock UI (reference) |
| `tests/test_cocreative_proposal_inbox.py` | Inbox accept/reject/undo/dock tests |
| `tests/test_cocreative_live_bridge.py` | Bridge stale guard |
| `tests/test_cocreative_live_ops.py` | Live ops accept/stale/ApplyAIOpBatch |
| `tests/test_creator_mode_proposal_review_details.py` | Creator Mode detail display tests |
| `tests/test_creator_mode_proposal_accept_readiness.py` | Creator Mode readiness display tests |
| `docs/design/creator_mode_proposal_accept_recon.md` | CREATOR-1p accept path recon |

**Not modified in CREATOR-1v.**

---

## 8. CREATOR-1v Scope Confirmation

- Documentation only.
- No `engine/*` runtime changes.
- No tests changed.
- No accept/reject/apply implementation.
- No buttons, clickable actions, or hitboxes added.
- No input routing, renderer, bridge, inbox, or live ops changes.
- No scene/content JSON changes.
