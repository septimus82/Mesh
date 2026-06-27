# Native Co-creative Chatbox Architecture

## Goal

Add a native in-editor Claude chatbox so a human can type in the editor, Claude can inspect the live scene, and Claude can stage proposals into the existing AI Proposals inbox. This removes the external MCP-client setup from the co-creative loop while preserving the same human approval gate.

This is research-only. The recommendation below is based on current code inspected in:

- `pyproject.toml`
- `engine/editor_controller.py`
- `engine/editor/editor_live_ops_controller.py`
- `engine/editor/live_session_bridge.py`
- `engine/editor/proposal_inbox.py`
- `engine/ui_overlays/proposal_inbox_overlay.py`
- `engine/editor/dock_tab_registry.py`
- `engine/game_parts/ui_dispatcher.py`
- `engine/editor_runtime/editor_input_click_handlers.py`
- `tests/test_cocreative_proposal_inbox.py`
- `tests/test_cocreative_live_bridge.py`
- `docs/design/cocreative_editor_arc.md`

The requested `claude-api` skill is not available in this Codex session, so SDK facts were verified against official Anthropic docs instead:

- Python SDK: https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python
- Tool use: https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
- Define tools: https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools
- Adaptive thinking: https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking
- Models overview: https://platform.claude.com/docs/en/about-claude/models/overview

## Current State

North star #2 already exists through the loopback/MCP route:

```text
external AI client
  -> stdio MCP server
  -> loopback live bridge
  -> EditorModeController.read_live_scene / stage_proposal / accept_proposal / reject_proposal
  -> ProposalInbox + AI Proposals dock
```

The live machine inside the editor is the important reusable asset:

- `EditorModeController.read_live_scene(compact=False)` returns the live `SceneController.build_scene_snapshot()` plus current scene path, dirty state, content revision, and selected entity ids.
- `EditorModeController.stage_proposal(ops)` validates an AI op batch without mutating the scene.
- `EditorModeController.accept_proposal(proposal)` applies a valid, non-stale batch as one `ApplyAIOpBatch` undo command.
- `EditorModeController.reject_proposal(proposal)` drops a proposal without mutation.
- `EditorLiveSessionBridge` stores durable proposals by `proposal_id` and exposes `list_pending_proposals()`, `accept_pending_proposal()`, and `reject_pending_proposal()`.
- `ProposalInbox` reads that same bridge proposal store. The AI Proposals dock is already the human approval surface.

The chatbox must not create a second proposal store or second mutation path. It should reuse the same editor methods and, if a live bridge exists, the same bridge proposal store so the existing inbox sees proposals immediately.

## SDK Facts Verified

The official Anthropic Python SDK is the right dependency:

- Package install is `pip install anthropic`.
- `from anthropic import Anthropic`; `Anthropic()` uses `ANTHROPIC_API_KEY` by default when no explicit key is supplied.
- `client.messages.create(...)` and `client.messages.stream(...)` support model `claude-opus-4-8`.
- Streaming helpers support `with client.messages.stream(...) as stream:` and `.get_final_message()`.
- Tool use is supported through `tools=[...]`; client tools run in the application. Claude returns `stop_reason == "tool_use"` and `tool_use` content blocks, the application executes them, and then sends `tool_result` blocks in a follow-up user message.
- The SDK also has beta tool helpers / `tool_runner`, but those automatically call Python functions and send results on each iteration.
- Adaptive thinking for `claude-opus-4-8` must be explicit with `thinking={"type": "adaptive"}`. Manual `thinking={"type": "enabled", "budget_tokens": ...}` is rejected for Opus 4.8.
- SDK errors include `APIConnectionError`, `RateLimitError`, and `APIStatusError` subclasses.

Add `anthropic` as a new optional dependency, mirroring the existing `mcp` extra:

```toml
[project.optional-dependencies]
chat = [
    "anthropic>=0.112,<1",
]
```

The exact lower bound can be adjusted during implementation, but pinning the range below `1` keeps the repo insulated from a future major SDK break. Engine import must stay gate-safe when the extra is absent.

## Architecture Decision

Choose an editor-hosted Claude API agentic loop with manual client-tool dispatch.

```text
AI Chat dock
  -> ChatSessionController.submit(prompt)
  -> worker thread
  -> Anthropic client.messages.stream(...)
  -> manual tool loop
  -> editor-main-thread tool dispatcher
  -> read_live_scene / stage_proposal
  -> existing ProposalInbox / AI Proposals dock
```

This is Claude API + client tool use, not Managed Agents and not MCP:

- The editor process owns the compute, conversation state, tool definitions, and tool execution.
- Anthropic hosts only the model inference.
- Mesh owns the live editor tools.

### Why Manual Tool Loop

Use manual tool dispatch instead of the SDK `tool_runner`.

Rationale:

- Mesh must marshal every live-editor tool onto the Arcade/editor main thread. An automatic function runner would hide the exact point where a tool is invoked, making it easier to accidentally touch `SceneController`, sprites, or GL state from the worker thread.
- The chat panel needs streamed UI updates. Manual streaming lets the worker thread enqueue token deltas, tool status updates, and final messages to the main thread in a predictable order.
- Tests need a small seam: inject a fake client that returns canned messages with `tool_use` blocks, then assert Mesh dispatches `read_live_scene` and `stage_proposal`.
- Manual dispatch keeps the surface explicit. Only the whitelisted Mesh tools run; there is no reflection-based auto-registration.

Rejected: SDK `tool_runner`. It is useful for pure Python functions, and Anthropic documents that it can automatically call tools and continue iterations. That is the wrong default here because Mesh tools are editor-thread-affine and the proposal store is tied to live editor state.

Rejected: Managed Agents. Managed Agents would move runtime orchestration and tool execution outside the editor process. That does not fit the requirement that tools wrap existing live editor methods and preserve the same in-editor proposal/undo path.

Rejected: embedding the existing MCP server inside the editor. MCP remains valuable for external clients, but the native chatbox should call the editor methods directly through a main-thread dispatcher. Re-entering stdio/HTTP MCP from inside the same process adds protocol overhead without adding safety.

## Tool Surface

Expose only read/stage tools in the first chat arc. The AI must not auto-accept.

### Required Tools

`read_live_scene`

- Input: `{ "compact": boolean }`, default `false`.
- Runs on editor main thread.
- Calls `editor.read_live_scene(compact=compact)`.
- Returns the live snapshot and metadata. This is the authoritative read-back for unsaved human edits.

`stage_proposal`

- Input: `{ "ops": [ ... ] }`.
- Runs on editor main thread.
- Calls the same staging path used by the live bridge.
- Stores the proposal where `ProposalInbox.list_pending()` can see it.
- Returns `{ ok, proposal_id, preview_summary, dry_run }`.
- Never calls `accept_proposal()`.

Implementation detail: if `editor.live_bridge` exists, prefer a public bridge method such as `stage_pending_proposal(ops)` so proposals land in the existing bridge `_proposals` store that the inbox already reads. If no bridge exists in native-only mode, slice 14a should either start the same live bridge without exposing network discovery or extract the proposal-store part into an editor-owned `ProposalStore` used by both bridge and chat. Do not add a second independent pending-list model.

### Grounding Tools

`list_prefabs`

- Input: optional `query`, optional `limit`.
- Runs on main thread or on a pure snapshot of `editor.prefab_palette`.
- Returns prefab ids, display names, behaviour names, and any short tags available.
- Purpose: reduce invalid `add_entity_from_prefab` proposals.

`list_entities`

- Input: optional `query`, optional `selected_only`.
- Runs on main thread using `read_live_scene(compact=True)` or the current snapshot.
- Returns entity ids/names, prefab ids, behaviours, and positions.
- Purpose: help `set_behaviour_params` and `delete_entity` target valid entities without forcing Claude to scan a huge full scene each time.

These grounding tools are not substitutes for validation. `stage_proposal()` remains the authority.

### Out of Scope for First Slices

- `accept_proposal` as a Claude tool.
- `reject_proposal` as a Claude tool.
- Raw `apply_live_op`.
- File-backed `apply_ops`.
- Arbitrary filesystem reads.
- Shell commands.

The human approval invariant is: Claude can stage, the human accepts/rejects in the existing inbox.

## System Prompt Draft

```text
You are Mesh's in-editor co-creative scene assistant. You collaborate with the human on the live scene currently open in the editor.

Use tools to inspect the live editor state before proposing scene changes. The live scene may contain unsaved human edits, so do not rely on files or prior memory when a tool can read current state.

You may stage proposals by calling stage_proposal with supported live ops. Staging does not apply changes; it creates a proposal for the human to review in the AI Proposals dock. Never auto-accept, never ask for or call an accept tool, and never imply a change has been applied until the human accepts it.

Prefer small, reviewable batches. When adding an entity, use a valid prefab id. When editing behaviour params or deleting an entity, target a valid live entity id or name. If you are unsure which prefab/entity to use, ask a concise clarifying question or call list_prefabs/list_entities.

After staging, summarize what is waiting for review and mention that the human can accept or reject it in the AI Proposals dock. If staging validation fails, explain the validation warning and suggest a corrected next step.
```

## Agentic Loop

State:

- Chat transcript: user messages, assistant text, tool-use/result blocks needed for the Anthropic conversation.
- UI transcript: renderable messages, partial streaming assistant text, tool status rows.
- Config: model id default `claude-opus-4-8`, max tokens, adaptive thinking enabled, optional effort.
- Cancellation flag for the active run.

Loop:

1. Main thread receives chat input and appends a user message.
2. Main thread starts a worker thread for the run, unless one is already active.
3. Worker builds request with:
   - `model=config.model_id`
   - `thinking={"type": "adaptive"}`
   - `tools=[read_live_scene, stage_proposal, list_prefabs, list_entities]`
   - `messages=conversation`
   - system prompt above
4. Worker calls `client.messages.stream(...)`.
5. For stream text deltas, worker enqueues UI updates to the main thread. If thinking deltas are emitted, do not display raw hidden reasoning by default; optionally show a neutral "Thinking..." status.
6. Worker calls `stream.get_final_message()` and appends the final assistant message to conversation.
7. If final message contains `tool_use` blocks:
   - For each supported tool call, worker asks the editor main-thread dispatcher to execute it and blocks for the result.
   - Worker appends a user message containing `tool_result` blocks.
   - Continue the loop.
8. If no tool calls remain, mark run complete and leave any staged proposals in the existing inbox.

Do not log prompts, API keys, full scene snapshots, or tool arguments at info level. Debug logging may report coarse state such as "chat run started" and "tool stage_proposal returned ok=True proposal_id=...".

## Threading Design

The editor main thread owns all `SceneController`, sprite, GL, dock, and proposal-store mutation.

The worker thread owns:

- Anthropic network I/O.
- Anthropic message assembly.
- Tool-loop control flow.
- Waiting on main-thread tool results.

Main-thread dispatcher:

- Reuse the live-bridge enqueue/drain pattern conceptually.
- Prefer extracting a small editor-local `EditorMainThreadDispatcher` rather than importing the HTTP bridge's private `_QueuedWork`.
- API shape:
  - `call_sync(func, timeout=5.0) -> result`: worker enqueues callable, blocks on event, main thread drains and executes.
  - `post(func)`: worker enqueues UI update, returns immediately.
  - `drain(limit=...)`: called from the editor tick/draw path, the same place `drain_live_bridge()` is already called in `EditorOverlayController.draw_overlay()`.
- Tool execution uses `call_sync`.
- Streaming token updates use `post`.

This preserves the existing no-off-thread-editor-mutation rule established by the live bridge.

Failure policy:

- If the dispatcher times out, return a tool error result to Claude and show a panel error.
- If the worker crashes, catch at the worker boundary and enqueue a visible error message.
- If the user closes editor mode, cancel the run and drain/drop queued work safely.

## Chat Dock / Panel UI

Add a new right dock tab, likely `AI Chat`, next to `AI Proposals`.

UI model:

- `ChatMessage(role, text, status, timestamp, tool_name=None, proposal_id=None)`
- `ChatSessionState(messages, current_input, is_running, error, scroll_offset)`
- `ChatSessionController.submit(text)`, `cancel()`, `append_stream_delta()`, `append_tool_status()`

Overlay:

- Mirror `ProposalInboxOverlay` and other right-dock overlays:
  - self-gate on `right_tab == "AI Chat"`
  - use `EDITOR_THEME` tokens
  - draw a scrollable message transcript
  - draw a multiline-ish input area at bottom
  - draw send/cancel buttons
  - route mouse clicks through editor input router, like the AI Proposals fix
  - route text input and key events through existing editor input service patterns

Input ergonomics:

- Enter sends when the input is focused.
- Shift+Enter inserts newline if multiline input is implemented; otherwise slice 14a can be single-line.
- Escape clears focus or cancels an active run.
- Disabled send button while a run is active.

The chat dock should not replace the AI Proposals dock. It creates proposals; the inbox remains the approval gate.

## Key Handling and Secrets

Primary key source:

- `ANTHROPIC_API_KEY`, resolved by `Anthropic()` or explicit `os.environ` fallback.

Optional future UI field:

- A settings field may exist, but it must be user-local only.
- Do not write the key into scenes, workspace files under source control, committed config, logs, crash reports, or proposal payloads.
- If a key is entered in-app, store only in process memory for slice 14, or in an ignored local secret store only after a separate security review.

Missing key behavior:

- Chat dock shows "Claude API key missing. Set ANTHROPIC_API_KEY and restart/retry."
- Send is disabled or sends a local error without starting a worker.
- Engine imports remain clean.

Missing dependency behavior:

- Anthropic import must be guarded:
  - `try: from anthropic import Anthropic`
  - on `ImportError`, mark provider unavailable.
- Chat dock shows "Claude chat requires the optional chat extra: pip install -e .[chat]".
- No import-time failure in headless tests or normal editor startup.

API failures:

- `RateLimitError`: show rate-limit message and leave the transcript intact.
- `AuthenticationError` / 401: show key/auth message without echoing key.
- `APIConnectionError`: show connectivity message.
- `APIStatusError`: show generic provider status code and request id if available, but not prompt/scene content.
- Refusal or tool validation failure: show the assistant text and/or staging warnings. Do not mutate state.

## Testability

The agentic loop must be testable without real API calls.

Required seams:

- `AnthropicClientFactory`: creates the real client in app, returns a fake client in tests.
- `ClaudeMessageAdapter`: normalizes SDK content blocks into small internal dicts/dataclasses, so tests do not need real SDK model classes.
- `EditorMainThreadDispatcher`: can be drained explicitly in tests.
- `ToolExecutor`: maps tool names to editor methods and can be called directly.

Headless test for slice 14a:

1. Build the same fake editor/window controller used by `tests/test_cocreative_live_ops.py`.
2. Ensure a proposal store exists through the same path `ProposalInbox` reads.
3. Inject fake Anthropic client:
   - first streamed/final message contains a `tool_use` block for `read_live_scene`
   - second streamed/final message contains a `tool_use` block for `stage_proposal` with a valid `add_entity_from_prefab` op
   - final response says proposal staged
4. Submit chat prompt.
5. Drain worker/main-thread queues until complete.
6. Assert:
   - `read_live_scene` was called on main thread
   - `stage_proposal` was called on main thread
   - no entity was applied yet
   - `ProposalInbox.list_pending()` contains one proposal
   - AI Proposals dock would see the same proposal id

Additional contract tests:

- Missing `anthropic` import does not break `import engine.editor_controller`.
- Missing key surfaces a panel error and starts no worker.
- API exception surfaces an error and leaves pending proposals unchanged.
- Worker thread never directly calls editor tool functions; it uses dispatcher.
- Staging invalid ops returns tool error/result but does not mutate.

## Sliced Implementation Plan

### Slice 14a: Stubbed loop stages one proposal

Smallest proof: chat input -> Claude tool loop -> `stage_proposal` -> proposal appears in existing inbox, with no real API in tests.

Scope:

- Add optional `[chat]` dependency entry and guarded Anthropic provider module.
- Add `EditorMainThreadDispatcher` or equivalent queue.
- Add `ChatSessionController` with injectable client factory and manual tool loop.
- Add only two tools: `read_live_scene` and `stage_proposal`.
- Add a minimal non-pixel UI hook or controller method for submitting text; real dock rendering can be skeletal if needed.
- Store proposals in the existing inbox-visible proposal store. Do not auto-accept.

Tests:

- Fake Anthropic client returns canned `tool_use` blocks.
- Run chat loop headless; assert one pending proposal, no mutation, no undo entry.
- Assert missing dependency/key failure is visible and non-crashing.

### Slice 14b: AI Chat dock shell

Scope:

- Register `AI Chat` right-dock tab.
- Add overlay with message transcript, input row, Send/Cancel buttons.
- Add mouse/text/key routing through editor input router.
- Use editor theme tokens.

Tests:

- Dock tab registration/toggle contract.
- Input focus receives text and Enter triggers `ChatSessionController.submit`.
- Active run disables Send and Cancel calls controller cancellation.

### Slice 14c: Streaming UI and cancellation

Scope:

- Stream text deltas from worker thread to main-thread chat state.
- Show tool status rows such as "Reading live scene" and "Staged proposal".
- Add cancellation flag; stop appending new deltas after cancel.

Tests:

- Fake streaming client emits deltas; panel state updates only via main-thread dispatcher.
- Cancel before final message leaves no proposal unless stage tool already completed.

### Slice 14d: Grounding tools

Scope:

- Add `list_prefabs` and `list_entities`.
- Keep `stage_proposal` validation authoritative.
- Update system prompt/tool descriptions.

Tests:

- Fake client calls list tools before staging.
- `list_prefabs` returns prefab ids used by the fake proposal.
- Selected entity context appears in `list_entities(selected_only=True)`.

### Slice 14e: Error and settings polish

Scope:

- Better missing-key/missing-extra messages.
- Optional model/effort local setting, defaulting to `claude-opus-4-8` and adaptive thinking.
- Rate-limit/auth/connectivity UI states.
- Redact provider errors before display/logging.

Tests:

- Simulated SDK exceptions map to stable user-facing statuses.
- Model id setting is local and does not write secrets.

### Slice 14f: Dogfood hardening

Scope:

- Timeouts and max tool-iteration limits.
- Transcript compaction/summarization if needed.
- Guard huge scene snapshots by using compact read or grounding tools first.
- UX affordance linking a staged chat response to the AI Proposals dock.

Tests:

- Tool loop stops at max iterations.
- Huge fake snapshot is summarized or rejected gracefully.
- Stale proposal after human edit remains handled by existing accept path.

## Final Recommendation

Build the native chatbox as an editor-hosted Claude API client with manual tool dispatch. Keep the AI's write capability limited to staging proposals through the existing co-creative live methods. Run Anthropic I/O and tool-loop logic on a worker thread, and marshal every editor tool and every chat-state mutation back to the editor main thread. Add `anthropic` only as an optional `[chat]` extra and keep engine imports safe when it is absent.

The invariant for this arc is: native Claude chat may propose, but only the existing AI Proposals inbox and human accept/reject flow can commit live scene changes.
