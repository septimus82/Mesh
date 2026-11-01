# Milestone 15, Stage 1: Visual Direction for Mesh Studio

Branch `redesign/visual-editor` (draft PR #344). **This is a design proposal only:** no editor code has changed.
Implementation waits for the owner's approval.

## How the previews were made

The previews are the **real launcher and the real Studio**:

- Each was rendered in a hidden window, with the proposed theme patched into that process only.
- The Studio previews use a scratch copy of the M14 Check project.
- Nothing is a static mock-up, and no test touched the desktop.

So every preview shows something the existing `arcade.gui` widgets can already draw, with no new UI framework.

Evidence: [`milestone15_evidence/`](milestone15_evidence/).

| Image | What it shows | In the repo? |
|---|---|---|
| `palette.png` | The proposed palette | Yes |
| `launcher_new_now_vs_proposed.png` | New-project screen | Yes |
| `launcher_home_now_vs_proposed.png` | Launcher home | Local only: contains the logo (see below) |
| `studio_yard_now_vs_proposed.png` | Studio, an object selected | Local only: contains the logo |
| `studio_court_now_vs_proposed.png` | Studio, the door panel | Local only: contains the logo |
| `logo_usage.png` | Logo variants and rules | Local only: contains the logo |

The repository is public. Images showing the MeshMind Studios logo stay out of git until the owner agrees to publish
it.

## 1. Direction: "Graphite + MeshMind cyan"

A quiet, dark professional workspace, close to modern code editors and Godot's 4.x look, but simpler. The rules:

- **Surfaces carry no colour.** Separation comes from a few graphite steps and thin divider lines, not from blocks of
  colour.
- **One accent, the logo's own cyan.** It means only "selected / focused / where you are".
- **Green is only for Play / Create.** Red is only for deleting and for problems.
- **One typeface throughout.**
- **The map is the brightest thing on screen.**

No gradients, no ornament, no fantasy framing.

## 2. Palette

| Token | Hex | Use |
|---|---|---|
| canvas | `#111317` | Behind the map |
| bg | `#15171C` | Window, status bar |
| panel | `#1B1E24` | Side panels |
| raised | `#22262E` | Top bar, menus |
| line | `#2C313A` | 1 px dividers and button outlines |
| button | `#282D36` | Buttons and fields |
| text | `#E4E8EE` | Text |
| muted | `#8A92A0` | Help and captions (about 5:1 on panels) |
| accent | `#009CF0` | MeshMind cyan, sampled from the logo (`#0098F0`–`#00B0F8`): selection, focus |
| accent dim | `#103E5C` | Fill of a selected button, tab or toggle (with the accent outline) |
| play | `#1C8C60` | Play, Create & Open |
| ok | `#6ECD96` | Confirmations |
| error | `#F06E64` | Problems |
| danger | `#462224` | Delete (with a red outline and light-red text) |

Today the palette is about as dark, but it has no dividers and selection is a heavy mid-blue block (`#306EAA`).
Most of the improvement comes from the dividers and the outline-plus-tint selected state.

## 3. Typography

Today every screen mixes two fonts:

- buttons fall back to **Arial**, because arcade's default "Kenney Future" isn't loaded;
- labels use **Calibri**.

Proposal: one UI font, **Segoe UI** (the Windows system font; falls back to Calibri, then Arial), in four sizes:

| Size | Weight | Use |
|---|---|---|
| 26 | Semibold | Launcher title |
| 13 | Bold | Product name and panel sections ("Rooms", "Map", "Shadows") |
| 10–11 | Regular | Buttons and fields |
| 10 | Regular, muted | Help and captions |

Nothing goes below 9. Bundling Inter (OFL licence) instead is an option if Mesh ever needs identical text on other
platforms.

## 4. The logo: where it goes

**Finding.** The logo file (`Downloads\MeshMind Studios-logotyp.png`, 1254×1254, transparent) has near-black navy
ink. On any dark surface the brain outline and "Mesh" almost vanish (`logo_usage.png`, left).

**Proposal.** Use a **light-ink variant**: the navy becomes `#E2E8F0`, and the cyan stays exactly the logo's own.
Two crops come from it:

- **The mark** (brain and network, no lettering);
- **The wordmark** ("MeshMind STUDIOS").

**MeshMind Studios** is the maker and **Mesh Studio** is the product:

| Place | Shows |
|---|---|
| Studio, top-left of the top bar | The mark (about 30 px) + "Mesh Studio" |
| Launcher title | The mark (about 56 px) + "Mesh Studio" / "2D RPG engine and editor" |
| Launcher footer | "by" + the MeshMind Studios wordmark (about 136 px wide) |
| Window and taskbar icon | The mark |
| About dialog and a splash, if added | The full lockup with the wordmark |

**Never:**

- on buttons, panels or the map;
- the original dark ink on a dark surface;
- the cyan recoloured;
- the mark smaller than 24 px, or the wordmark narrower than 120 px.

## 5. What most needs improving (found by inspecting the current UI)

1. **Mixed fonts.** Arial buttons beside Calibri labels on every screen.
2. **No surface hierarchy.**
   - The top bar, both side panels and the window are one flat colour, with no dividers.
   - The status bar is a separate hard-coded black.
3. **Heavy selected state.** A saturated blue block, used for tabs, tools, rooms and toggles alike.
4. **The launcher has no identity.** A plain "Mesh Engine" title, a large empty right half, and recent projects
   shown as bare buttons with raw paths.
5. **A black void around the map.** The room's lighting darkens everything outside the map to black, and the map's
   2 px white border is harsh.
6. **No app icon.** The window and taskbar show pyglet's default icon.
7. **42 colours hard-coded** in `studio.py` (32), `studio_inspector.py` (10) and the launcher (2), instead of the
   shared tokens in `studio_ui.py`.
8. **No icons.** Every tool is a text button. That's fine at this size; icons are a later, separate step.

## 6. Risk tiers

**Low risk: visual polish.** The theme lives in one module, so this is mostly tokens; no layout or workflow changes.
Everything in the previews:

- the palette (`studio_ui.py` tokens);
- one font;
- outlined buttons and the outline-plus-tint selected state;
- panel dividers;
- the top-left product mark;
- the launcher title block and its MeshMind credit;
- the window icon;
- the light-ink logo assets in `assets/branding/`.

Checks: the existing Studio and launcher tests, plus hidden-window renders. The real-window suites only read widget
text and positions, and these changes don't move positions, apart from the top bar shifting 150 px right.

**Medium risk: layout cleanup.** Small layout changes, but they touch drawing and spacing:

- a neutral graphite canvas around the map instead of black, and a softer map border;
- the 42 hard-coded colours turned into tokens;
- one 8 px spacing grid and consistent section headers;
- recent projects as cards (name, path, last opened, a thumbnail from the start room);
- an About dialog.

The real-window suites click by position, so a layout change needs one owner-approved real-window run.

**Higher risk: UI rework.** Real redesign work, each item its own decision:

- icon buttons for tools (a licensed icon set such as Lucide or Tabler, MIT);
- resizable or collapsible panels;
- a splash screen;
- re-flowing the right-hand inspector;
- a light theme.

## 7. Recommendation

**Do the low-risk polish pass next, as Stage 2.**

- It is all of what the previews show, and most of the "real commercial tool" feel.
- It reuses the existing widgets.
- It's reversible.
- The previews show it can be built, because they are the real UI.

Then live with it, and decide whether a **larger editor refresh milestone** (canvas, launcher cards, icons) is
worth doing. Don't start with the higher-risk tier.

## Owner decisions needed before Stage 2

1. **Product name.** The launcher window, its title and `Mesh Engine.bat` say "Mesh Engine"; the editor is
   "Mesh Studio".
   - Proposal (as previewed): "Mesh Studio" for everything the user sees.
   - "Mesh" stays the engine's name.
   - The `.bat` file name can stay.
2. **The mark.**
   - **A (previewed):** the brain-and-network mark also serves as the app and product glyph, beside the
     "Mesh Studio" name.
   - **B:** keep the mark only for MeshMind Studios credits and show the product as text only.
3. **Font.** Segoe UI (system, Windows) or bundled Inter.
4. **Publishing the logo.** The repository is public. Adding the light-ink logo assets (and these previews) makes
   the logo public.

## Separate housekeeping (owner decisions of 2026-10-24, not part of this redesign)

- **Wheel:** include the redistributable packs a pip install needs, after checking licences and size.
- **Pause menu:** remove the obsolete "Soft Shadows" toggle; older saved settings that contain it must still load.

Both are recorded in `MESH_REBUILD.md`, to be done as their own changes.
