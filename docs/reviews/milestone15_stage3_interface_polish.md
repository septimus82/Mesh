# Milestone 15, Stage 3: Icons & Interface Polish

Branch `redesign/visual-editor` (draft PR #344), building on the accepted Stage 2 theme (`1402ca7`). There are three
changes, each its own commit so each can be judged on its own:

| Part | Commit | What |
|---|---|---|
| 1. Icons | `80d34d4` | A Lucide icon on Studio's and the launcher's buttons |
| 2. Launcher | `e1c902c` | Recent projects as compact cards |
| 3. Canvas | `d977c3c` | The workspace around the map in graphite, with a subdued map edge |

Nothing changed in the engine's runtime, the project format or game rendering. No control moved.

## 1. Icon system

**The choice: [Lucide](https://lucide.dev)** (`lucide-static@1.61.0`), **ISC licence**: permissive, with no visible
credit required. One consistent family: 24-unit grid, 2-unit strokes, round caps and joins. Tabler would have worked
just as well; Lucide had every glyph needed in one style.

**How it fits Mesh, with no new dependency:**
- The 36 SVGs are vendored, unmodified, in `assets/icons/lucide/` with their `LICENSE`; each keeps its `@license`
  comment.
- `tooling/make_icons.py` draws them with Pillow into white 16 and 32 px PNGs. Nothing renders SVG at run time and
  nothing needs the network.
  - Mesh has no SVG renderer, and pulling one in (cairo, resvg) for a few dozen line icons wasn't worth it.
  - The script handles what Lucide uses: paths (M L H V C Q A Z, absolute and relative), circles and rectangles.
- All the code is in `engine/studio_ui.py`:
  - `icon_texture` (cached; `None` if the file is missing);
  - `TintedImage`;
  - `IconButton`;
  - `make_button`;
  - **one table, `BUTTON_ICONS`, maps a button's label to its icon.** Studio and the launcher build buttons as
    before.
- `IconButton` **is a `UIFlatButton`**, with the same text, size and click target.
  - The icon sits left of the text, the pair centred.
  - The icon is **tinted with the button's own text colour**, so every state comes for free:
    - selected: cyan text and icon;
    - disabled: muted, still distinguishable;
    - hover and press: as before;
    - danger: light red.
  - The real-window suites, which click by text and position, see the same buttons.
- **Fallbacks:** a button whose icon is missing, or whose text wouldn't fit beside it, is a plain button.

**Where the icons are:**

| Area | Controls and icons |
|---|---|
| Top bar | Play (play), Save (save), Undo / Redo (undo / redo), Flags (flag), Lighting (lightbulb), AI (sparkles) |
| While playing | Stop (square), Flags, Menu |
| Rooms (the project's maps) | Each room (map) |
| Map tools | Select (pointer), Eraser, Brush, Rect (square), Fill (paint bucket); the tileset button (grid); Import... (image+); Resize... (scaling) |
| Objects | Person (user), Sign (signpost), Empty object (box), Trigger zone (dashed square) |
| Inspector tabs | Look (eye), Animation (film), Collision (scan), Dialogue (speech), Conditions (checklist), Behaviours (sliders) |
| Inspector actions | Choose picture... (image), Import PNG... (upload), Delete object (trash) |
| Launcher | New Project (folder+), Open Project... (folder open), the Recent projects heading (history), Browse..., Back, Create & Open |

**Not given icons, on purpose:**
- **Ground / Walls / Above:** at their 67 px width, "Ground" and an icon don't fit. Rather than widen them (a layout
  change) or mix icon and text-only buttons in one row, the row stays text-only.
- **"+ New room":** it already has its "+"; the text is unchanged because tests click it by name.
- **Brief categories with no control in Mesh Studio:** Move, Events, Sprites/Audio/Scripts/Folders explorers,
  Transform, Settings. No feature was invented to carry an icon.
- **Tooltips:** Studio has none, so none were added or lost.

**The icon set:** `milestone15_evidence/stage3_icon_set.png` shows each icon at 32 px (white) and 16 px (cyan).

## 2. Launcher: recent projects

Each recent project is now one compact card (`studio_ui.CardButton`):
- a folder icon;
- the **project name** (11 pt);
- under it, **where it is** (9 pt, muted). A missing project shows "Missing: ..." in light red on the danger
  surface, with **Remove** beside it as before.
- The card has the theme's border and hover. A long location loses its start, not its end, measured in pixels to fit
  the card.
- A history icon sits beside "Recent projects".

The card is still a button whose text is the project's name, and the whole card is the click target. Opening a
project, the missing-project message, **Remove** and the launcher's layout dump (which its tests read) work as before.

Unchanged: the product name, the application icon, the MeshMind Studios credit, New / Open, the new-project screen.
The only other recent-project data the launcher keeps is the folder, so there's no "last opened" date to show.

## 3. Map canvas

- **Before:** in a lit room, everything outside the map was black (the room's lighting is composited over the whole
  view), with a 2 px white border.
- **After:**
  - Studio draws the graphite canvas (`C_CANVAS`, 90% opaque) over **only what lies outside the map's bounds**,
    after the room is drawn and **before** the editor's overlays.
  - The map's border is a subdued neutral (`C_MAP_EDGE`), with the same width and position.
- Zone, door, route, collision and selection overlays and their labels draw on top as before.
- Anything overhanging the map edge still shows through, dimmed. That dimming is the one visible side effect.
- Rooms without a map get no canvas. Play mode is untouched.

**What does not change:** the map's rendering, coordinates and size; tile placement and editing; picking, dragging,
zooming and panning. It is a draw call between the room and the overlays, nothing more.

**Proof:**
- Stage 2 and Stage 3 Studio renders were compared pixel by pixel.
- Within each map's border, **0 pixels changed**: the yard (683×455 px on screen, its 24×16 tiles at the view's zoom)
  and the court (683×511).
- Outside the map, black (0, 0, 0) became graphite (15, 17, 21).
- Unlit rooms also get the canvas instead of the window colour. The garden was checked the same way: 0 changed
  inside.

## Before and after (hidden windows)

"Before" is the accepted Stage 2 code (`1402ca7`, from a temporary worktree), rendered with the same scratch copy of
M14 Check, the same recent list (one project that exists, one missing) and a fresh editor state.

| Evidence | Screen |
|---|---|
| [`stage3_studio_yard_before_after.png`](milestone15_evidence/stage3_studio_yard_before_after.png) | Studio, an object selected |
| [`stage3_studio_court_before_after.png`](milestone15_evidence/stage3_studio_court_before_after.png) | Studio, the door panel |
| [`stage3_launcher_home_before_after.png`](milestone15_evidence/stage3_launcher_home_before_after.png) | Launcher |
| [`stage3_launcher_new_before_after.png`](milestone15_evidence/stage3_launcher_new_before_after.png) | New project |
| [`stage3_icon_set.png`](milestone15_evidence/stage3_icon_set.png) | The icon set |

## Files

| Kind | Files |
|---|---|
| New: icons | `assets/icons/lucide/*.svg` + `LICENSE`, `assets/icons/*_16.png` and `*_32.png`, `assets/icons/NOTICE.md` |
| New: tooling | `tooling/make_icons.py` |
| New: tests | `tests/test_studio_icons.py` (fast), `tests/test_studio_icons_gpu.py` (GPU), `tests/test_launcher_cards_gpu.py` (GPU), `tests/test_studio_canvas.py` (fast) |
| Changed | `engine/studio_ui.py`, `engine/studio.py`, `engine/launcher.py` |

`studio_ui.py` gains:
- **icon code:** `icon_texture`, `TintedImage`, `IconButton`, `make_button`, `BUTTON_ICONS`;
- **cards:** `CardButton`, with `S_CARD` and `S_CARD_MISSING`;
- **tokens:** `C_CANVAS`, `C_MAP_EDGE`, `C_DANGER_TEXT`, `C_DANGER_EDGE`.

## Automated results

All of these ran, headless or in hidden windows, after all three changes:

- **Type gate:** ok (0 beyond the baseline). **Ruff gate:** ok. No `type: ignore` added anywhere.
- **Fast suite** (`python -m tooling.test_tiers tier0`): **4,344 passed**, 0 failed, 6 skipped (120 s). It includes:
  - the new fast tests;
  - icons present with their sources and licence;
  - the rasteriser on lines, arcs and circles;
  - the canvas's rectangles never reaching into the map and covering exactly the view outside it;
  - no canvas for a room without a map.
- **GPU tier** (hidden): **52 passed**. The new GPU tests:
  - an icon button keeps its text and size;
  - the tint follows the normal, selected and disabled states;
  - it falls back when the icon is missing or too wide;
  - a recent card is a button named for its project, with its location shortened from the start to fit.
- **Studio and launcher tests** (`-k "studio or launcher or ui_ or brand or icon"`): passed during the work, and are
  part of tier0.
- **`tooling/visual_polish_check.py`** (M12.2, hidden): **10/10**. Studio still outlines door areas, and the game
  still draws nothing of them.
- **Map interior, Stage 2 vs Stage 3:** 0 changed pixels in the yard, the court and the garden.

**Real-window suites (run by the owner on the desktop, after Stage 3):**
- **creator:** 21/21.
- **launcher:** at first 1/20. Its step 2 still expected the launcher window to be titled "Mesh Engine"; Stage 2 had
  renamed it "Mesh Studio". After the test's expectation was updated (`74464e3`), 20/20.

## Known limitations

- **The Ground / Walls / Above row has no icons** (too narrow, see above).
- **The icons are 16 px glyphs drawn at 16 px.** They are crisp at Mesh's DPI-unaware scale; on a high-DPI monitor
  Windows scales the whole window, so they soften with everything else.
- **Overhanging objects are dimmed.** Anything placed partly outside the map is dimmed in Studio where it overhangs;
  in the game it is drawn as before.
- **Recent projects show only name and location;** that's all the launcher records.

## Deferred (each needs a separate decision)

- **About dialog.** The MeshMind Studios credit already sits on the launcher.
- **A consistent spacing grid** across the panels.
- **Wider layer buttons**, so Ground / Walls / Above can take icons.
- **Thumbnails in recent-project cards:** a picture of the start room, which needs rendering a room off-screen.
- **Collapsible or resizable panels.**
- **A light theme.**

## Owner acceptance checklist

1. **Launcher:** the recent-project cards (name, location, hover) and the icons on New / Open. Open M14 Check from its
   card.
2. **Studio top bar and left panel:** do the icons read clearly beside their labels?
   - Disabled Save / Undo / Redo: muted.
   - The selected tool or room: cyan.
3. **Inspector:** the tab icons (Look, Animation, Collision, Dialogue, Conditions, Behaviours) and Delete object's
   trash icon.
4. **The map:**
   - The graphite workspace around it, and the quieter border.
   - Paint, erase, select, drag, zoom and pan: do they feel exactly as before?
5. **Play (F4):** the Stop / Flags / Menu bar has icons, and the game looks as before.
6. **(Optional, needs the desktop) the real-window suites:**

   ```
   py -3.13 tooling/runtime_gate.py --owner-present --only launcher creator
   ```

## Owner verdict

**2026-10-24:** the owner reviewed Stage 3 and said it "looks good". Stage 3 is accepted by the owner: the icons, the
launcher cards and the map canvas.
