# Editor Design System v1 (Extracted)

## 1) Purpose & scope
This document is the canonical extraction of visual/editor-UI decisions currently locked in code as of `1ae9cdd` (PR #19 merged). It is intended for contributors touching editor overlays, panel rendering, modal UX, command palette presentation, and feedback/progress messaging. Use it before introducing UI changes, and cite it in UI-affecting commits. This is intentionally a **descriptive** document, not a prescriptive redesign brief: it captures what is implemented today, including inconsistencies. It does **not** define new direction for unresolved areas (icons, unified interaction states, animation language). Unresolved areas are explicitly marked `TBD — needs director adjudication`.

---

## 2) Color palette

### 2.1 Severity colors (toast feedback)
| Token | Value (RGB / Hex) | Usage | Source |
|---|---:|---|---|
| `severity-info-bg` | `(32, 36, 44)` / `#20242C` | Info toast panel fill | `engine/ui_overlays/editor_feedback_overlay.py:15` |
| `severity-info-border` | `(150, 190, 255)` / `#96BEFF` | Info toast border | `engine/ui_overlays/editor_feedback_overlay.py:16` |
| `severity-info-text` | `(255, 255, 255)` / `#FFFFFF` | Info toast text | `engine/ui_overlays/editor_feedback_overlay.py:17` |
| `severity-warning-bg` | `(64, 44, 20)` / `#402C14` | Warning toast panel fill | `engine/ui_overlays/editor_feedback_overlay.py:18` |
| `severity-warning-border` | `(255, 191, 92)` / `#FFBF5C` | Warning toast border | `engine/ui_overlays/editor_feedback_overlay.py:19` |
| `severity-warning-text` | `(255, 244, 224)` / `#FFF4E0` | Warning toast text | `engine/ui_overlays/editor_feedback_overlay.py:20` |
| `severity-error-bg` | `(72, 24, 24)` / `#481818` | Error toast panel fill | `engine/ui_overlays/editor_feedback_overlay.py:21` |
| `severity-error-border` | `(255, 110, 110)` / `#FF6E6E` | Error toast border | `engine/ui_overlays/editor_feedback_overlay.py:22` |
| `severity-error-text` | `(255, 255, 255)` / `#FFFFFF` | Error toast text | `engine/ui_overlays/editor_feedback_overlay.py:23` |

### 2.2 Problems panel colors
| Token | Value (RGBA / Hex RGB) | Usage | Source |
|---|---:|---|---|
| `problems-text` | `(220,220,230,255)` / `#DCDCE6` | Main list and action labels | `engine/ui_overlays/problems_panel_overlay.py:15` |
| `problems-dim` | `(150,150,160,255)` / `#9696A0` | Meta rows, counts, hints | `engine/ui_overlays/problems_panel_overlay.py:16` |
| `problems-selected-bg` | `(90,140,200,140)` / `#5A8CC8` | Selected row background | `engine/ui_overlays/problems_panel_overlay.py:17` |
| `problems-header` | `(180,200,220,255)` / `#B4C8DC` | Header title | `engine/ui_overlays/problems_panel_overlay.py:18` |
| `problems-panel-bg` | `(18,18,22,220)` / `#121216` | Dock panel background fill | `engine/ui_overlays/problems_panel_overlay.py:82-88` |
| `problems-panel-border` | `(100,100,110,255)` / `#64646E` | Dock panel border | `engine/ui_overlays/problems_panel_overlay.py:89-96` |

### 2.3 Settings/modal/base panel colors
| Token | Value (RGBA / Hex RGB) | Usage | Source |
|---|---:|---|---|
| `settings-frame-bg` | `(0,0,0,210)` / `#000000` | Settings outer frame fill | `engine/ui_overlays/settings_overlay.py:669-675` |
| `settings-frame-border` | `SKY_BLUE` | Settings outer border | `engine/ui_overlays/settings_overlay.py:676` |
| `settings-section-bg` | `(22,24,30,180)` / `#16181E` | Non-overview/options section fills | `engine/ui_overlays/settings_overlay.py:697-710` |
| `modal-dim` | `(0,0,0,140)` / `#000000` | Unsaved-changes full-screen dim | `engine/editor/editor_unsaved_changes_controller.py:153-160` |
| `modal-panel-bg` | `(0,0,0,220)` / `#000000` | Unsaved-changes modal panel | `engine/editor/editor_unsaved_changes_controller.py:169` |
| `modal-panel-border` | `SKY_BLUE` | Unsaved-changes modal border | `engine/editor/editor_unsaved_changes_controller.py:170-176` |

### 2.4 Text colors
| Token | Value | Usage | Source |
|---|---:|---|---|
| `text-primary` | `WHITE` | Modal/body primary text | `engine/editor/editor_unsaved_changes_controller.py:186-189` |
| `text-secondary` | `LIGHT_GRAY` | Settings labels + many helper rows | `engine/ui_overlays/settings_overlay.py:734-747` |
| `text-muted` | `problems-dim` / `(150,150,160,255)` | Problems counts/meta + hints | `engine/ui_overlays/problems_panel_overlay.py:112-113`, `263-264` |

### 2.5 Border & track colors
| Token | Value | Usage | Source |
|---|---:|---|---|
| `slider-track` | `(70,70,80,220)` / `#464650` | Slider base track | `engine/ui_overlays/settings_overlay.py:716-717` |
| `slider-fill` | `(120,180,255,230)` / `#78B4FF` | Slider active fill | `engine/ui_overlays/settings_overlay.py:718-719` |
| `slider-knob-idle` | `(220,220,230,230)` / `#DCDCE6` | Slider knob idle | `engine/ui_overlays/settings_overlay.py:721` |
| `slider-knob-drag` | `(255,220,120,230)` / `#FFDC78` | Slider knob while dragging | `engine/ui_overlays/settings_overlay.py:721` |
| `input-focus-border` | `(90,120,170,180)` / `#5A78AA` | Focused text-input outline | `engine/ui_overlays/find_everything_overlay.py:328-335` |
| `input-idle-border` | `(85,85,95,120)` / `#55555F` | Unfocused text-input outline | `engine/ui_overlays/find_everything_overlay.py:328-335` |

### 2.6 Interactive states
- `selected-row` is implemented (blue translucent fill) in list overlays: `engine/ui_overlays/find_everything_overlay.py:409`, `engine/ui_overlays/scene_browser_overlay.py:384`, `engine/ui_overlays/problems_panel_overlay.py:184-191`.
- `drag-active` is implemented for slider knobs (color swap): `engine/ui_overlays/settings_overlay.py:721`.
- `focused-input` border is implemented in search overlays: `engine/ui_overlays/find_everything_overlay.py:333`, `engine/ui_overlays/scene_browser_overlay.py:306`.
- `hover`, `pressed`, and globally unified `disabled` visuals are **not consistently standardized** across widgets/overlays.  
  `TBD — needs director adjudication`.

---

## 3) Typography

### 3.1 Font face
- Core editor overlays use monospace fallback stack `("Consolas", "Courier New", "Courier")`:  
  `engine/ui_overlays/settings_overlay.py:738`, `engine/editor/editor_overlay_controller.py:79`, `engine/editor/editor_overlay_controller.py:149`.
- Feedback toast overlay pins `font_name="Consolas"`:  
  `engine/ui_overlays/editor_feedback_overlay.py:180`.

### 3.2 Size scale in active use
| Size | Typical usage | Source |
|---:|---|---|
| `10` | Status/meta/hints/footer counters | `engine/ui_overlays/problems_panel_overlay.py:113`, `288`; `engine/ui_overlays/find_everything_overlay.py:438-455` |
| `11` | Main list text + compact headers | `engine/ui_overlays/problems_panel_overlay.py:101`, `123`, `156`; `engine/ui_overlays/find_everything_overlay.py:346`, `426` |
| `12` | Settings labels, slider labels, modal prompt lines | `engine/ui_overlays/settings_overlay.py:329`, `735-747`; `engine/ui_overlays/confirm_modal_overlay.py:60`, `97` |
| `13` | Tour body copy | `engine/editor/editor_overlay_controller.py:158` |
| `14` | Confirm modal title, settings overview/options label rows | `engine/ui_overlays/confirm_modal_overlay.py:38`; `engine/ui_overlays/settings_overlay.py:356`, `368` |
| `22` | Play/build center overlay title text | `engine/editor/editor_overlay_controller.py:76`, `105` |
| `30` | Pause title | `engine/ui_overlays/pause_menu.py:131` |

### 3.3 Weight conventions
- Bold title treatment is explicit in confirm modal title (`bold=True`): `engine/ui_overlays/confirm_modal_overlay.py:40`.
- Most editor text is normal-weight monospace; no global type token system exists.  
  `TBD — needs director adjudication`.

---

## 4) Spacing scale

### 4.1 Repeated spacing tokens
| Value (px) | Use | Source |
|---:|---|---|
| `2` | Slider label-to-track gap; border widths | `engine/ui_overlays/settings_overlay.py:39`, `676` |
| `4` | Default section spacing in labeled-section helper | `engine/ui_overlays/settings_overlay.py:325` |
| `6` | Audio/input row spacing; short right/left panel pads | `engine/ui_overlays/settings_overlay.py:69`, `85` |
| `8` | Panel padding and toast stack gap | `engine/ui_overlays/settings_overlay.py:73`, `89`, `94`; `engine/ui_overlays/editor_feedback_overlay.py:26`, `28` |
| `10` | Min scrollbar thumb height | `engine/ui_overlays/confirm_modal_overlay.py:81`, `engine/ui_overlays/problems_panel_overlay.py:252` |
| `12` | Feedback horizontal pad + common small insets | `engine/ui_overlays/editor_feedback_overlay.py:27` |
| `16` | Feedback viewport inset | `engine/ui_overlays/editor_feedback_overlay.py:25` |
| `18` | Line height baseline in find/scene browser and problems | `engine/ui_overlays/find_everything_overlay.py:18`; `engine/editor/scene_lint_model.py:16` |
| `20` | Confirm modal row-height + title/body spacing unit | `engine/ui_overlays/confirm_modal_overlay.py:20`, `22` |
| `24` | Modal text inset; panel edge inset in find overlay | `engine/editor/editor_unsaved_changes_controller.py:179-180`; `engine/ui_overlays/find_everything_overlay.py:155`, `180` |

### 4.2 Row heights and component heights
| Component | Height rule | Source |
|---|---|---|
| Scroll rows (find/scene) | `int(LINE_HEIGHT)` where `LINE_HEIGHT=18.0` | `engine/ui_overlays/find_everything_overlay.py:18`, `27`; `engine/ui_overlays/scene_browser_overlay.py:22`, `27` |
| Scroll rows (asset/keybinds) | Fixed `24` | `engine/ui_overlays/asset_browser_overlay.py:43`, `299`; `engine/ui_overlays/keybinds_overlay.py:52`, `249` |
| Slider row | `28.0` in settings | `engine/ui_overlays/settings_overlay.py:57-59`, `77` |
| Toggle row | `22.0` (rumble toggle) | `engine/ui_overlays/settings_overlay.py:76` |
| TextInput row | `18.0` in widgetized search overlays | `engine/ui_overlays/find_everything_overlay.py:53`; `engine/ui_overlays/scene_browser_overlay.py:53` |

### 4.3 Modal anatomy spacing
- Unsaved modal width clamps to `[360, 520]` with `0.6 * window.width`: `engine/editor/editor_unsaved_changes_controller.py:162`.
- Unsaved modal line layout uses `18px` vertical step: `engine/editor/editor_unsaved_changes_controller.py:163`, `185`.
- Confirm modal width is fixed `600`, line height `20`, min height `200`: `engine/ui_overlays/confirm_modal_overlay.py:19-23`.

---

## 5) Component anatomy

### 5.1 Toast
- Placement: top-right of editor viewport with `16px` inset from viewport top/right: `engine/ui_overlays/editor_feedback_overlay.py:131-132`.
- Stack spacing: `8px`: `engine/ui_overlays/editor_feedback_overlay.py:26`, `160`.
- TTL defaults: info `4s`, warning `6s`, error `8s`: `engine/editor/editor_feedback_controller.py:19`, `22`, `25`; canonical default function `engine/editor/editor_feedback_model.py:29-34`.
- Max visible toasts: `3`: `engine/editor/editor_feedback_model.py:7`.
- Duplicate collapse window: `1.0s`: `engine/editor/editor_feedback_model.py:8`, `68`.
- Fade-out window: `0.3s` (300ms): `engine/editor/editor_feedback_model.py:9`; used by alpha resolver `engine/ui_overlays/editor_feedback_overlay.py:58-67`.

### 5.2 Badge
- Shortcut badge population is explicit allowlist-driven (`_COMMAND_SHORTCUT_BADGE_IDS`), then surfaced via action shortcut text: `engine/editor/editor_commands_registry.py:25-40`, `44-49`, `59`.
- Shortcut normalization format is deterministic `Ctrl+Alt+Shift+Key` ordering and title-cased key aliases (`Esc`, `Enter`, `PageUp`, `F#`): `engine/editor/shortcut_resolver_model.py:16-44`, `86-105`, `113-119`.
- Problems severity badge format is ASCII bracketed tag (`[ERROR]`, `[WARN]`, `[INFO]`): `engine/editor/scene_lint_model.py:354-364`.

### 5.3 Panel row
- Widgetized list row is a `ScrollList` row rectangle with deterministic `row_height`, selected-state boolean, and paired bg/text draw instructions: `engine/ui/widgets.py:544-579`, `581-626`.
- Selected-state visual convention is translucent blue fill in overlay draw pass: `engine/ui_overlays/find_everything_overlay.py:409`; `engine/ui_overlays/scene_browser_overlay.py:384`; `engine/ui_overlays/problems_panel_overlay.py:184-191`.

### 5.4 Modal
- Center-anchored with full-screen dim underlay in unsaved-changes: `engine/editor/editor_unsaved_changes_controller.py:153-167`.
- Confirm modal is center-anchored fixed-width (`600`) with title/body/prompt regions: `engine/ui_overlays/confirm_modal_overlay.py:19-25`, `31-41`, `44-63`, `90-99`.
- Tour modal is center-anchored (`600x220`) with step indicator, body text, and right/left control affordances (`Next/Done`, `Skip`): `engine/editor/editor_overlay_controller.py:132-187`.
- Esc behavior: unsaved cancel route uses Esc/B: `engine/editor/editor_unsaved_changes_controller.py:123-125`; tour skip request is Esc-triggered by input dispatch policy comment + controller method intent: `engine/game_runtime/input_dispatch.py:41`, `engine/editor/editor_first_launch_tour_controller.py:88`.

### 5.5 Slider
- Label/value are rendered above track at `y = bounds.top - 2.0`: `engine/ui/widgets.py:430`, `440`.
- Track height rule: `max(4.0, bounds.height * 0.25)`: `engine/ui/widgets.py:399`.
- Knob width basis: `max(6.0, bounds.height * 0.18)`: `engine/ui/widgets.py:400`.
- Settings overlay refinement (PR #5): knob vertical cap `10px`, and bars moved below label using `2px` label gap: `engine/ui_overlays/settings_overlay.py:39-40`, `306-312`.
- Value text format is integer percent (`"{value_percent}%"`): `engine/ui/widgets.py:423`, `438`.

### 5.6 Button
- Button labels are imperative action phrases in critical modals/workflows:
  - `"Save and Playtest"`, `"Playtest Without Saving"`, `"Cancel"`: `engine/editor/editor_play_controller.py:48`.
  - `"Build for Windows"` action title: `engine/editor/editor_actions_registry.py:747-748`.
- Primary vs secondary visual style is not globally tokenized; text labels and selection brackets are used in places (`[label]` in unsaved dialog): `engine/editor/editor_unsaved_changes_controller.py:141-145`.  
  `TBD — needs director adjudication`.

---

## 6) Voice & copy conventions

### 6.1 Locked patterns that are clearly present
- Empty-state copy in editor panels follows sentence case with terminal period:
  - `"No assets in this folder."`: `engine/editor/asset_browser_panel.py:17`.
  - `"Select an entity to inspect."`: `engine/editor/entity_panels.py:25`.
  - `"No entities in this scene."`: `engine/editor/entity_panels.py:24`.
- Status/hint rows in widgetized overlays are compact, operator-oriented, and deterministic:
  - `"Hints: Tab focus | Ctrl+N/P nav | Ctrl+Enter activate | Enter activates in results"`: `engine/ui_overlays/find_everything_overlay.py:39` (also SceneBrowser/Keybinds/AssetBrowser).

### 6.2 Tour copy format
- Tour content is step-indexed and concise (`Step X / N` + short actionable body): `engine/editor/editor_overlay_controller.py:142`, `153-164`.
- Tour strings explicitly end with concrete actions (e.g., use `Ctrl+P`, `F6`, `Esc`): `engine/editor/editor_first_launch_tour_controller.py:24-36`.

### 6.3 Toast copy format
- Current implementation favors subject-first operation status:
  - `"Build started: Windows player package."`, `"Build complete: {path}"`, `"Build failed: {code}. See {stderr_log}"`: `engine/editor/editor_build_controller.py:77`, `110`, `120`.
- Punctuation is **not fully unified** (some trailing periods, some not), so a strict no-period toast rule is not locked yet.  
  `TBD — needs director adjudication`.

### 6.4 Pluralization/severity text
- Problems panel currently uses compact counts (`E:{n} W:{n} I:{n}`), not long-form plural phrases: `engine/ui_overlays/problems_panel_overlay.py:105`.
- Severity tags are normalized to fixed badge tokens (`[ERROR]`, `[WARN]`, `[INFO]`): `engine/editor/scene_lint_model.py:354-364`.

### 6.5 Constraints that are not universally true yet
- “No exclamations” is **not** globally true (example exists): `"Welcome to Mesh Editor!"` in tour step content `engine/editor/editor_first_launch_tour_controller.py:20`.
- Emoji use appears absent in the extracted editor UI strings sampled here, but there is no explicit hard rule in runtime code.  
  `TBD — needs director adjudication`.

---

## 7) Z-order conventions
Current registered z-order (actual code, not target aspiration):

| Layer | Kind | z | Source |
|---|---|---:|---|
| Editor dock panels (`project_explorer`, `problems`, `inspector`, etc.) | panel | `10` | `engine/editor/editor_panels_controller.py:192-198` |
| Tooltips | overlay | `500` | `engine/editor/editor_panels_controller.py:199` |
| Feedback toasts | overlay | `700` | `engine/game_parts/ui_dispatcher.py:151-156` |
| Command palette | modal | `1000` | `engine/editor/editor_panels_controller.py:133` |
| Keybinds modal | modal | `1500` | `engine/editor/editor_panels_controller.py:139-143` |
| Context menu / project context menu | modal | `2000` | `engine/editor/editor_panels_controller.py:150`, `158-162` |
| Confirm modal | modal | `2500` | `engine/editor/editor_panels_controller.py:173-177` |

---

## 8) Animation & timing
- Feedback fade-out: `0.3s` (`FADE_OUT_WINDOW_S`): `engine/editor/editor_feedback_model.py:9`.
- Toast TTL defaults: info `4.0`, warning `6.0`, error `8.0`: `engine/editor/editor_feedback_controller.py:19`, `22`, `25` and fallback defaults in `engine/editor/editor_feedback_model.py:29-34`.
- Duplicate collapse timing: `1.0s`: `engine/editor/editor_feedback_model.py:8`.
- Modal open/close transitions are currently immediate state flips (`is_open` / `is_active` toggles) with no generalized easing/tween token set.  
  `TBD — needs director adjudication` (see `engine/editor/editor_unsaved_changes_controller.py:23-25`, `52-54`; `engine/editor/editor_first_launch_tour_controller.py:67-71`, `83-85`).

---

## 9) Iconography
- No unified icon asset system is locked in current editor UI code paths.
- Current “icon-like” affordances are text/ASCII markers:
  - Toggle marker: `"[x]"` / `"[ ]"`: `engine/ui/widgets.py:515`.
  - Severity marker: `"[ERROR]"`, `"[WARN]"`, `"[INFO]"`: `engine/editor/scene_lint_model.py:354-364`.
  - Selection/bracketing: `"[label]"` in unsaved choices: `engine/editor/editor_unsaved_changes_controller.py:141-145`.
- `TBD — needs director adjudication` for a formal icon set, icon sizing grid, and semantic mapping.

---

## 10) Layout patterns
- Editor shell layout is deterministic and rectangle-driven:
  - top bar `48px`, bottom bar `28px`, default dock `320px`: `engine/editor/editor_shell_layout.py:15-18`.
  - splitters `6px`, tab header `32px`: `engine/editor/editor_shell_layout.py:24`, `253`.
- Viewport-centric overlays use shell viewport rect instead of whole window when appropriate:
  - Feedback toasts anchored to `layout.viewport`: `engine/ui_overlays/editor_feedback_overlay.py:128-132`.
- Modal placement convention is centered in viewport/window:
  - Unsaved confirm centering: `engine/editor/editor_unsaved_changes_controller.py:164-167`.
  - Confirm modal centering: `engine/ui_overlays/confirm_modal_overlay.py:25`.
  - Tour modal centering: `engine/editor/editor_overlay_controller.py:129-133`.

---

## 11) Gaps & TBDs
These are extracted gaps, not new proposals:

1. Unified hover/pressed/focus token map across all widgets and overlays.  
   Evidence: only partial local implementations (`engine/ui_overlays/find_everything_overlay.py:333`; `engine/ui_overlays/settings_overlay.py:721`).
2. Formal icon system and icon asset language.  
   Evidence: current ASCII-only indicators (`engine/ui/widgets.py:515`; `engine/editor/scene_lint_model.py:364`).
3. Consistent disabled-state visuals beyond per-overlay text dimming.  
   Evidence: ad-hoc dim usage (`engine/ui_overlays/problems_panel_overlay.py:198`).
4. Modal transition/animation primitives (open/close/focus transition timings).  
   Evidence: direct state toggles, no animation tokens (`engine/editor/editor_unsaved_changes_controller.py:23-25`, `52-54`).
5. Toast punctuation/copy normalization policy (trailing period consistency).  
   Evidence: mixed styles in build feedback (`engine/editor/editor_build_controller.py:77`, `110`, `120`).
6. Severity count long-form phrase standardization (`"1 error"` vs compact `E:1`).  
   Evidence: current compact format in Problems header (`engine/ui_overlays/problems_panel_overlay.py:105`).
7. Primary/secondary button visual differentiation token set.  
   Evidence: text/bracket emphasis but no shared style token framework (`engine/editor/editor_unsaved_changes_controller.py:141-145`).

---

## 12) How to use this document
1. Before changing editor UI visuals, check this document first and align with existing locked tokens/rules.
2. In PR descriptions touching visuals, cite relevant sections and exact source references.
3. If a needed decision is not defined here, either:
   - follow a documented existing convention, or
   - add a scoped update to this document in the same slice.
4. If code and document diverge, reviewers should treat it as design drift and request correction/update.

---

## 13) Revision log
- **2026-05-17** — Initial extraction (`v1`) from merged PR arc #3 through #19 at `1ae9cdd`.
  - Merge commit references reviewed:
    - `b18b10f` (PR #3) editor feedback foundation
    - `1ea808f` (PR #5) slider geometry/layout fix
    - `c77c2a8` (PR #10) shortcut badges
    - `bae8215` (PR #11) palette recency
    - `ab25a83` (PR #12) problems severity badge
    - `421c060` (PR #13) empty states
    - `f652ebb` (PR #16) in-editor playtest
    - `5cd09ac` (PR #17) one-click deploy
    - `1ae9cdd` (PR #19) first-launch tour

