# Co-creative Editor Architecture Scoping

## Goal

Bridge the current AI/file mutation path and human/live-editor mutation path so an AI-issued operation can land on the same live in-editor scene that a human is editing, while human edits are visible back to the AI before disk save.

This is research-only. The recommendation below is based on the current code paths inspected in:

- `engine/ai_ops.py`
- `engine/mcp_server/tools.py`
- `engine/editor_controller.py`
- `engine/editor/editor_command_dispatch_controller.py`
- `engine/editor/editor_undo_controller.py`
- `engine/editor/editor_entity_ops_controller.py`
- `engine/editor/editor_duplicate_controller.py`
- `engine/editor/editor_tile_controller.py`
- `engine/editor/editor_lights_controller.py`
- `engine/editor/editor_dialogue_controller.py`
- `engine/editor/editor_database_form_controller.py`
- `engine/editor/editor_quest_editor_controller.py`
- `engine/scene_lifecycle_controller.py`
- `engine/scene_runtime/persistence.py`
- `engine/scene_controller_core.py`
- `engine/scene_controller_parts/authoring.py`
- `engine/scene_controller_parts/tilemap_state.py`
- `engine/editor_runtime/ops.py`
- `engine/console_runtime/handlers_entity.py`

## Two-surface Map

### AI/MCP mutation surface

`engine/mcp_server/tools.py` exposes the AI read/write surface. `apply_ops()` creates `AIOps(base_dir=root)` and calls `AIOps.apply_job({"operations": ...})`, then optionally calls `run_validation(validate_scene_path)`. `list_op_types()` returns `OP_CATALOG`, which mirrors `AIOps.apply_job`.

Current full `apply_job` operation set:

- `create_scene`
- `add_entity_from_prefab`
- `delete_entity`
- `set_behaviour_params`
- `edit_dialogue`
- `edit_quest`
- `add_quest_definition`
- `update_quest_definition`
- `delete_quest_definition`
- `paint_tiles`
- `add_light`
- `update_light`
- `delete_light`
- `run_validation`
- `add_world_scene`
- `link_world_scenes`
- `set_world_start`
- `add_cutscene`
- `update_cutscene`
- `delete_cutscene`
- `insert_cutscene_step`
- `update_cutscene_step`
- `delete_cutscene_step`

`AIOps.apply_job()` is a per-op dispatch loop. Each scene op loads the scene from disk through `_load_scene(scene_path)`, mutates the parsed dict, and persists immediately through `_save_scene(scene_file, scene)`. `_save_scene()` compacts via `scene_serializer.compact_scene_payload()` and writes atomically. World, quest, and cutscene ops similarly load/write JSON files. `run_validation(scene_path)` constructs a `SceneLoader` and validates a scene file path; if no scene path is supplied, it returns a skipped validation success.

The scene-only op bodies are mostly dict transformations, so the logic is not conceptually hard-wired to disk. The hard-wiring is in their boundaries: each method resolves a path, loads a file, mutates, and saves. `paint_tiles()` also reads a referenced tilemap file to infer dimensions. `add_entity_from_prefab()` reads prefab palettes. `run_validation()` validates files, not a live dict. Therefore an in-memory target mode is possible with moderate extraction, but not a one-line parameter change.

### Human/editor mutation surface

There is not one common human mutation core. There is one common undo dispatch mechanism, but many ad-hoc mutation producers.

Common undo/redo pieces:

- `EditorModeController._push_command()` backfills labels, delegates to `EditorUndoController.push()`, clears redo, and marks dirty.
- `EditorUndoController.undo()` and `redo()` pop/push command dicts and call `EditorModeController._revert_command()` / `_apply_command()`.
- `EditorCommandDispatchController` is the central undo/redo dispatcher for many command types, including `MoveEntity`, `AddEntity`, `DeleteEntity`, `ChangeProperty`, `EditDialogue`, `PaintTile`, `AddLight`, `EditLight`, `DeleteLight`, `EditOccluder`, `AltDragDuplicate`, `AlignEntities`, and `EditBackgroundPlanes`.

Human mutation producers are distributed:

- Entity move/nudge uses `SceneController._apply_entity_mutation()` and pushes `MoveEntity`.
- Entity create/delete uses `EditorEntityOpsController.create_entity_internal()` / `delete_entity_internal()` and pushes `AddEntity` / `DeleteEntity` from call sites.
- Inspector/component edits update `SceneController._loaded_scene_data`, sync runtime sprite state, mark dirty, and in some cases push command entries.
- Dialogue edits use `EditorDialogueController.apply_dialogue_edit()`, update behaviour config through `_update_param_internal()`, and push `EditDialogue`.
- Tile painting uses `EditorTileController.paint_tile_at()`, calls `SceneController.set_tile()` on the runtime tilemap, and pushes `PaintTile`.
- Light edits use `EditorLightsController`, mutate `scene_controller._loaded_scene_data["lights"]`, sync the lighting runtime, and push light command dicts.
- Quest editor extends `EditorDatabaseFormController`; it edits an overlay buffer and saves `assets/data/quests.json` directly through `quest_editor_model.save_quests()`. It is a file-backed database form, not a live-scene mutation path.
- Duplicate, clipboard, align, shape, prefab override, background plane, HD-2D, scene lint, and problem-fix flows add more mutation producers. Some replace `sc._loaded_scene_data` with a new dict, some mutate it in place, and some also rebuild runtime caches.

Human save path:

- `engine/editor_runtime/ops.py:save_current_scene()` calls `controller.window.scene_controller.build_scene_snapshot()` and writes the returned JSON to `current_scene_path`.
- `build_scene_snapshot()` starts from `controller._loaded_scene_data`, updates settings/state, rebuilds `entities` from current sprites, copies tilemap layer data into `tilemap.overrides.layers`, applies scene defaults, and optionally compacts.

This means save is not a raw write of `_loaded_scene_data`. It reconciles sprite runtime state and tilemap runtime state back into the JSON shape.

### Third mutation path found

There is a third live mutation surface in console/debug authoring:

- `engine/console_runtime/handlers_entity.py` can spawn entities and call `SceneController._apply_entity_mutation()` directly.
- `engine/console_runtime/handlers_scene.py` can save snapshots.
- `engine/scene_controller_parts/authoring.py` exposes debug authoring proxies such as `debug_add_entity_payload()`, `debug_remove_entity_by_id()`, `debug_move_entity_by_id()`, duplicate/copy/paste, behaviour/tag/name edits, and macro preview/build helpers.

This does not replace the editor path, but it is important because it proves the live `SceneController` already has non-editor authoring APIs. The bridge should not ignore these or create a fourth independent mutation model.

## Representation Findings

The live scene anchor is `SceneController._loaded_scene_data`. `scene_lifecycle_controller.load_scene()` loads JSON through `SceneLoader`, assigns `current_scene_path`, assigns `_loaded_scene_data`, keeps `_loaded_scene_source_data`, parses background layers/planes, applies settings, configures lighting, loads tilemaps, and creates sprites from `scene["entities"]`.

The on-disk JSON and live scene share the same broad dict shape. The strongest read-back API today is `SceneController.build_scene_snapshot(compact=False)`, implemented in `engine/scene_runtime/persistence.py`. It produces the same scene-payload shape used by AI tools by reconciling:

- loaded scene metadata from `_loaded_scene_data`
- current camera/game state
- entity transforms and runtime entity data from sprites
- tilemap runtime layer data into `tilemap.overrides.layers`
- loader defaults through `SceneLoader.apply_scene_defaults()`
- optional compaction through `compact_scene_payload()`

Therefore live read-back should use `build_scene_snapshot(compact=False)` for AI context, not direct `_loaded_scene_data`, because direct `_loaded_scene_data` can be stale for sprite transforms and tile painting.

## Architecture Decision

Choose option (ii): the editor exposes a live op-apply endpoint, and AI operations route through it when an editor session is active.

The endpoint should be editor-owned, not file-owned:

```text
MCP/app prompt
  -> AI proposal service
  -> editor live op endpoint
  -> preview/staging
  -> accept
  -> one editor undo command
  -> SceneController live scene + GUI refresh
```

The first version should support a narrow live scene-op subset, then grow:

- slice 1: `add_entity_from_prefab` to current scene
- next: `delete_entity`, `set_behaviour_params` / `edit_dialogue`, `add_light` / `update_light` / `delete_light`
- then: `paint_tiles`
- later: multi-file ops such as quests, worlds, and cutscenes with separate database/file staging

Rationale:

- Co-creation requires AI changes to appear in the existing GUI session without reload and without racing unsaved human changes on disk.
- The editor already owns runtime synchronization concerns: sprite creation/removal, selection, inspector/hierarchy refresh, tilemap invalidation, lighting sync, dirty state, and undo history.
- The editor undo stack is the user-facing history. AI accept must produce an undoable editor command, not an invisible disk patch.
- `build_scene_snapshot()` already gives AI read-back of unsaved human edits in the correct scene JSON shape.

### Rejected alternative: AIOps gains live/in-memory mode

This is tempting because the scene op bodies are mostly dict transforms. It is rejected as the primary bridge because it would still bypass editor runtime concerns. A dict-only `AIOps` mutation would need an additional adapter to create/remove sprites, refresh caches, sync lighting/tilemap state, update panels, mark dirty, and push undo. That adapter would end up recreating editor logic outside the editor.

This option remains useful internally for pure transformation helpers. Extract small shared functions from `AIOps` only when they are genuinely pure and can be called by the editor endpoint.

### Rejected alternative: extract a shared op-applier core first

A shared core is the right long-term shape for pure scene-dict transforms, but extracting it first is too broad. Current editor mutation producers are not all dict-only, and current AI ops include scene, world, quest, and cutscene files. A large shared applier would either ignore runtime/undo details or become an editor-shaped service anyway.

Do not start by extracting a universal core. Start with an editor live endpoint, then extract shared pure helpers behind it as duplication becomes real.

### Rejected alternative: disk write then reload editor

This would be the smallest code movement, but it does not satisfy co-creation. It overwrites or races unsaved human edits, destroys live selection/context, and makes AI changes visible only after a reload. It preserves the file/memory wall instead of removing it.

## Live Read-back Design

Add an AI-visible live scene read endpoint in the editor session:

- `read_live_scene(compact=False)` returns `scene_controller.build_scene_snapshot(compact=compact)`.
- Include metadata: `current_scene_path`, dirty flag, editor revision, undo revision, and selected entity ids.
- Existing MCP `read_scene()` can remain file-backed. The co-creative surface should either add a separate `read_live_scene` tool/resource or route `read_scene(current_scene_path, live=True)` to the active editor session.

Track an editor content revision:

- Increment on every `_push_command()` and on dirty mutations that currently call only `_mark_dirty()`.
- Stamp AI proposals with the live revision they were generated against.
- On accept, compare proposal base revision to current revision.

Use `build_scene_snapshot()`, not `_loaded_scene_data`, because it is the only current serializer that reconciles sprite state, tilemap runtime data, and scene defaults into the AI-readable payload shape.

## In-editor AI Surface and Staging UX

Place the first AI prompt input as a dock tab or bottom panel in the editor shell, not as an external-only console. The editor already has dock concepts such as History, Inspector, and database forms; an `AI` dock keeps the human in the same GUI session.

Minimal UX model:

1. Human enters prompt in the AI dock.
2. AI receives `read_live_scene()` plus current selection/context.
3. AI returns an op batch proposal, not an immediate commit.
4. Editor validates the proposal against the live op endpoint in dry-run mode.
5. Preview shows a compact change list and optionally highlights affected entities/lights/tiles.
6. Human accepts or rejects.
7. Accept applies the whole batch as one undoable editor command. Reject drops it with no dirty change.

Staging should store:

- proposed operations
- base live revision
- preview summary
- dry-run result / validation warnings
- affected ids for preview highlighting

For slice 1, preview can be text-only: "Add prefab X at (x, y)" plus affected new entity name. Later slices can add visual ghost sprites and diff views.

## Undo/redo and Conflict Policy

Accepted AI batches must land on the editor undo stack as one command, labelled clearly, for example `AI: Add guard patrol`. Undo should revert the entire accepted batch. Redo should reapply it.

Implementation detail for early slices:

- Use editor-native command dicts where they already exist (`AddEntity`, `DeleteEntity`, `ChangeProperty`, `EditDialogue`, `PaintTile`, `AddLight`, `EditLight`, `DeleteLight`).
- For multi-op batches, add a composite command type such as `ApplyAIOpBatch` only if needed; it can contain ordered child editor commands and the dispatch controller can apply/revert them in forward/reverse order.
- Do not push one undo entry per low-level op for accepted AI batches; that makes a single AI proposal hard to undo.

Conflict rule:

- If the human edits after proposal generation, the proposal's base revision no longer matches current revision.
- Slice 1 should block accept and ask the AI to regenerate against current live state.
- Later slices can rebase non-overlapping ops by checking touched ids/paths, but default should be conservative.

Validation:

- File validation currently validates paths. Live validation should initially validate a temporary snapshot built from `build_scene_snapshot()` without saving over the scene.
- For slice 1, validation can be limited to "op can resolve prefab, target scene is current scene, generated entity id/name is unique, sprite creation succeeds."

## Sliced Implementation Plan

### Slice 1: live AI add-entity proof

Smallest independently shippable proof that an AI-issued op lands on the live in-editor scene and is visible in the GUI.

Scope:

- Add an editor-session live op endpoint for a single op: `add_entity_from_prefab`.
- Input matches the existing AI op fields, except `scene_path` must equal the current live scene or be omitted to mean current scene.
- Resolve prefab using the same palette logic as `AIOps.add_entity_from_prefab()` or a small extracted helper.
- Build the entity dict, ensure unique name/id, call `EditorModeController._create_entity_internal()`, add it to the appropriate layer, update `scene_controller._loaded_scene_data["entities"]`, mark dirty, refresh hierarchy/inspector as needed, and push one `AddEntity` undo command.
- Expose a minimal in-editor trigger path. This can be a temporary AI dock button or command palette action that applies a hard-coded/provided op batch through the endpoint.

Test:

- Controller-level test with an editor/window stub: applying the live op increases live sprite count, appends to `_loaded_scene_data["entities"]`, marks dirty, and pushes `AddEntity`.
- Integration-style test: accepted op is visible through `build_scene_snapshot()` before saving.
- Undo test: undo removes the sprite and snapshot entity.

### Slice 2: live read-back endpoint

Scope:

- Add `read_live_scene(compact=False)` using `SceneController.build_scene_snapshot()`.
- Return current scene path, dirty flag, content revision, selection context, and scene payload.
- Add a test that unsaved human movement/tile changes appear in read-back.

Test:

- Move an entity through the editor path without saving; `read_live_scene()` returns the new coordinates.
- Paint a tile without saving; `read_live_scene()` includes `tilemap.overrides.layers`.

### Slice 3: proposal staging and revision conflicts

Scope:

- Add proposal objects containing ops, base revision, preview summary, and dry-run status.
- Add accept/reject flow.
- On accept, reject stale proposals when current revision differs from base revision.

Test:

- Proposal generated at revision N accepts at N.
- Human edit bumps to N+1; same proposal is blocked.
- Reject does not mark dirty or push undo.

### Slice 4: live entity and dialogue edits

Scope:

- Support `delete_entity`, `set_behaviour_params`, and `edit_dialogue` through editor-native mutation paths.
- Use existing `DeleteEntity`, `ChangeProperty`, and `EditDialogue` command forms where possible.
- Refresh inspector/hierarchy/dialogue cache when touched entity is selected.

Test:

- AI edit updates selected entity's behaviour config live and appears in inspector/read-back.
- Undo restores previous config.

### Slice 5: live lights

Scope:

- Support `add_light`, `update_light`, and `delete_light` through `EditorLightsController`.
- Reuse `ensure_scene_lights()`, `add_light()`, `update_light_property()`, and existing light undo command shapes.
- Always call lighting runtime sync after apply/undo/redo.

Test:

- AI-added light appears in overlay/runtime lighting config.
- Undo removes it and redo restores it.

### Slice 6: live tile painting

Scope:

- Support `paint_tiles` against `SceneController.set_tile()`.
- Batch many tile edits into one AI undo command or one composite command containing child `PaintTile` commands.
- Refresh tilemap batches/invalidation through existing `set_tile()` behavior.

Test:

- AI tile batch changes runtime tilemap, read-back includes overrides, and one undo reverts the batch.

### Slice 7: MCP/session routing

Scope:

- Add a co-creative MCP/app route that targets the active editor session when present.
- Keep existing file-backed `apply_ops()` for headless/batch workflows.
- Add clear routing metadata so AI knows whether it is using `live_editor` or `file_workspace`.

Test:

- With no editor session, existing `apply_ops()` remains file-backed.
- With active editor session, live route changes GUI and does not write scene file until human saves.

### Slice 8: multi-file content staging

Scope:

- Bring quests, worlds, and cutscenes into the same proposal UX but treat them as database/file changes rather than live scene changes.
- Quest editor already saves `assets/data/quests.json` through a database form; align AI quest proposals with that form's validation and save model.
- World/cutscene ops should stage file diffs and require explicit accept.

Test:

- AI quest proposal previews a file/database diff and does not silently modify disk.
- Accept writes through existing model save helpers where available.

### Slice 9: shared pure helpers

Scope:

- Extract pure helpers from `AIOps` only where both file-backed and live-backed paths now duplicate logic: prefab resolution, unique entity naming, behaviour config deep merge, light normalization, tile op normalization.
- Keep orchestration separate: file-backed `AIOps` writes files; editor live endpoint syncs runtime/undo.

Test:

- Existing AI op tests still pass.
- Live endpoint tests still pass.
- Drift test confirms op schemas remain shared or intentionally diverged.

## Final Recommendation

Build the co-creative bridge as an editor-owned live op endpoint with staged accept/reject. Use `SceneController.build_scene_snapshot()` for AI read-back. Keep existing `AIOps` as the file/headless path, and extract pure helpers only after the first live slices prove the shape.

The north-star invariant should be: once an editor session is active, AI accepted scene ops mutate the same live `SceneController` state and the same editor undo history as human edits; disk changes happen only through the editor save path.
