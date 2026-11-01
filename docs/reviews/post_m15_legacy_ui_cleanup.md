# Post-Milestone 15: Legacy UI Cleanup

Branch `chore/legacy-ui-cleanup`, built on `chore/remove-soft-shadows-toggle` (draft PR #346). Its draft PR targets
that branch, so the diff contains only this cleanup. PR #344 is untouched and nothing is merged.

**Principle:** remove obsolete interfaces, not capabilities. The legacy editor still holds features Mesh Studio
doesn't have yet. It stays intact, reachable through explicit options, and out of the normal workflow.

## 1. Audit (before any change)

### How each editor is reached

| Path | Before | After |
|---|---|---|
| `Mesh Engine.bat` → launcher → a project | Mesh Studio | Unchanged |
| `mesh edit` on a project with a world | Mesh Studio | Unchanged |
| `mesh edit` on an older project without a world | Legacy editor (Studio needs a world) | Unchanged: an explicit editor launch, kept for compatibility |
| `MESH_LEGACY_EDITOR=1` | Legacy editor | Unchanged: the explicit developer / compatibility option |
| **F4 in a running game outside Studio** (`mesh play`, a standalone game) | **Dropped into the full legacy editor, with no gating**, on any project, Studio projects included | Only with `MESH_LEGACY_EDITOR=1`, in an editor launch, or to leave an editor that's already open |
| F4 in Studio's play-test | Studio stops the play-test (handled before the game's own keys) | Unchanged |

### Audit of the legacy editor's 140 registered commands

101 are in its command palette and 56 in its menus: File, Edit, View, Scene, Entity, Arrange, Preferences and Help.

**Method:** a script resolved every command's handler and listed the editor attributes each reaches through
`getattr(..., None)`, which fails silently, checking them against the real editor object built hidden on a scratch
project. Every handler exists, because the registry would fail to build otherwise. The one-line handlers were read:
all delegate to real implementations. Only one command reached for something that doesn't exist:

- **File → "Export Web Demo..."** (`app.export_web_demo`). It called `window.export_web_demo`, which no window has, so
  clicking it did nothing.

Limits of the audit: it proves every handler is real and catches calls to missing attributes. It does not execute
the 140 commands, some of which delete or move files, so behaviour beyond that is not claimed.

### What else users see

| Found | Status before | Verdict |
|---|---|---|
| HUD controls hint and Help overlay: **"F2: Editor"** | False: F2 is debug capture or the encounter overlay; the editor key was F4. And a player has no editor | **Corrected** |
| Title menu: **"Run Web Demo (Local Preview)"**, **"Export Web Demo (.zip)"** | They import the engine checkout's `tooling/`, which a creator's own game and a pip install don't have, so there they logged a warning and did nothing | **Shown only where they can run** |
| Title menu's **project browser** (recent projects, create, open, "Use current repo") | Shown only when the legacy editor is active, or the engine repository itself runs with no project pinned. Never for a launched game | **Kept** (legacy and developer only); the launcher replaces it for normal use |
| Legacy **"Toggle Soft Shadows"** command and the pause and main menu toggle | Removed in PR #346 | **Verified:** no references remain |
| Studio and launcher | Every control is wired to a working operation (Milestones 1–15 acceptance) | No change |

### Duplicated by Studio, but legacy-only in reach

These legacy commands overlap Studio. They're kept because they serve legacy-editor sessions, which Studio
doesn't load:
- **Edit:** save scene; undo / redo; duplicate / delete.
- **Placing:** the prefab palette (Studio: Objects); the light tool (Studio: Lighting).
- **Rooms:** the scene browser / switcher (Studio: Rooms).
- **Playing:** "Play From Here" / "Stop" (Studio: F4).
- **Lighting:** fog and lighting presets (Studio: Lighting panel).
- **Creator Mode's** door workflow (Studio: doors and passages).

None is reachable from Studio, so none is on the normal path.

## 2. Removed

| Removed | Where | Reason |
|---|---|---|
| **F4 opening the legacy editor in a game launch** | `action_runtime/registry._toggle_editor`, now gated by `legacy_editor_allowed()` | Studio is the editor. A creator testing with `mesh play`, or a player of a standalone game, shouldn't drop into a second, older editor. It stays available with `MESH_LEGACY_EDITOR=1` and in editor launches, and an open legacy editor or its play-test can always be left with F4. |
| **"F2: Editor"** in the HUD controls hint and the Help overlay | `ui_overlays/hud.py`, `help_overlay.py` | Wrong key, and it advertised an editor to players |
| **File → "Export Web Demo..."** (`app.export_web_demo`, `_export_web_demo`) and its menu-bar slot and web filter | `editor_actions_registry.py`, `editor_actions_parts/core_actions.py`, `menu_bar_model.py` | Inert: its backend (`window.export_web_demo`) never existed. Web export itself remains on the title menu where its tool exists |
| **"Run Web Demo" / "Export Web Demo (.zip)" in places they can't work** | `main_menu_overlay._items`, via `_tool_available()` | They did nothing outside the engine checkout. The items remain where `tooling.web_preview` / `tooling.release_web_demo` import |
| Soft Shadows (PR #346, not redone) | — | Verified only: no `soft_shadows.toggle`, `_toggle_soft_shadows` or "Toggle Soft Shadows" left in the engine |

**Not changed:**
- Mesh Studio, the launcher, the Graphite theme and branding, the icons, the cards, the map workspace and the
  inspector;
- the pause menu, save/load and every functional setting;
- room lighting (Sharp / Soft / Softer) and per-light shadows (no renderer code changed);
- project formats, gameplay and save files.

## 3. Legacy-only functionality retained (migration requirements for Studio)

Kept intact in the legacy editor (`MESH_LEGACY_EDITOR=1`, or `mesh edit` on a project without a world). Studio has
no equivalent yet:

| Area | Legacy commands / panels |
|---|---|
| **HD-2D** | Scene presets (Soft, Crisp, Noir, Dreamy), "Upgrade Scene to HD2D Defaults"; scene toggles (shadows, contact, AO, depth tint, outline) and strengths; 20 per-object override commands, including copy, paste and batch paste by radius |
| **Background planes** (parallax) | Add, duplicate, remove, reorder, select, tiling X/Y |
| **Project explorer and asset refactoring** | Safe rename, move and delete of assets with reference updates, inline rename, reveal, copy paths |
| **Asset browser, prefab variant editor** | Browse assets; edit prefab variants |
| **Diagnostics** | Problems panel (jump to and copy locations), Debug tab, Export Debug Bundle, quest diagnostics, filtered events, cutscene summary |
| **Arrange** | Align left/right/top/bottom/centre; distribute horizontally/vertically |
| **Lighting extras** | Occluder tool (hand-drawn shadow casters); lighting presets 1–4 |
| **Build** | **Build for Windows** (File menu) |
| **Editor comfort** | Keyboard-shortcut editor, Find Everything, editor tour, dock and panel layout, ghost originals |
| **Creator Mode** | The friendly read-only overlay and door workflow on the legacy editor |

Also still needed in Studio, from `MESH_REBUILD.md`: quest, item and prefab editors; full dialogue editing; list
fields; triggers drawn on the map; HD-2D and parallax controls.

## 4. Compatibility

| Case | Result | Checked by |
|---|---|---|
| Older projects without a world | `mesh edit` still opens them in the legacy editor (an editor launch: F4 play/stop works) | `test_legacy_ui_cleanup` (editor launch allowed); `game_launch` unchanged |
| A running legacy editor or its play-test | F4 always leaves it | `test_legacy_ui_cleanup` |
| `MESH_LEGACY_EDITOR=1` | F4 opens the legacy editor anywhere, as before | `test_legacy_ui_cleanup`, `test_input_toggle_editor` |
| Older saved settings and configs with Soft Shadows | Load (PR #346) | `test_soft_shadows_setting_removed` (in the fast tier) |
| Studio projects, launcher, play-test, save/load | Unchanged code paths | Tests below; `visual_polish_check` (hidden Studio and game render) |

## 5. Tests

All of these ran headless or in hidden windows, on the final tree:

- **New `tests/test_legacy_ui_cleanup.py`** (fast, 5 tests):
  - F4 in a game no longer opens the legacy editor;
  - it still does in an editor launch, with `MESH_LEGACY_EDITOR=1`, and to leave an open editor or play-test;
  - no hint names an editor;
  - every legacy menu slot names a real command, and the inert export is gone;
  - the title menu's web-demo items appear only where their tool exists, and the game's own items stay.
- **Updated:** the HUD hint text (`test_hud_controls_hint_toast`), the legacy File menu's separator count and the
  suppressed web item (`test_menu_separators_web_contract`), and the editor-toggle test, now an editor launch
  (`test_input_toggle_editor`).
- **Targeted:** **4,186 passed**, 52 skipped (GPU-gated). This ran
  `-k "studio or launcher or palette or menu or shortcut or keymap or input or editor or project or legacy or settings or save or load or play or shadow or toggle"`,
  which covers Studio start-up and editing, the launcher, command-palette registrations, menus and shortcuts,
  project loading, legacy projects, shadow settings, save/load and play-test transitions.
- **Fast tier** (`python -m tooling.test_tiers tier0`): **4,351 passed, 0 failed**.
- **Gates:** type gate ok, ruff gate ok, no `type: ignore`.
- **`tooling/visual_polish_check.py`** (hidden Studio and game render): **10/10**. Studio starts, selects and outlines
  door areas; the game draws them correctly.
- **Rendering:** no rendering code changed, so the GPU tier wasn't needed.

No real-window or desktop tests were run.

## 6. Commits and PR

| Commit | What |
|---|---|
| `e5dca9f` | The cleanup: engine changes and tests |
| (this document's commit) | This review |

- **Draft PR:** https://github.com/septimus82/Mesh/pull/347. Its base is `chore/remove-soft-shadows-toggle` (#346),
  so the diff contains only this cleanup.
- **Order to merge, if accepted:** #346, then this PR, both into `redesign/visual-editor` (#344).
