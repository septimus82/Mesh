# Milestone 15, Stage 2: the "Graphite + MeshMind cyan" theme

Branch `redesign/visual-editor` (draft PR #344). This stage carries out the low-risk polish approved after
[Stage 1](milestone15_stage1_visual_direction.md):
- the theme colours, with all the UI chrome colours turned into shared tokens;
- one typeface;
- restrained selection states and button styling;
- panel dividers;
- launcher branding and the application icon.

**Not done (they need a separate decision):** any medium- or higher-risk item, such as the canvas around the map,
recent-project cards, icons or layout changes.

## Owner decisions applied

| Decision | How it was applied |
|---|---|
| **Product name** | "Mesh Studio" for the editor and the launcher (window titles, heading, crash dialog). "Mesh Engine" stays the engine's name. `Mesh Engine.bat` keeps its name. |
| **Branding** | The brain-and-network mark is Mesh Studio's application icon and sits beside the product name. The "MeshMind Studios" wordmark is used only as the publisher's credit. The design and the cyan are the logo's own; only the navy ink is light, for dark surfaces. |
| **Font** | Segoe UI, falling back to Calibri, then Arial. No bundled font. |
| **Logo publication** | Only the adapted assets are committed, in `assets/branding/`, with a `NOTICE.md`: © MeshMind Studios, all rights reserved, not covered by the engine's code licence. The original Downloads file is not committed. The Stage 1 previews with the logo were deleted rather than published. |

## Changes

### The theme (`engine/studio_ui.py`)

- **One place for tokens:**
  - surfaces: `C_BG`, `C_PANEL`, `C_RAISED`, `C_LINE`, `C_BUTTON`, `C_FIELD`, `C_FIELD_EDGE`;
  - text: `C_TEXT`, `C_MUTED`;
  - accent: `C_ACCENT`, `C_ACCENT_DIM`, `C_ACCENT_TEXT`, `C_SELECT`;
  - states: `C_OK`, `C_WARN`, `C_ERROR`, `C_PLAY`, `C_DANGER`;
  - the font: `FONT`.
- **Buttons** have a 1 px outline and quieter hover and press steps, and use the UI font.
- **The selected state** is an outline in MeshMind cyan with a dark-teal fill; it replaces the saturated blue block.
- **Branding helpers:**
  - `brand_texture` (images from `assets/branding`);
  - `set_app_icon` (the icon at 16–256 px).
  - A copy of Mesh without the branding folder still runs, unbranded.

### Studio (`engine/studio.py`, `engine/studio_inspector.py`)

- **Surfaces:** the top bar is one step lighter than the side panels, with 1 px dividers between the top bar, the
  panels and the status bar.
- **Brand:** the mark and "Mesh Studio" sit at the **right** end of the top bar.
  - No toolbar control or click target moved.
  - In a window too narrow for both, the brand is left out.
- **One font:** all labels, fields and map labels use the UI font. Before, buttons were Arial and labels Calibri.
- **Tokens instead of literals:** 17 hard-coded chrome colours now use the tokens:
  - menu and dialog backgrounds;
  - the field fill and border;
  - the status bar;
  - the tile-palette background;
  - picture wells;
  - the warning amber (×9);
  - route problems.
- **Untouched:** the map-overlay colours (zones, doors, routes, handles, the map border) and the canvas around the
  map. Those are medium-risk.
- **Window icon:** set when Studio opens a project. A game run on its own keeps its own icon.

### Launcher (`engine/launcher.py`)

- **Heading:** the mark and "Mesh Studio", with the existing subtitle unchanged.
- **Recent projects:** shown on a panel surface with a divider. The column's position is unchanged.
- **Credit:** "by" and the MeshMind Studios wordmark at the bottom left. A status message takes its place while one
  is shown.
- **Selected template:** outlined in the accent.
- **Window:** titled "Mesh Studio", with the icon.

### The real-window suites (`tooling/acceptance_creator.py`, `tooling/acceptance_launcher.py`)

- They find the launcher by the title "Mesh Studio" and Studio by "Mesh Studio - <room>". Studio's title has always
  had that form, so the two never match each other while one hands over to the other.
- **The suites were not run.** They need your permission to use the desktop. They are the check to run once you
  agree; the Studio and launcher tests below cover the same code headless.

## Before and after

Real hidden-window renders. "Before" is the code at `1f3371a`; "after" is this stage. The launcher uses an isolated
recent list; Studio uses a scratch copy of M14 Check.

| Evidence | Screen |
|---|---|
| [`stage2_launcher_home_before_after.png`](milestone15_evidence/stage2_launcher_home_before_after.png) | Launcher |
| [`stage2_launcher_new_before_after.png`](milestone15_evidence/stage2_launcher_new_before_after.png) | New project |
| [`stage2_studio_yard_before_after.png`](milestone15_evidence/stage2_studio_yard_before_after.png) | Studio, an object selected |
| [`stage2_studio_court_before_after.png`](milestone15_evidence/stage2_studio_court_before_after.png) | Studio, the door panel |

## Checks (headless and hidden-window only)

- Studio and launcher tests (`-k "studio or launcher or ui_ or theme or brand"`): 204 passed, 1 skipped. The skip is
  the GPU wrap test, run in the GPU tier.
- GPU tier: 48 passed.
- New `tests/test_studio_branding.py` (3, fast):
  - the assets and their notice exist;
  - the icon is set from them;
  - a copy without branding still runs;
  - the selected state is outlined in the accent and uses the UI font.
- `tooling/visual_polish_check.py` (M12.2, hidden): 10/10. The door areas are still outlined in Studio and still not
  drawn in the game.
- Gates: type gate ok, ruff gate ok, no `type: ignore`, tier markers ok.

## For your eyes

1. **Open Mesh with `Mesh Engine.bat`.**
   - The launcher should say "Mesh Studio", with the mark and the MeshMind credit.
   - The taskbar and title bar should show the new icon.
2. **Open M14 Check.**
   - The brand should sit at the top right.
   - Selected buttons should be cyan-outlined.
   - All text should be in one font.
   - Every control should be where it was.
3. **Segoe UI at your monitor's scaling.** Is the 10 pt button text comfortable? It was 11 pt Arial before.
