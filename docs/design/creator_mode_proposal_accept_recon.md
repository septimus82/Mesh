# Creator Mode Proposal Accept Path Recon

## Summary

Mesh already has a safe proposal accept/apply path. Creator Mode should not create a second apply path. Future Creator Mode accept work should hand off to the existing bridge/inbox/controller flow and preserve the existing revision guard and undo batch semantics.

CREATOR-1p is documentation-only. It adds no accept/apply code, no buttons, no input routing, no renderer changes, and no scene mutation.

## Existing Accept Path

Current staged proposals live in `engine.editor.live_session_bridge.EditorLiveSessionBridge`.

The staged proposal flow is:

1. A caller stages live-op dictionaries through `EditorLiveSessionBridge.stage_pending_proposal(ops)`.
2. The bridge calls `_stage_proposal({"ops": ops})`.
3. `_stage_proposal()` validates that `ops` is a list, then calls `editor.stage_proposal(ops)`.
4. `EditorModeController.stage_proposal()` delegates to `EditorLiveOpsController.stage_proposal(ops)`.
5. `EditorLiveOpsController.stage_proposal()` deep-copies the ops, dry-runs them against a copied scene, stores `base_revision`, and returns a `LiveOpProposal`.
6. The bridge stores that proposal in its private `_proposals` map under a generated `proposal_id`.
7. `EditorLiveSessionBridge.list_pending_proposals()` exposes GUI-safe rows with `proposal_id`, `preview_summary`, `affected_ids`, and `dry_run`.

The accept path is:

1. The existing proposal inbox UI/model calls `ProposalInbox.accept(proposal_id)`.
2. `ProposalInbox.accept()` obtains `editor.live_bridge.accept_pending_proposal`.
3. `EditorLiveSessionBridge.accept_pending_proposal(proposal_id)` calls `_accept_proposal({"proposal_id": proposal_id})`.
4. `_accept_proposal()` looks up the proposal in `_proposals`.
5. If the proposal is missing, the bridge returns `{"ok": False, "mode": "live_editor", "reason": "proposal_not_found"}`.
6. If found, `_accept_proposal()` calls `editor.accept_proposal(proposal)`.
7. `EditorModeController.accept_proposal()` delegates to `EditorLiveOpsController.accept_proposal(proposal)`.
8. `EditorLiveOpsController.accept_proposal()` validates proposal type, dry-run success, and content revision.
9. If accepted, the live-op controller applies each op with `push_undo=False`, collects child commands, and pushes one `ApplyAIOpBatch` undo command.
10. On success, the bridge removes the proposal from `_proposals` and returns the accept result with `mode` and `proposal_id`.

## Existing Reject Path

The reject path is separate and non-mutating:

1. `ProposalInbox.reject(proposal_id)` forwards to `editor.live_bridge.reject_pending_proposal`.
2. `EditorLiveSessionBridge.reject_pending_proposal(proposal_id)` calls `_reject_proposal({"proposal_id": proposal_id})`.
3. `_reject_proposal()` looks up the proposal id.
4. If missing, it returns `{"ok": False, "mode": "live_editor", "reason": "proposal_not_found"}`.
5. If found, it calls `editor.reject_proposal(proposal)`.
6. `EditorModeController.reject_proposal()` delegates to `EditorLiveOpsController.reject_proposal(proposal)`.
7. The live-op controller drops its active proposal reference and returns success.
8. The bridge removes the proposal from `_proposals`.

Tests verify rejection leaves sprites, scene entity data, undo stack, and `content_revision` unchanged.

## Revision Guard

The critical stale-proposal guard lives in `EditorLiveOpsController.accept_proposal()`.

During staging, `EditorLiveOpsController.stage_proposal()` stores:

- `ops`: deep-copied live ops.
- `base_revision`: the editor `content_revision` at staging time.
- `preview_summary`: dry-run preview text.
- `dry_run`: dry-run result.

During accept, `EditorLiveOpsController.accept_proposal()` compares `proposal.base_revision` to current `editor.content_revision`. If they differ, it returns a failed stale result and does not apply proposal ops.

Existing tests verify stale accepts are blocked without mutation through both the direct controller path and the live bridge path.

## Undo And Batch Semantics

Accepting a proposal is undoable as one batch.

`EditorLiveOpsController.accept_proposal()` applies each child live op with `push_undo=False`, collects the command data returned by each live op, then calls `editor._push_command()` with:

```text
type: ApplyAIOpBatch
children: [...]
preview_summary: ...
```

`EditorCommandDispatchController` knows how to undo and redo `ApplyAIOpBatch` by reverting or applying child commands in the correct order. Existing tests verify:

- A single accepted proposal pushes one undo entry.
- Multi-op accepts are one undoable batch.
- Undo removes all accepted proposal effects.
- Redo reapplies all accepted proposal effects.

Creator Mode must preserve this path. It must not call command dispatch or `_push_command()` directly.

## Candidate Systems Found

### `engine/editor/live_session_bridge.py`

- Stages proposals in `_proposals`.
- Lists proposal rows for UI.
- Accepts/rejects by proposal id.
- Adds `mode` and `proposal_id` to accept/reject responses.
- Queues HTTP endpoint work onto the editor main thread for transport callers.

Creator Mode should use this as the proposal store/bridge surface, but only through injected/editor-owned bridge references. It should not call MCP HTTP tooling from inside the editor.

### `engine/editor/proposal_inbox.py`

- Existing main-thread proposal review model.
- Lists pending proposals from `editor.live_bridge.list_pending_proposals()`.
- Accepts via `editor.live_bridge.accept_pending_proposal(proposal_id)`.
- Rejects via `editor.live_bridge.reject_pending_proposal(proposal_id)`.
- Returns `no_live_session` when the bridge is unavailable.

This is the official in-editor review path today.

### `engine/editor/editor_live_ops_controller.py`

- Owns dry-run staging, accept, reject, live-op application, stale guard, and undo batch creation.
- This is where validation and mutation semantics live.
- Future Creator Mode accept work must not bypass it.

### `engine/editor_controller.py`

- Exposes `stage_proposal()`, `accept_proposal()`, and `reject_proposal()` as thin delegates to `EditorLiveOpsController`.
- Maintains `content_revision` through `_mark_dirty()`.
- Provides `_push_command()` as the undo entry path used by live-op accept.

Creator Mode should not call `_push_command()` or command dispatch directly.

### `engine/editor/editor_command_dispatch_controller.py`

- Applies and reverts editor commands.
- Handles `ApplyAIOpBatch` by applying children in order and reverting children in reverse order.

This is the lower-level undo/redo mechanism after the accepted proposal has already gone through the proposal guard.

## Tests Inspected

Relevant coverage already exists in:

- `tests/test_cocreative_live_ops.py`
- `tests/test_cocreative_live_bridge.py`
- `tests/test_cocreative_proposal_inbox.py`
- `tests/test_cocreative_chatbox_grounding.py`

Verified behaviours from tests:

- Staging dry-runs without mutation.
- Accept at matching revision applies changes.
- Accept pushes one `ApplyAIOpBatch`.
- Multi-op accept remains one undoable batch.
- Undo/redo works for accepted proposals.
- Stale accept is blocked without mutation.
- Reject drops proposals without mutation.
- Proposal inbox accept/reject routes through existing bridge.
- AI proposals dock uses the existing inbox path.

## Safety Invariants For Future Creator Mode Accept Work

Any future Creator Mode accept/apply slice must preserve all of these:

- No direct scene mutation from Creator Mode.
- No direct scene JSON writes.
- No bypassing `EditorLiveOpsController.accept_proposal()`.
- No bypassing the `base_revision` versus `content_revision` stale guard.
- No direct command dispatch from Creator Mode.
- No direct `_push_command()` from Creator Mode.
- No accept during render.
- No accept during snapshot/model building.
- No auto-accept after staging.
- No accept without a visible proposal id.
- No accept if proposal id is missing.
- No accept if proposal id is stale.
- No accept if bridge is unavailable.
- No apply if the bridge result fails.
- No Creator Mode-owned proposal store.
- No MCP HTTP tooling from inside the editor.
- All apply behaviour remains in the existing undoable `ApplyAIOpBatch` path.
- Reject remains non-mutating.
- Missing proposal ids fail closed as `proposal_not_found`.

## Future Implementation Recommendation

Do not jump directly to a clickable Apply button from Creator Mode.

Recommended next slice:

### CREATOR-1q Candidate: Creator Proposal Review Action Model

Add a read-only model that determines whether a pending proposal row is eligible to show future accept/reject affordances. It should:

- Read pending rows through the existing bridge/inbox surface.
- Expose display-only action state.
- Fail closed when bridge is unavailable.
- Require a concrete `proposal_id`.
- Not call accept/reject/apply.
- Not add clickable UI.
- Not touch input routing.

An alternate acceptable next slice is a pure accept readiness model with the same constraints.

Only after that model is reviewed should a later slice consider input wiring. That future clickable slice must call the existing `ProposalInbox.accept(proposal_id)` or `editor.live_bridge.accept_pending_proposal(proposal_id)` path, not a new apply route.

## Manual Dogfood Requirements For Future Accept/Apply PRs

Any future Creator Mode accept/apply PR must dogfood the existing official review path first:

1. Start Mesh.
2. Press F4 to enter editor mode.
3. Press Shift+F5 to enter Creator Mode.
4. Stage a proposal.
5. Confirm the proposal is listed.
6. Accept through the existing official AI Proposals inbox/review path before Creator Mode gets its own button.
7. Verify scene changes happen only after accept.
8. Verify undo works and removes the accepted proposal effects.
9. Verify redo works if applicable.
10. Verify stale proposal accept fails without mutation.
11. Verify reject removes the pending proposal without mutation.
12. Verify no scene/content JSON is committed unless intentionally saved.
13. Verify Creator Mode does not accept during render or snapshot.

## Open Questions

- Whether Creator Mode should ever get its own accept button, or should only deep-link/focus the existing AI Proposals inbox.
- Whether accept/reject readiness should be modeled per pending row or as a single selected proposal review panel.
- Whether proposal rows should display dry-run warnings before any Creator Mode accept affordance exists.
- Whether Creator Mode should require a selected pending proposal id before rendering future accept/reject action state.
