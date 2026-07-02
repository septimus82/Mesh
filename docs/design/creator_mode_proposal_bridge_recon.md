# Creator Mode Proposal Bridge Recon

## Summary

Mesh already has a safe proposal/staging mechanism in the co-creative live editor path. The core path is:

- `engine.editor.editor_live_ops_controller.EditorLiveOpsController`
- `engine.editor.live_session_bridge.EditorLiveSessionBridge`
- `engine.editor.proposal_inbox.ProposalInbox`
- `engine.editor_controller.EditorModeController.stage_proposal()`
- `engine.editor_controller.EditorModeController.accept_proposal()`
- `engine.editor_controller.EditorModeController.reject_proposal()`

The important contract is two phase: staging performs a dry run and records a pending proposal without mutating the live scene; accepting is a separate explicit action that checks the editor content revision and applies the proposal as one undoable batch. Creator Mode should use this existing bridge later instead of inventing a direct JSON mutation path.

CREATOR-1d added no staging, no applying, and no scene mutation.

## Candidate Systems Found

### Live editor proposal controller

Path: `engine/editor/editor_live_ops_controller.py`

What it does:

- Defines `LiveOpProposal`.
- `stage_proposal(ops)` deep-copies live ops, dry-runs them against a copied scene, records `base_revision`, and returns preview/dry-run data.
- `accept_proposal(proposal)` applies only a valid proposal whose `base_revision` still matches `editor.content_revision`.
- `reject_proposal(proposal)` drops a proposal without mutation.
- Accepted proposals are pushed as one `ApplyAIOpBatch` undo command.

Stage/preview/validate/apply/mutate:

- Stages: yes, as `LiveOpProposal`.
- Previews: yes, via `preview_summary`.
- Validates: yes, by dry-running supported live ops.
- Applies: yes, but only through `accept_proposal`.
- Mutates: yes, only during accept/apply, not during stage.

Creator Mode fit:

- This is the best core system for Creator Mode to use later.
- It already protects against stale proposals and invalid batches.
- It is live-editor oriented, which matches Creator Mode's frontend workflow.
- It only supports the current live-op vocabulary: `add_entity_from_prefab`, `set_behaviour_params`, and `delete_entity`. Door workflow staging will need an adapter that converts `CreatorDoorWorkflowModel.plan.operations` into supported live ops or explicitly extends the live-op vocabulary in a separate reviewed slice.

### Live session bridge

Path: `engine/editor/live_session_bridge.py`

What it does:

- Owns a loopback JSON bridge for external MCP/chat callers.
- Queues mutation-capable work onto the editor main/update thread.
- Exposes `/live/stage_proposal`, `/live/accept_proposal`, `/live/reject_proposal`, and `/live/read_scene`.
- Stores pending proposals in `_proposals` and returns GUI-safe summaries through `list_pending_proposals()`.
- Provides `stage_pending_proposal(ops)`, `accept_pending_proposal(proposal_id)`, and `reject_pending_proposal(proposal_id)`.

Stage/preview/validate/apply/mutate:

- Stages: yes, via `stage_pending_proposal()` and `/live/stage_proposal`.
- Previews: yes, through proposal `preview_summary` and `dry_run`.
- Validates: yes, by delegating to `EditorModeController.stage_proposal()`.
- Applies: yes, only through explicit accept.
- Mutates: only when accepting.

Creator Mode fit:

- Appropriate if Creator Mode needs to put proposals into the same AI Proposals inbox that the bridge owns.
- Creator Mode runs in-process, so CREATOR-1e should prefer a small adapter that calls the editor/bridge object directly, not HTTP.
- If `editor.live_bridge` is absent, the adapter must fail closed or create/use the bridge only if that is already safe for the current editor lifecycle. It must not start broad new runtime machinery as part of a pure UI click.

### Proposal inbox

Path: `engine/editor/proposal_inbox.py`

What it does:

- Lists proposals from `editor.live_bridge.list_pending_proposals()`.
- Accepts or rejects by forwarding proposal IDs to the live bridge.
- Returns `no_live_session` when no live bridge exists.

Stage/preview/validate/apply/mutate:

- Stages: no.
- Previews: lists staged preview summaries.
- Validates: no direct validation.
- Applies: yes, indirectly through bridge accept.
- Mutates: only when accepting through the bridge.

Creator Mode fit:

- Useful as the review surface once Creator Mode stages proposals.
- Not sufficient by itself because it cannot stage.
- Future Creator Mode should stage through the bridge/controller, then rely on the existing inbox for human review and apply/reject.

### Co-creative chat session tool path

Path: `engine/editor/chat_session_controller.py`

What it does:

- Defines a `stage_proposal` tool for the AI chat loop.
- Uses `ToolExecutor.execute("stage_proposal", payload)` to call `_stage_into_inbox(editor, ops)`.
- `_stage_into_inbox()` uses `editor.live_bridge.stage_pending_proposal()` when available, or creates an `EditorLiveSessionBridge` best-effort.
- Uses the main-thread dispatcher to keep editor work on the editor thread.

Stage/preview/validate/apply/mutate:

- Stages: yes.
- Previews: yes, via the bridge result.
- Validates: yes, via `stage_proposal`.
- Applies: no, the chat tool only stages.
- Mutates: no during stage.

Creator Mode fit:

- This confirms the intended "stage, do not apply" assistant contract.
- Creator Mode should not depend on chat-specific provider/tool-loop code.
- CREATOR-1e may mirror the staging shape but should put reusable adapter logic under `engine/editor/creator_mode/`, not inside chat session code.

### MCP live session client/tools

Paths:

- `engine/mcp_server/live_session_client.py`
- `engine/mcp_server/tools.py`

What they do:

- Provide external process wrappers for live editor operations.
- Verify `.mesh/live_session.json`, loopback host, token, workspace root, and health before forwarding requests.
- Expose `live_stage_proposal`, `live_accept_proposal`, and `live_reject_proposal`.

Stage/preview/validate/apply/mutate:

- Stages: yes, over HTTP to a running editor.
- Previews: yes, through bridge response.
- Validates: yes, by forwarding to the editor bridge.
- Applies: yes, only through explicit accept.
- Mutates: only after accept.

Creator Mode fit:

- Appropriate for external MCP clients, not for in-process Creator Mode UI.
- Creator Mode should not call HTTP or discover `.mesh/live_session.json` from inside the editor when it already has the editor object.

### Editor command dispatch and undo

Paths:

- `engine/editor/editor_command_dispatch_controller.py`
- `engine/editor/editor_undo_controller.py`
- `engine/editor/editor_command_push_model.py`

What they do:

- Apply/revert concrete editor commands for undo/redo.
- Support command types such as `AddEntity`, `ChangeProperty`, `DeleteEntity`, and `ApplyAIOpBatch`.

Stage/preview/validate/apply/mutate:

- Stages: no.
- Previews: no.
- Validates: no proposal validation.
- Applies: yes.
- Mutates: yes.

Creator Mode fit:

- Not a staging bridge.
- Creator Mode must not call command dispatch directly for door workflows.
- It remains the lower-level implementation used after a proposal is accepted by the existing live-op system.

### File-backed AI ops and plan executor

Paths:

- `engine/ai_ops.py`
- `mesh_cli/ai.py`
- `engine/tooling/plan_executor.py`

What they do:

- Read and write project content files.
- Provide CLI plan application, dry-run flags, safe path checks, AI-safe lint/test gates, and validation helpers.

Stage/preview/validate/apply/mutate:

- Stages: no live editor proposal inbox staging.
- Previews: some CLI dry-run/planning support.
- Validates: yes in several CLI flows.
- Applies: yes to files.
- Mutates: yes when not dry-run.

Creator Mode fit:

- Not appropriate for Creator Mode's first in-editor staging path.
- It is file-backed and can write scene JSON, while Creator Mode should work with the live editor review path and avoid direct save/load or JSON writes.

### Scene lint/fix and refactor preview systems

Representative paths:

- `engine/editor/scene_lint_model.py`
- `engine/editor/scene_lint_ops.py`
- `engine/editor/asset_refactor_preview_model.py`
- `engine/editor/asset_refactor_model.py`

What they do:

- Build diagnostics/previews and apply specific fixes/refactors through their own workflows.
- Some paths support preview-like models or undoable fixes.

Stage/preview/validate/apply/mutate:

- Stages: no general live-op proposal staging.
- Previews: yes for their domains.
- Validates: domain-specific.
- Applies/mutates: yes in fix/refactor paths.

Creator Mode fit:

- Useful design references for reviewable UI models.
- Not the proposal bridge for door creation/configuration.

## Recommended Path For Creator Mode

CREATOR-1e should add a pure or near-pure adapter that converts a `CreatorDoorWorkflowModel` into existing live-op proposal operations, without staging or applying by default.

Recommended shape:

1. Add a Creator Mode adapter under `engine/editor/creator_mode/`, for example `creator_door_live_ops.py`.
2. Convert `CreatorDoorWorkflowModel.plan.operations` into a list of existing live ops.
3. Initially support only operations that can be expressed safely using the current live-op vocabulary.
4. Return an explicit blocked result when a door plan cannot be represented without extending live ops.
5. Add tests proving the adapter is deterministic, read-only, and does not import Arcade or editor runtime.

When staging is intentionally added in a later slice, the in-editor path should be:

1. Build `CreatorDoorWorkflowModel`.
2. Convert it to reviewed live ops.
3. Call `editor.live_bridge.stage_pending_proposal(ops)` if the bridge is available, or call `editor.stage_proposal(ops)` and place the resulting proposal into the existing pending proposal flow through the established bridge/inbox contract.
4. Let the existing AI Proposals inbox show the proposal.
5. Keep accept/reject owned by `ProposalInbox` and `EditorLiveSessionBridge`.

Exact existing paths to reuse:

- In-process staging core: `engine.editor_controller.EditorModeController.stage_proposal(ops)`
- Pending inbox bridge: `engine.editor.live_session_bridge.EditorLiveSessionBridge.stage_pending_proposal(ops)`
- Review list: `engine.editor.proposal_inbox.ProposalInbox.list_pending()`
- Human accept: `engine.editor.proposal_inbox.ProposalInbox.accept(proposal_id)`
- Human reject: `engine.editor.proposal_inbox.ProposalInbox.reject(proposal_id)`

Do not use these as the Creator Mode staging path:

- `engine.mcp_server.live_session_client.live_stage_proposal()` from inside the editor.
- `engine.mcp_server.tools.apply_ops()`.
- `engine.ai_ops.AIOps`.
- `engine.tooling.plan_executor.PlanExecutor`.
- `editor.command_dispatch.apply_command()` directly.
- Save/load or direct scene JSON writes.

## Safety Rules For Future Staging

- Creator Mode must not directly mutate scene JSON.
- Creator Mode must not call save/load directly.
- Creator Mode must not bypass validation or dry-run checks.
- Creator Mode must produce a reviewable proposal first.
- Applying must remain a separate explicit human action.
- Creator Mode staging must fail closed if no safe proposal bridge is available.
- Creator Mode must not call command dispatch directly.
- Creator Mode must not accept its own proposals automatically.
- Creator Mode must preserve undo by relying on the existing accepted-proposal batch path.
- Creator Mode must reject stale proposals through the existing revision guard.

## Open Questions

- Door creation is not yet directly covered by the current live-op vocabulary unless it can be represented as `add_entity_from_prefab` plus `set_behaviour_params`.
- If doors require non-prefab entity creation, CREATOR-1e should stop at an adapter result that says the operation is not representable yet, rather than adding mutation.
- If `EditorLiveSessionBridge` is not active in some editor sessions, we need an explicit product decision: fail closed with "proposal bridge unavailable" or initialize the existing bridge through its lifecycle helper.
- The right review surface is probably the existing AI Proposals dock, but manual dogfood is needed once actual staging is implemented.
- The live-op operation schema is AI-named today. A future cleanup may rename labels for Creator Mode while keeping the underlying operation contract unchanged.
