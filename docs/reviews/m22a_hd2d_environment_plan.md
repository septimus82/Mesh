# M22A: Studio HD-2D creation and environment controls (audit and plan)

These are the two high-priority gaps Lakeside Village found (`m22_studio_usability_backlog.md`): an HD-2D room can't be created in Studio, and its gameplay camera, sun and sky can't be set there. This document is the audit and the plan. The draft PR implements the first slice described below, and stops there for review.

## Audit: what exists today (`redesign/visual-editor` after #408)

**Rooms.**
- `Project.add_room(label)` (`engine/studio_project.py`) always makes a **2D** room: `ops.new_room`, plus a 20 × 15 tilemap with a wood floor and stone-wall border (`ops.add_map`).
- An HD-2D room is a room whose `settings.hd2d` exists. Its ground, structures, camera, sun, ambient and sky all live there (`engine/hd2d/settings.py`, `parse_hd2d`).

**How the template makes one** (`engine/hd2d/starter_village.py`): `_map` (a plain tilemap of the room's size, plus `world_width`/`world_height`); `_hd2d` (ground texture over `from`–`to`, camera, sun `{direction, color, intensity}`, ambient, optional sky); and `catalog.install_kit` (the starter kit's models and textures copied into the project).

**Lakeside Village needed a documented edit outside Studio:** it popped Studio's 2D tilemap and applied those helpers.

**The gameplay camera:** `settings.hd2d.camera`.

| Field | Range or meaning | Default |
|---|---|---|
| `pitch` | 5–89° | 32 |
| `fov` | 5–120° | 30 |
| `distance` | 1–500 m | 15 |
| `ortho` | on or off | |
| `follow` | the tag it follows | player |
| `height` | m above the followed feet | |
| `bounds` | px rectangle it never shows past | |

The template derives `distance` from a "view" (metres of world top to bottom at the player, `OUTDOOR_VIEW` 11.25 m, `INDOOR_VIEW` 7.5 m) and `FOV` 12°.

**The sun:** `settings.hd2d.sun`, either a direction `[x, y, z]` or `{direction, color, intensity}` (intensity 0–10). Plus `ambient` (0–1), `sky` (a colour), and the ambient light's tint (a scene light of type `ambient`).

**Studio today:**
- **None of these can be edited.** The 3D view's camera is the editor's own (pan, zoom, turn), separate from the game's.
- **The Lighting panel** edits the 2D lighting and the lamps.
- **The 3D view's left panel** has Wind and motion (M20E), the only room-level HD-2D setting with controls.
- **No project operation** exists for the camera, sun, ambient or sky (`grep project_ops`). They're set only by templates, by hand, or by AI tools writing whole settings.

## The plan: one small, coherent workflow

**"Make an outdoor HD-2D room, frame it, light it", entirely in Studio:**

1. **New room → HD-2D, with its size.** The "+ New room" panel gains a choice between a **2D map** (as today) and an **HD-2D room**. The HD-2D choice adds **Width × Depth (m)** fields (default 32 × 24, limits 8–256) and **Outdoor / Indoor**.
   - **New op `make_hd2d_room(scene, width_m, depth_m, outdoor)`:** the template's own recipe, moved into `project_ops`. That's a plain map of that size; the ground (the kit's grass) over it; a camera framed for the size; the default sun and sky; `world_width`/`world_height`.
   - **No kit in the project** (a 2D project's first HD-2D room): Studio installs the starter kit first (`catalog.install_kit`, as the template does) and says so.
   - **One undo step for the room.** Its map file is written straight away, as for 2D rooms today.
2. **Ground size afterwards.** **Room size (m)** in the 3D view's section: the ground's extent, the map and the camera bounds follow. **Refused with the reason** on sculpted ground (its heights are a grid of that size; resizing them is a separate job).
3. **The gameplay camera.** A **Game camera** section (3D view, left panel):
   - **Presets:** Outdoor, Indoor, Close, Wide;
   - **Fields:** View (m top to bottom at the player), Pitch (°), Lens (fov °), Height above the player (m), Stay inside the room (bounds on or off), Flat (ortho);
   - **See it:** puts the editor's 3D view where the game's camera would be, at the player's start (with **Back to editing view**), so it's framed before Play.
   - **New op `set_hd2d_camera(scene, **fields)`,** checked by `parse_hd2d`.
4. **The sun, ambient light and sky.** A **Sun and sky** section:
   - **Presets:** Morning, Noon, Evening, Overcast, Night;
   - **Fields:** Sun from (compass °), Sun height (° above the horizon), Sun colour, Sun strength, Ambient light (0–1), Sky colour;
   - **Live:** the 3D view updates as it changes, by updating the renderer's settings in place (as M20E's motion does), with no room reload.
   - **New ops `set_hd2d_sun(scene, azimuth=, elevation=, color=, intensity=)` and `set_hd2d_sky(scene, ambient=, sky=)`.** Azimuth and elevation are kept for the creator; the direction vector the renderer reads is derived from them.

Every change is one checked `project_ops` edit: one undo step, saved with the room, and the same operations AI tools use.

## What M22A does not do

- **Resizing sculpted ground** (it needs the height grid resampled).
- **Indoor rooms with walls**, beyond choosing the indoor camera and ambient.
- **Time-of-day animation**, and the rest of the M22 backlog: the start room, large trees, water level, lamp brightness, the scatter-order message, import warnings, arrival spots in 3D, Ctrl+S in fields, room music in Studio.
- **Changes to existing templates or 2D rooms:** the template keeps building its village the same way. Its helpers move behind the new op, with the same output.

## How it will be checked

- **Ops (fast tests):**
  - a new HD-2D room parses with `parse_hd2d` and matches the template's own output for the same size;
  - the camera, sun and sky ops round-trip;
  - bad values are refused with reasons;
  - resizing sculpted ground is refused;
  - the HD-2D template project is byte-identical before and after;
  - 2D rooms are unchanged.
- **Studio, in hidden windows:**
  - a 2D starter project gets an HD-2D room made in Studio (the kit installed), its size set, its camera and sun changed, then saved, reopened, played (the game's camera matches "See it") and exported;
  - the Lakeside Village copy's camera and sun are edited in Studio;
  - screenshots.
- **Gates:** the default selection, the GPU tier, mypy at 73, the ruff gate.

## The first draft PR

It covers **steps 1, 3 and 4** (create an HD-2D room with its size, the gameplay camera, the sun and sky). Step 2, ground size afterwards, follows only if review agrees: creation already takes the size, and Lakeside's need was the creation.
