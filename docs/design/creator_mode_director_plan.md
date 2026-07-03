# Creator Mode Director Plan

## Goal

Creator Mode is a friendly, task-based creator shell over the existing Mesh editor/runtime. It should make Mesh feel approachable for RPG Maker-style creation without replacing Advanced Mode, weakening the engine, or bypassing the editor's existing safety systems.

CREATOR-0 is a frontend-only slice: **Friendly Creator Mode Shell**. It introduces a creator-facing layer that reads current editor state, explains it in user terms, and leaves all mutation paths disabled.

## Non-goals

- No editor rewrite.
- No GameWindow refactor.
- No scene schema changes.
- No monster battle changes.
- No save/load changes.
- No broad UI overhaul.
- No direct JSON hacking from the overlay.
- No mutation in the CREATOR-0 read-only slice.

## Design Principle

Creator Mode should speak in user terms:

- Map
- Person
- Door
- Monster Area
- Battle
- Quest
- Item
- Light
- Test Play
- Fix Problems

Creator Mode should hide engine terms by default:

- Entity
- Behaviour
- TriggerZone
- SceneExit
- behaviour_config
- prefab_id
- render_layer
- depth_z

Advanced Mode keeps the exact technical controls. Creator Mode translates common authoring intent into friendly language and, later, safe staged proposals.

## Editor Key Bindings (current)

These are the current in-editor toggles documented for Creator Mode dogfood and agent tasks:

| Key | Action |
|-----|--------|
| **F4** | Toggle editor mode on/off |
| **Shift+F5** | Toggle Creator Mode overlay on/off (requires editor mode active) |

Plain **F5** is not the Creator Mode toggle. When the editor is inactive, F5 remains the existing global quick-save route.

## Existing Seams

Mesh already has the right shape for an additive shell:

- `EditorModeController` is a facade over focused controllers, not a place to add another large UI system.
- `EditorOverlayController` orchestrates editor overlay drawing and is the likely integration point for a small Creator Mode overlay hook.
- `EditorSelectionController` owns selection state and should remain the source for selected entity identity.
- `ProblemsController` already provides filtered issue rows, severity counts, and jump/fix-oriented data for a friendly "Things to Fix" panel.
- `EditorCommandDispatchController` applies and reverts existing editor commands. Creator Mode must not rewrite this path.
- `EditorLiveSessionBridge` already stages proposals and keeps mutation work on the editor thread. This is the correct future path for Creator Mode proposals.
- `ChatSessionController` already models read-only scene inspection, prefab/entity listing, and staged proposal tooling. Creator Mode can borrow the safety model without becoming chat-driven.

The first slice should therefore be additive, read-only, and controller-local. It should not modify scene loading, runtime state, save/load, battle systems, or advanced editor internals.

## Architecture

Creator Mode should live under a new package:

```text
engine/editor/creator_mode/
```

Suggested modules:

- `creator_mode_controller.py`
- `creator_overlay.py`
- `creator_state.py`
- `creator_terms.py`
- `creator_actions.py`
- `creator_problems.py`

Responsibilities:

- `creator_mode_controller.py`: owns enabled/disabled state, mode toggling, read-only snapshot assembly, and handoff to overlay rendering.
- `creator_overlay.py`: renders the shell. It must be visual-only in CREATOR-0.
- `creator_state.py`: pure dataclasses or typed dictionaries for shell state, selected object summary, visible panel tab, and recent read-only events.
- `creator_terms.py`: pure classification and label mapping from engine concepts to creator-facing terms.
- `creator_actions.py`: defines disabled action descriptors in CREATOR-0 and later pure proposal-building entry points.
- `creator_problems.py`: adapts existing `ProblemsController` payloads into friendly "Things to Fix" rows.

Data flow:

1. Read editor/window/scene snapshots.
2. Classify and summarize them using pure functions.
3. Render a friendly shell over the existing viewport.
4. Do not mutate scene JSON, sprites, behaviour config, commands, saves, or runtime systems in CREATOR-0.
5. Later slices may build proposal objects, but application must go through existing safe proposal and review systems.

Creator Mode must not directly edit scene JSON. Future writes must be staged through existing safe systems, such as the live proposal bridge/proposal inbox, and then reviewed by a human before applying.

## Proposed UX

Top bar:

```text
[Save] [Test Play] [Fix Problems] [Advanced Mode]
```

For CREATOR-0, buttons may render as disabled/read-only except `Advanced Mode`/toggle controls if wired by the implementation task.

Left rail:

```text
Map
Person
Door
Monster Area
Battle
Quest
Item
Light
```

Center:

- Existing viewport remains visible.
- Creator Mode must not replace camera, selection, transform, tile, or playtest behavior in CREATOR-0.

Right panel:

- Friendly selected-object summary.
- No raw JSON.
- No behaviour_config dump.
- No schema-level fields unless the user explicitly switches to Advanced Mode in a later slice.

Bottom:

```text
Things to Fix / Recent Changes / Playtest Notes
```

For CREATOR-0, this can be read-only and backed by existing problems/session state where available.

## Friendly Terms

Initial terms should map common Mesh patterns into creator language:

- Door: transition/exit behaviour or scene-linking data.
- Person: dialogue, quest giver, vendor, schedule, or NPC-like tags.
- Monster Area: encounter zone, monster encounter behaviour, or trigger area configured for encounters.
- Shopkeeper: vendor behaviour or shop-related config.
- Item: collectible, pickup, inventory reward, or item prefab.
- Light: light entity, scene light, or light-source behaviour.
- Enemy: combat/health/AI behaviour combination.
- Thing: fallback when no friendly classification is confident.

The classifier must be pure logic. It can inspect snapshots of names, tags, behaviours, and behaviour config, but it must not require Arcade, GL, live sprites, or filesystem writes.

## CREATOR-0 Phased Slice Plan

### CREATOR-0a - Read-only shell

- Add Creator Mode controller/overlay.
- Render friendly shell.
- No scene mutation.
- No write actions.
- Can be toggled safely.
- Existing editor still works.

Implementation limits:

- Allowed files should be limited to the new `engine/editor/creator_mode/` package, narrowly scoped overlay hook wiring, and tests.
- Do not rewrite `EditorModeController`.
- Do not alter command dispatch, scene controllers, save/load, schema, or GameWindow.

Expected tests:

- Headless controller state tests.
- Overlay smoke test with drawing calls stubbed.
- Toggle test proving Advanced Mode remains reachable.
- No-mutation test comparing scene payload before/after toggle/draw.

### CREATOR-0b - Friendly entity classifier

- Pure logic.
- Classify selected entity snapshots into:
  - Door
  - Person
  - Monster Area
  - Shopkeeper
  - Item
  - Light
  - Enemy
  - Thing
- Use behaviours/config/tags/names to infer kind.
- Unit tests only, no Arcade GL.

Expected tests:

- One fixture per friendly kind.
- Ambiguous cases prefer the most creator-useful label.
- Unknown shapes return `Thing`.
- Classifier never mutates input dictionaries.

### CREATOR-0c - Friendly inspector read-only

- Selecting a Door shows destination, spawn, and lock info in plain English.
- Selecting a Person shows dialogue, quest, vendor, or schedule role info.
- Selecting a Monster Area shows encounter info.
- Advanced details remain hidden unless explicitly requested in a future slice.

Expected tests:

- Pure summary formatting tests.
- Selected-object missing/invalid data falls back gracefully.
- No raw `behaviour_config`, `prefab_id`, `render_layer`, or `depth_z` appears in default friendly summaries.

## CREATOR-1 Follow-up Plan

### CREATOR-1a - Door plan builder

- Add a pure function that builds intended Mesh ops for creating/configuring a door.
- Return ops only.
- Do not apply them.
- Do not mutate scene JSON.
- Can later stage through the proposal bridge.
- Door Plan Builder is pure and returns proposed operations only.
- It does not apply or stage changes yet.

Expected tests:

- Source scene, destination scene, spawn id, and lock options produce deterministic ops.
- Invalid inputs return structured errors, not partial mutation.
- Function does not import Arcade or editor runtime.

### CREATOR-1b - Stage Proposal integration

- Door Plan Preview Model is pure.
- It only formats plans for human review.
- Stage/Apply actions remain disabled.
- Door Workflow Model combines the door plan and preview.
- It remains pure/read-only.
- It still does not stage or apply changes.
- CREATOR-1d inspected the existing proposal bridge; CREATOR-1e must follow `docs/design/creator_mode_proposal_bridge_recon.md`.
- CREATOR-1d added no staging or applying.
- CREATOR-1e converts door workflows into live-op dictionaries only when representable.
- CREATOR-1e does not stage, apply, or mutate.
- CREATOR-1f stages door proposal ops through an injected existing bridge-like object only.
- CREATOR-1f does not accept/apply proposals; UI wiring remains future work.
- CREATOR-1g adds a read-only staging readiness model.
- CREATOR-1g does not stage or apply; UI wiring remains future work.
- CREATOR-1h adds a read-only door panel presentation model.
- CREATOR-1h does not render, stage, or apply; UI rendering/wiring remains future work.
- CREATOR-1i renders the door panel read-only in Creator Mode.
- CREATOR-1i does not stage, apply, or add clickable actions; manual F4 / Shift+F5 dogfood is required.
- CREATOR-1j adds an explicit `CreatorModeController.stage_selected_door_proposal()` action to stage the selected door proposal through the existing staging adapter.
- CREATOR-1j does not add clickable UI or input wiring; overlay rendering remains read-only display-only.
- CREATOR-1k wires the Stage Proposal display action to explicit staging via overlay click hit-testing.
- CREATOR-1k does not accept/apply proposals; manual click dogfood is required.
- CREATOR-1l updates Creator Mode toggle documentation to match the current binding (**Shift+F5**, not plain F5).
- CREATOR-1m prevents duplicate staging of the same selected door proposal after a successful stage.
- CREATOR-1m does not accept/apply proposals and does not add new clickable actions.
- CREATOR-1n adds read-only staged proposal status in Creator Mode.
- CREATOR-1n does not accept/apply/reject proposals and does not add new clickable actions.
- CREATOR-1o adds a read-only pending proposal list.
- CREATOR-1o does not accept/apply/reject proposals and does not add new clickable actions.
- CREATOR-1p documents the existing proposal accept/apply path.
- CREATOR-1p does not implement accept/apply.
- Future accept/apply work must preserve revision guard and undo batch semantics.
- CREATOR-1q adds a read-only proposal accept/reject readiness model.
- CREATOR-1q does not call accept/reject/apply and does not add clickable actions.
- CREATOR-1r displays read-only proposal accept/reject readiness in Creator Mode.
- CREATOR-1r does not call accept/reject/apply and does not add clickable actions or hitboxes.
- CREATOR-1s shares one proposal status read across proposal status/list and accept-readiness derivation.
- CREATOR-1s does not change UI behavior and does not call accept/reject/apply.
- CREATOR-1t adds a read-only proposal review details model.
- CREATOR-1t does not render new UI, call accept/reject/apply, or add clickable actions.
- CREATOR-1t prepares dry-run and affected-id detail for later review UI.
- CREATOR-1u displays read-only proposal review details from the shared proposal status read.
- CREATOR-1u does not call accept/reject/apply and does not add clickable actions or hitboxes.
- CREATOR-1v documents proposal review **surface ownership** (where review UI should live).
- CREATOR-1v recommends **hybrid handoff**: Creator Mode keeps compact read-only summary; official **AI Proposals** inbox owns accept/reject.
- CREATOR-1v recommends **avoiding further bottom-panel expansion** for review/mutation.
- CREATOR-1v does not implement accept/reject/apply, buttons, or input routing.
- Future accept/reject work should prefer **official Proposal Inbox handoff** before any Creator Mode mutation trigger.
- CREATOR-1w adds read-only proposal inbox handoff state (`CreatorProposalHandoffModel`).
- CREATOR-1w does not click/focus/open the AI Proposals inbox yet.
- CREATOR-1w does not call accept/reject/apply and does not expand the bottom panel.
- CREATOR-1x renders the read-only Proposal Inbox handoff label in Creator Mode.
- CREATOR-1x replaces Creator Mode accept/reject wording with inbox handoff wording (`Review: Use AI Proposals`).
- CREATOR-1x does not click/focus/open the inbox.
- CREATOR-1x does not call accept/reject/apply and does not expand the bottom panel.
- CREATOR-1y dogfoods the official **AI Proposals** path with Creator-staged proposals (see `docs/design/creator_mode_official_inbox_dogfood.md`).
- CREATOR-1y does not add Creator Mode accept/reject/focus/open.
- Future focus/open work (CREATOR-1z) depends on human completion of the CREATOR-1y GUI checklist.
- CREATOR-1z-pre displays `proposal_id` as plain text in the official AI Proposals dock (`ID: {proposal_id}`).
- CREATOR-1z-pre is display-only; it does not change accept/reject behavior or add clickable actions.
- Non-representable door workflows fail closed.
- Creator Mode may stage a proposal using the existing safe live proposal bridge.
- Human still reviews before applying.
- Proposal staging must be explicit and visible.
- Proposal application remains owned by existing proposal/command systems.

Expected tests:

- Staging creates proposal rows without applying scene changes.
- Rejection leaves scene unchanged.
- Acceptance uses existing safe path; Creator Mode does not implement a second command dispatcher.

## Safety Rules For Agents

Every implementation task must state:

- Allowed files.
- Forbidden files.
- Acceptance tests.
- Manual dogfood step.
- Rollback expectation.

Forbidden by default:

- `engine/game.py`
- `engine/monster/*`
- `engine/scene_controller.py`
- save/load systems
- battle systems
- broad `editor_controller.py` rewrites
- command dispatch rewrites
- scene schema migrations

Also forbidden for CREATOR-0:

- Any scene JSON writes.
- Any direct mutation of `behaviour_config`.
- Any direct filesystem write from the overlay.
- Any new runtime dependency.
- Any requirement for Arcade GL in pure model tests.

Rollback expectation:

- Creator Mode must be removable by disabling the overlay/controller hook.
- Existing Advanced Mode must remain the fallback.
- A failed Creator Mode draw must not corrupt editor state or scene data.

## Acceptance Criteria For First Implementation Slice

- Creator Mode can be toggled on/off.
- Overlay renders without crashing.
- No scene JSON changes occur.
- Current Advanced Mode still works.
- Selected entity can be summarized in friendly terms.
- Tests run headless where possible.
- Problems data can be displayed in friendly form without changing `ProblemsController`.
- The implementation does not touch runtime/editor internals outside the narrow agreed hook.

## Manual Dogfood Step For CREATOR-0

1. Open a normal Mesh project in the existing editor.
2. Press **F4** to enter editor mode if needed.
3. Press **Shift+F5** to toggle Creator Mode on.
4. Confirm the viewport remains visible.
5. Select a door/person/ordinary object.
6. Confirm the right panel shows a friendly read-only summary.
7. Press **Shift+F5** again to leave Creator Mode, or **F4** to exit editor mode.
8. Confirm the existing editor controls still work.
9. Close and inspect the scene file to confirm it did not change.

## Manual dogfood checklist

- Launch Mesh.
- Press **F4** to enter editor mode.
- Press **Shift+F5** to toggle Creator Mode on.
- Confirm Creator Mode overlay appears.
- Confirm it says "Read-only preview".
- Select a door/person/monster area if available.
- Confirm the right panel updates or at least does not crash.
- Press **Shift+F5** again.
- Confirm overlay hides.
- Confirm normal editor still works.

## Director Notes

Make Mesh feel simple without making Mesh stupid. Creator Mode is a friendly shell, not a weaker engine.

The goal is not to hide power forever. The goal is to make the first five minutes understandable while keeping the advanced editor, schema, behaviours, proposal bridge, and engine architecture intact.

Agents should bias toward small pure modules, read-only snapshots, and tests that prove non-mutation. Any task that needs to touch GameWindow, scene schema, command dispatch, save/load, or battle systems is not CREATOR-0 and must be rejected or re-scoped.
