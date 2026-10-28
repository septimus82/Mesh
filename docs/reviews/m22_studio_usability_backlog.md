# M22 backlog: Mesh Studio usability findings

These were found while building Lakeside Village ([`lakeside_village.md`](lakeside_village.md)) and its soundscape (M21B). They're recorded here for Milestone 22 rather than fixed as they came up. Each one was reproduced in a hidden window through Studio's own controls, and the evidence is in those reports.

## High priority (the owner's call after Lakeside Village)

1. **Creating an HD-2D room.** A new room was always a 2D tilemap room; making it HD-2D took a documented edit outside Studio. **M22A** adds an HD-2D choice, with its size, to New room.
2. **Gameplay camera, sun and sky controls.** These were set by the template or by hand. **M22A** adds them in the 3D view's **Camera and sun...** panel.

## Missing

- **The start room.** It can't be chosen in Studio; Lakeside is reached from the template's Village by road.
- **A large tree asset.** The kit's tree is a trunk whose leaves come from the scatter brush; placed as a model, it's a bare trunk.
- **A water-level field.** A water surface's level is wherever it was placed.
- **A lamp brightness field.** HD-2D lamps have size and height, but no brightness.
- **Room music in Studio.** A room's `settings.music` can't be set in Studio. M21A's semantics are documented in `docs/audio.md`, but they're reachable only by hand or by AI tools.
- **Weather that changes during play.** Weather is per room; within a room only the particle layer's on/off switch changes it. There's no scripted or timed weather (M21B).

## Found in M22A

- **The left panel doesn't scroll.** In an HD-2D room its sections (3D view, Wind and motion, Models, Sculpt and paint) run past the window's bottom. M22A put its own button high in the panel.
- ~~See it ignores the camera's room edges~~: fixed in #409's review (it goes through the follow camera's `fit_view`).
- **Resizing an existing HD-2D room's ground:** M22A.1 expands flat, unpainted rooms east and north (docs/reviews/m22a1_ground_expansion.md). Still waiting for review: sculpted or painted ground, growing west or south, shrinking.
- **Undo after Save** left the undone rooms marked saved, so their state never reached disk. Fixed in M22A.1 for every edit, not only expansion.
- **A 2D room's Resize leaves its map file at the old size** (the room's own size wins at runtime; Tiled, `ai_ops` tile painting and `brush_report` read the file). Unchanged by M22A.1, which keeps 2D Resize as it was.

## Broken or misleading

- **Scatter is order-dependent, silently.** After a meadow, trees and rocks have no room, and Studio only says "The stroke changed nothing".
- **Import accepts a canopy-less model** (the scatter tree's trunk) without a warning.
- **Arrival spots can't be picked or dragged in the 3D view.**
- **The first light switches 2D lighting to Night** in an HD-2D daylight room. The HD-2D view is unaffected, but the panel says "Night".

## Awkward

- **A Natural pond can be waded by default**, even 1.5 m deep (Walk through it: On).
- **Ctrl+S right after typing in a field didn't save**; the Save button did.
- **Sculpting is by time held**; there's no "raise to N m" except Flatten.
- **A brush stroke works only inside the view**; long paths are several strokes.
- **The kit's bridge is built for cliff tops** (a deck 2 m up); over a stream it needs a typed negative height.
- **Placing a sound refuses spots a character couldn't stand on** (inside a building), though a humming machine could be there (M21B). It's because sounds use the objects' placement check.

## Fixed since: not in this backlog

- **The pause menu's Settings:** slider labels overlapped their bars, and changes raised raw `UI_SETTINGS_SAVED` toasts (Milestone 21B.1).
