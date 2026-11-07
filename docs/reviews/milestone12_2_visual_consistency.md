# Milestone 12.2: Visual Consistency, Transitions & Shadow Verification

**Goal:** ordinary games stop showing implementation artefacts: a door object with a round smudge under it,
shadows that don't match what casts them, and wedges at wall joints. This is focused polish, not another renderer.

Branch `redesign/visual-editor` (draft PR #344, unmerged), after `dda5056`.

**Testing rule from this milestone on.** Nothing here moved the mouse or pressed a key on the owner's desktop.
- Every picture comes from hidden windows: the real game window, or Mesh Studio's edit view, made invisible in the
  tool's own process (`tooling/scene_snapshot.py`), or the shadow bench.
- Everything else is headless.
- What still needs a person at the screen is listed under "Deferred".

## 1. Doors and room transitions

**What the owner saw.** A large square object with a round shadow under it.

**What is actually there.**
- *Add door to a new room* (`project_ops.link_rooms`) places a 64×64 door picture (`assets/sprites/door.png`) on the
  floor, with `SceneTransition` (walk-in) and an arrival spot beside it.
- The scene renderer draws a ground "blob" ellipse under every drawn sprite whenever the room's sprite shadows are on
  (the default), whatever the object is. So the door got one, at the fixed blob size: a small smudge under a big
  flat door.
- Arrival spots and objects without a picture were already hidden (no blob).

**One behaviour, three ways to show it.** Nothing is duplicated: every door is still a `SceneTransition`, and its
style only changes what is drawn and how big the trigger is.

| Style | In the game | Trigger | Data |
|---|---|---|---|
| **Door** (default; every existing door) | Its picture (choose another under Look) | The picture's box | no `door_style` |
| **Invisible passage** | Nothing drawn | Its area (default 64×64; fields) | `door_style: "passage"`, `picture_hidden: true`, `area_width/height` |
| **Map artwork** | Nothing extra: goes over a painted door, stairs or opening | Its area (default one tile) | `door_style: "map_art"`, same keys |

- **`picture_hidden`** is generic: any object's picture can be hidden while the object keeps working.
  - The sprite stays `visible`, so touch and press-E still work; the interaction system ignores invisible sprites,
    which is why hiding could not reuse `visible = False`.
  - It is marked `mesh_drawn = False`. The scene renderer skips it, so it gets no ground blob, and the lighting skips
    it, so it casts no lamp shadow.
  - The hidden styles keep the picture, so choosing Door again brings it back.
- **The trigger area.** `SceneTransition` gains optional `area_width` / `area_height`. With both set, walking in is
  tested against that rectangle, not the (hidden or placeholder) picture's box. Without them, it behaves exactly as
  before.
- **Doors never block.** They are not solid, before or after. Walk-in and press-E stay independent switches, and at
  least one must be on.
- **In Studio** (Look tab of a door):
  - "How it shows: Door / Passage / Map artwork", with two short lines of help;
  - area width and height for the hidden styles;
  - "Walk in" and "Press E" switches;
  - the door's note says how the player gets through.
- **On the map.** Hidden doors are outlined, filled faintly and labelled "(passage)" / "(map artwork)", in the editor
  only. They stay selectable and draggable by their area, and arrival spots and linked rooms are unchanged.
- **The operation** is `project_ops.set_door(scene, id, style=, width=, height=, touch=, interact=)`: validated,
  undoable, saved, and available to AI authoring like every op. Its readers are `door_style()` and
  `door_settings()`.

## 2. Ground shadows where they belong

The default for the small shadow under an object is now decided by what the object is
(`sprite_shadow_model.ground_shadow_default`):

| Object | Shadow under it by default |
|---|---|
| Players, NPCs, props on the floor (barrels, signs, rocks as objects) | **yes**, unchanged |
| Doors and every `SceneTransition` (any style) | **no** |
| Arrival spots, objects with a hidden picture | **no** |
| Objects without a picture (zones, markers) | not drawn at all, as before |

- An object's own `shadow_enabled` still wins. Look → "Under feet" now shows the effective value
  (`project_ops.has_ground_shadow`) and stores only a choice that differs from the default.
- Contact shadows were not switched off globally, and Milestone 12.1's lamp shadows are unchanged: only players and
  NPCs cast them by default, and hidden objects never do.

## 3. Shadow shapes: what was really wrong

Each claim was reproduced before anything was changed, and the actual images examined. Two harnesses were used:
- **The shadow bench** (exact pixels against what the renderer should draw). Scenarios: inside and outside L corners,
  an L of tiles, a lamp in the corner, two lamps on one joint, each at Sharp, Soft and Softer.
- **The real game's room render** (`scene_snapshot`).

### A. Round objects with angular shadows: **real, fixed**

- **Cause.** Every tile on the walls (collision) layer became a whole-tile rectangle occluder, merged into strips.
  The starter tileset's Fence, Rock, Bush and Tree tiles are about half see-through, so a round rock cast a square
  block (`a3_rock.png`) and a bush a square-based wedge (`a2_door_and_bush.png`).
- **Fix** (`engine/lighting/occluders.py`).
  - A wall tile that is less than 90% drawn casts the convex outline of its drawn pixels, cut down to 12 corners at
    most. Rock, Bush and Tree become 12-sided outlines, Fence an 8-sided bar.
  - The outlines come from the tileset image, cached per tileset file.
  - Solid tiles are unchanged: whole tiles, merged.
  - Without a findable map file, everything is exactly as before.
- **Water.** It was on the walls layer, so a pond threw wall shadows. The starter tileset now marks Water
  `casts_shadow: false`, and any tileset can mark a tile that way.
- **Cost.** One small polygon per see-through tile instead of part of a strip. The Yard room went from 30 to 45
  shadow polygons; triangle count and timing are in Performance.
- **Entity outlines.** `occluder_poly` on objects was already exact. No round (circle) occluder type exists, and a
  12-corner outline is visually round at tile sizes.

### B. Corner joints with partial wedges: **real, two causes, both fixed**

The Milestone 12 corner fixes hold: inside and outside L, joined tiles, a lamp by a corner, and two lamps on one
joint are all exact at Sharp (0 wrong pixels). Two defects were outside what M12 tested.

1. **An L of wall tiles shadowed its own face.**
   - The loader merges an L into two touching rectangles (a vertical strip on a horizontal one). M12 made a rectangle
     never shadow itself, but one rectangle's shadow still fell across the face of its neighbour, leaving a dark
     triangle at the joint at every edge style (`a4_wall_joint.png`).
   - The M12 GPU tests skipped points inside walls, so it went unseen.
   - **Fix** (`engine/lighting/shadows.py`): rectangles that touch form one wall, and each one's shadows have the rest
     of its wall cut out. Convex pieces are clipped against rectangles, so the triangle fan still applies.
   - Another wall's shadow still falls on a wall: a pillar behind a wall stays dark (tested).
   - The new test fails on the old code at all four lamp positions (1 to 9 of 18 face points shadowed) and passes
     now.
2. **A soft lamp beside a wall leaked light behind it.**
   - Soft and Softer sample the lamp as a disc of points. Near a wall some points fall inside it, and a point inside a
     wall casts no shadow of that wall (M12's rule). Those samples lit everything behind the corner, giving fans of
     light wedges.
   - Measured: 2,506 of 5,101 pixels wrong for a lamp in an L's corner at Softer (`a5_softer_corner_leak.png`).
   - **Fix** (`light_compositor._lamp_points`): sample points inside a wall are not light sources, and the remaining
     points carry the whole shadow. A point lamp (Sharp) is unchanged.
   - After the fix: 1 of 5,101 pixels off, a shadow-edge pixel.

**After, every scenario at every style** (`tests/test_shadow_corners_gpu.py`, hidden window): at most 1% of pixels
differ by more than 6 levels, all of them on a shadow's exact edge. The same tests fail on the old code at the
corner.

## 4. The practical check

`tooling/visual_polish_check.py` builds one disposable room and renders it in hidden windows, as the game and in
Mesh Studio. The room has:
- a door (picture);
- an invisible passage through a gap in the left wall;
- a map-artwork door over an opening painted in the top wall;
- a villager, a rock and a bush on the walls layer, an L of wall tiles, and two lamps.

Last run: **10/10**.

| Check | Result |
|---|---|
| The door is drawn, with no blob under it | pass |
| Passage and map-artwork door: present (can be walked into), not drawn, no shadow of either kind | pass |
| Player and villager keep their ground shadows; only they cast lamp shadows | pass |
| Arrival spots not drawn | pass |
| Rock and bush cast outlines (polygon occluders), the walls rectangles | pass |
| The passage areas are identical, pixel for pixel, to the same room without the passages | pass (difference 0) |
| Door areas outlined in Studio, not in the game | pass |

**Pictures** (`milestone12_2_evidence/`):

| File | Shows |
|---|---|
| `a1_room_before_after.png` | The room in the game, before and after |
| `a2_door_and_bush.png` | The blob under the door gone; the bush's outline shadow |
| `a3_rock.png` | The rock: square block, then its own outline |
| `a4_wall_joint.png` | The L's face: shadowed triangle, then clean |
| `a5_softer_corner_leak.png` | Softer lamp by a corner: light wedges behind the walls, then none |
| `a6_studio_passage_selected.png` | Mesh Studio: the passage selected, "How it shows", both hidden doors outlined and labelled |
| `a7_game_without_passages.png` | The reference room for the pixel comparison |

**Inspection of the pictures.**
- The room reads as a game: a door in a doorway with no smudge, openings in the walls with nothing over them, and
  round things casting round-ended shadows.
- Wall faces are clean, and characters stand on their contact shadows.
- No editor symbols in the game: no outlines, labels or arrival markers.

## 5. Performance

- **Tile outlines.** They are built once per tileset (cached). The Yard room went from 8 occluders / 30 shadow
  polygons / 110 triangles to 8 / 45 / 140.
- **Wall-joint clipping** runs when a light's shadow cache is built, not every frame. It is O(n²) over that light's
  nearby rectangles, which are merged strips, so few.
- **Soft samples inside walls** cost nothing extra; they are simply dropped.
- **The 12.1 bench rooms re-run in the hidden window:** see `tests/test_shadow_*_gpu.py`, 46/46 pass. No new
  per-frame cost appears there.

## Tests

**Headless.**
- `tests/test_door_presentation.py` (6): styles, keeping the picture, areas, refusals, ground-shadow defaults,
  stored-only-if-different, and the passage area trigger.
- `tests/test_shadow_shapes.py` (8): tile outlines and water, occluders from a scene on disk (outline, merged walls,
  fallback), the L never shadowing its own face from four lamp positions, another wall's shadow still falling on a
  pillar, and soft-lamp points.
- The related suite: 5,900 passed.

**Hidden-window GPU** (`MESH_GL_SMOKE=1`). `tests/test_shadow_corners_gpu.py` (13), plus the existing character,
compositing and geometry GPU tests: **46/46**.

**Hidden-window real renders.** `tooling/visual_polish_check.py`: **10/10**.

## Deferred (needs someone at the screen; not run)

Per the new rule, no real-window suite was run. Unverified by a person:
- **Walking through a passage in a live play-test.** The trigger is unit-tested with real `SceneTransition` code, and
  the room loads and renders with it; the walk itself was not driven.
- **Mouse work in Studio:** dragging a passage by its area, and typing the area fields.
- **The existing runtime gate suites.**
  - `shadow_lab`, `lighting_polish_lab`, `lighting`, `creator`, `map_tools` and `event_authoring` cover lighting and
    door flows the changes touch.
  - Their pixel expectations (shadows of walls, doors) may move slightly where a joint or a see-through tile is
    involved.
  - Run them when the owner allows: `py -3.13 tooling/runtime_gate.py --only shadow_lab lighting_polish_lab lighting creator`.

## Compatibility

- **Existing doors keep working unchanged** (style Door, picture box trigger), but lose the blob under them. That is
  the intended fix; Look → Under feet brings it back.
- **Existing rooms' see-through wall tiles** (Fence, Rock, Bush, Tree) now cast their outlines instead of squares.
- **Water in existing projects still casts.** Each project has its own copy of the starter tileset; new projects get
  the marked one. To fix an existing project, add `casts_shadow: false` to its Water tile.
- **Wall joints and soft lamps near walls look different**, as intended.
- **New optional keys** `picture_hidden`, `door_style` (entity) and `area_width/height` (SceneTransition). Schema and
  loader are updated; absent means the old behaviour.

## Remaining visual limitations

1. **Softer has visible streaks.** At Normal quality it still shows the lamp's discrete sample points as faint streaks
   far behind a wall; High quality reduces them.
2. **Outlines are convex.** A C-shaped or hollow tile casts its convex hull.
3. **No door-picture choices beyond the starter door.** Any picture can be chosen under Look; there is no door set
   yet.
4. **Studio labels near the map edge are clipped.** A passage at the map edge has its label partly outside the view.
5. **Some small Studio labels lose a letter or split a word when they wrap.** Seen while checking this panel and
   avoided there with short lines; it is a UI-toolkit quirk, not investigated.
6. **Contact shadows are still a fixed-size ellipse.** Under large props they look small. Look → Under feet turns them
   off per object.
