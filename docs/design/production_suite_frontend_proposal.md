# Mesh Production Suite — Frontend Proposal (PARKED / future track)

**Status:** PARKED for later (recorded 2026-06-29). Not active work. The current focus is the
monster-RPG campaign ([`docs/monster_rpg_roadmap.md`](../monster_rpg_roadmap.md)). This is a *future
parallel track*: a production-grade editor shell ("Mesh Production Suite") that organizes Mesh's existing
editor systems into a clean, neutral, Godot/Unity/VS-Code-style workspace — **not** a skin, not a game menu.

Authored by an external agent. Reproduced below with a director's preface mapping it to Mesh's reality.

---

## Director's note — how this maps to what Mesh already has

This proposal is sound because it explicitly respects controller boundaries and is built around a
**read-only snapshot + command-dispatch** contract rather than reaching into internals. That is exactly the
right seam, and Mesh already has most of the load-bearing pieces from the co-creative-editor arc (NS#2):

- **Phase 3 (the snapshot layer) is the crux — and it largely exists.** `SceneController.build_scene_snapshot(compact=False)` already reconciles runtime state into an AI/UI-facing payload. The proposal's "stable JSON-like editor-state snapshot" is a superset of this — extend that, don't invent a new one.
- **The transport already exists.** `EditorLiveSessionBridge` (loopback HTTP, 127.0.0.1, bearer token, `.mesh/live_session.json` discovery) is exactly the "local JSON/WebSocket bridge" the proposal's tech-direction option 1/4 describes. A web frontend talks to Mesh through that, keeping the Arcade viewport in-engine (option 4, the hybrid — the realistic choice).
- **Command dispatch already exists.** The editor's command systems + `EditorMainThreadDispatcher` (call_sync/post/drain) + `ApplyAIOpBatch` (one undo entry per batch) are the "dispatch through existing command systems, preserve undo/redo" path. Inspector editing (Phase 6) routes through these — do NOT bypass them.
- **The Agent Plan panel already has a precursor:** the AI Proposals inbox dock + the native chatbox. The proposal correctly says "not a chatbot gimmick" — it's the practical execution surface (tasks/files/validation/commands), which aligns with the proposal-inbox model already built.
- **Problems/Validation (Phase 8)** maps onto existing `validate_scene` / `playability_check` / verify-all / the problems panel.

**The crux, restated:** the whole thing rises or falls on the **editor-state snapshot contract** (Phase 3).
Get that stable and complete and the rest is incremental. This is the same architectural seam called out as
the central tension of NS#2 (AIOps/file path vs editor/in-memory path) — so this track and the co-creative
editor share a spine.

**How to run it (director plan):** this is a good track to hand to **another AI** (it's mostly self-contained
frontend work in `prototypes/production_suite/` for Phases 1–2, then a defined snapshot/command contract for
Phases 3+), with me as director. It should **not** distract from the monster campaign — run it in parallel
only when there's slack, and gate every integration phase on "no existing editor/engine code broken" + the
snapshot contract, exactly as the proposal says. First concrete deliverable is a static mockup
(`prototypes/production_suite/index.html` + `styles.css` + `mock_state.json` + `README.md`) — zero engine risk.

**Honest caveat:** the user's standing direction is "the crown is AI, meh-UI is acceptable, generate visuals
later." So this Production Suite is valuable as a *workflow/credibility* layer (making Mesh feel like a
serious tool), not as visual polish. Prioritize it accordingly — after/around the game, not instead of it.

---

## The proposal (as received)

### Goal
Build a clean, boring, production-grade frontend shell for Mesh Engine. The aim is not a fantasy-themed game
menu or flashy mockup — it is to make Mesh feel like a serious content production tool: closer to Godot,
Unity, VS Code, or a lightweight internal editor suite. Mesh already has a strong in-engine editor
foundation (project explorer, dock state, inspector, problems panel, command/search, history, asset browser,
tile/lights tools, dialogue/animation editing, prefab tooling, scene validation, verify-all). The frontend
should organize and expose those systems clearly rather than add a decorative layer.

### Core product direction
Treat it as **Mesh Production Suite** — a consistent editor workspace around these pillars:
1. Project and asset navigation
2. Scene viewport and tool modes
3. Entity selection and inspection
4. Problems, validation, console, and history
5. Command palette and search
6. Build/run/verify workflow
7. Agent/developer task surface for AI-assisted authoring

Design is intentionally neutral: dark professional theme; sharp readable panels; simple icons; one
restrained accent; no fantasy/RPG skin; information density over flair; fast workflow over decoration.

### Important constraint
Not a skinning task. Define a stable production-app shell that maps onto the existing Mesh editor
architecture and can later be integrated safely. Respect controller boundaries — consume snapshots/providers
and dispatch existing commands; do not create giant new UI state objects or bypass existing controllers
(docks, inspector, project explorer, problems, command palette, search, history, tiles, lights, animation,
dialogue, prefab, hierarchy, cursor, play mode).

### Proposed layout
- **Top bar:** Mesh Production Suite branding; File/Edit/Scene/Tools/Build/Help menus; branch/project
  indicator; Save / Run / Verify / Build Demo; Play/Edit toggle; dirty-scene indicator.
- **Left activity rail (VS Code/Godot-style):** Project, Scenes, Assets, Hierarchy, Problems, Settings.
- **Left dock:** Project Explorer / Assets / Scenes / Prefabs / Worlds; search/filter; tree view; file +
  missing-reference status markers; (later) right-click rename/move/delete/reveal/duplicate, safe-refactor
  preview.
- **Center workspace:** breadcrumb (scene path / selected entity); tool-mode strip (Move, Zone, Path, Tile,
  Lights, HD-2D); viewport; grid/snap/zoom status; selection highlight; trigger/zone + light/occluder
  overlays; asset-placement ghost. v1 can be a static/clickable prototype; later integrate the live Arcade
  viewport or a snapshot-driven companion panel.
- **Right dock:** Inspector / Components / Rendering / Behaviour Config / Light / Prefab. Fields: name, id,
  position, scale, rotation, layer, sprite path, render layer/depth, behaviours, behaviour_config, prefab
  source/override, dirty/undo info. Edits route through existing editor commands (undo/redo intact).
- **Bottom dock:** Problems / Console / History / Validation / Logs / Agent Plan. Problems: severity,
  message, location, suggested action, jump-to, copy-location, reveal. Validation: scene validation, content
  audit, missing assets, verify-all result, test-tier status, packaging/build status. Agent Plan: pending
  tasks, suggested next actions, generated plan, validation checklist, files touched, commands to run
  (practical execution panel, not a chatbot).
- **Command palette:** open scene, find entity, reveal asset, run command, run verify-all, open problems,
  jump to inspector section, toggle tools, open panels, build/play/save. (High value — one discoverable
  surface over Mesh's many systems.)

### Implementation plan (layered)
1. **Static UI mockup** — HTML/CSS, no integration; finalize layout + dark theme; screens: main layout,
   inspector-with-entity, problems/validation, command palette, asset/project explorer.
2. **Clickable prototype** — standalone, mock JSON data; tabs switch; palette opens/closes; selecting mock
   entities updates inspector; problems filter/jump; collapsible docks; theme vars; fake console/history/
   validation. No real mutation.
3. **Editor state snapshot layer** — read-only state provider; stable JSON-like snapshot exposing project
   root, active scene path, dirty status, active tool mode, selected entity summary, entity/hierarchy list,
   asset index, problems, validation status, undo/redo summary, dock state, viewport metadata. *Most
   important integration layer — prevents tight coupling.*
4. **Read-only integrated dashboard** — shell shows live Mesh state (project/inspector/problems/validation);
   no editing except safe panel toggles.
5. **Command dispatch integration** — frontend actions go through existing command systems (save/open
   scene, select entity, toggle panel, run validation, jump to problem, reveal file, switch tool mode, play,
   verify-all). No direct mutation where a command/undo path exists.
6. **Inspector editing** — edit fields via safe editor ops with undo/redo + dirty + validation hooks
   (transform, sprite, layer, behaviours, behaviour_config, render/depth, light).
7. **Asset browser + placement** — browse/filter assets+prefabs, preview metadata, place via existing
   placement flow, ghost preview, undo/redo.
8. **Problems/validation workflow** — run validation, structured results, jump-to, copy location, suggest
   fix category, optionally create an agent task from a problem.

### Design system
Neutral dark theme: near-black blue/gray bg; dark-gray panels; subtle gray borders; high-contrast (not pure
white) text; muted metadata text; one restrained blue accent; green/yellow/red only for status; light
rounded corners; no ornaments. Reusable components: AppShell, TopBar, ActivityRail, Dock, DockTabs,
PanelHeader, SearchBox, TreeView, EntityList, InspectorSection, InspectorField, ComponentCard, ProblemsTable,
ConsolePanel, ValidationPanel, CommandPalette, StatusBar, ToolbarButton, Badge, Splitter. Accessibility:
readable fonts; clear focus; keyboard-first palette; consistent spacing; no tiny icon-only controls; panel
titles always visible; distinct warnings/errors; no hidden destructive ops; safe delete/refactor previews
first.

### Suggested technical direction
Start technology-agnostic; first prototype can be static HTML/CSS (no React needed yet). Later integration
options: (1) browser companion frontend via local JSON/WebSocket bridge; (2) embedded webview around the
Python/Arcade runtime; (3) native Arcade-rendered UI using the same layout/components; (4) hybrid — Arcade
viewport in-engine + external frontend for project/inspector/problems/commands. Do not choose heavy
architecture until the read-only snapshot is defined.

### Recommended first concrete task
Create `prototypes/production_suite/` with `index.html`, `styles.css`, `mock_state.json`, `README.md`. Mock
includes the full layout (top bar, activity rail, project explorer, scene viewport mock, inspector, bottom
tabs, command palette, status bar), loads mock data, and supports minimal interaction (switch tabs, select
entities → update inspector, open/close + filter palette, filter project tree).

### Acceptance (first pass)
Looks like a serious production tool; no fantasy/game styling; layout maps to Mesh's existing systems; opens
locally without setup pain; componentized enough to evolve; clear path from mock data to real snapshot; no
existing engine/editor code broken; no premature deep integration.

### Non-goals (first pass)
No Arcade viewport embedding, real scene mutation, full asset placement, drag/drop, refactor/delete FS
writes, live verify-all execution, full agent automation, replacing editor controllers, or architecture
redesign.

### Risks / mitigations
- Pretty mockup that doesn't integrate → build around snapshots + command dispatch + real Mesh concepts.
- Frontend bypasses undo/redo → all mutations go through existing editor command systems.
- Scope explosion → read-only shell first, then dispatch, then editing.
- AI-agent gimmick → Agent panel is practical (tasks/files/validation/commands), not chat-first.
- Web frontend fights Python/Arcade → delay final integration; define state + command contracts first.

### Final recommendation
Build in layers: static mockup → clickable prototype → read-only snapshot → live dashboard → command
dispatch → inspector editing → asset placement → validation/agent workflow. Keep it safe, testable, aligned
with existing architecture. Goal: make Mesh feel like a serious, boring, reliable production environment —
not flashy.
