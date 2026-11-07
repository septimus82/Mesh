# Watchfire R3: choosing what you edit in the 3D view

A creator-trial fix (*The Last Watchfire*, Major 3). It is not a milestone. Base: `redesign/visual-editor` at `c65a65f`.

## The defect

The trial found two problems in Mesh Studio's HD-2D view:

1. **A placed campfire couldn't be selected again by clicking it.** It couldn't be dragged either. Right-click was the
   only way to reach it.
2. **Overlapping objects couldn't be told apart.** A click always selected the nearest object, and right-click always
   took the newest one at that spot. Anything behind was out of reach. The trial worked around this by deleting the
   front campfire, editing the other one, and placing the first one again.

## Why

A left click in the 3D view (`Hd2dView.press`) works like this:

- `engine.hd2d.picking.Picker.pick` tests the mouse's ray against the structures' drawn triangles and the drawn
  sprites' billboards, and keeps the single nearest hit.
- Objects without a picture are added by hand: a sound emitter's post, and water's surface (only when nothing else
  was hit).
- Right-click uses `Studio._open_menu`, which picks with the 2D ground box `_entity_at`, newest object first, and
  selects that object.

That gives two causes:

- **Campfires had no hit shape.** A campfire has no picture: its sprite is never drawn, so `renderer._sprites()`
  leaves it out. Its logs and flames are scatter assets placed by `engine.fire`, not structures. Unlike sound
  emitters, nothing tested it, so no click could reach it.
- **Only the nearest object was ever kept.** `pick` returned one hit and right-click reselected the newest, so there
  was no way to reach anything behind.

The selection itself worked. The inspector, the highlight, dragging, undo and saving were all fine for whatever was
selected. Only the choice of what to select was missing.

This was reproduced before any change, on pristine `c65a65f`, with the same real-window tool
(`before_c65a65f_report.json`):

- a click on a campfire selected nothing;
- clicking two overlapping signs three times selected the front sign three times;
- two stacked campfires couldn't be clicked at all;
- right-click selected the newest object.

## The change: click again to choose what's behind

I chose **click-again cycling**. The other two options were rejected:

- **Depth-aware picking alone** already happens (nearest first). It doesn't reach anything behind.
- **An object list** would be a new panel, and a creator already has their eyes and mouse on the spot.

How a creator uses it:

- **Click:** selects the nearest thing under the mouse, exactly as before.
- **Click again without moving:** if more than one thing is under the mouse, this selects the next one behind it.
  Another click goes on to the next, and after the last one it goes back to the front.
- **The status line explains it** whenever several things are under the mouse, for example: "Sign: 1 of 2 here. Click
  again (without moving) for the one behind." On the last one it reads "...for the front one again."
- **Dragging moves what is selected.** If the selected object is under the mouse, pressing on it keeps it selected and
  a drag moves it, even when something else is in front. Before, the front object was always taken.
- **Right-click keeps the choice.** In 3D, if the selected object is under the mouse, its menu is for that object, not
  the newest one there.

Changed files:

- `engine/hd2d/picking.py`:
  - `Picker.pick_all` returns everything the ray meets, nearest first: each structure and character once, where the
    ray first meets it.
  - `pick` is now `pick_all`'s first entry.
- `engine/studio_hd2d.py`:
  - **`_under(x, y)`** builds one ordered list of what's under the mouse. It holds the structures and sprites from
    `pick_all`, plus the markers of objects without a picture (`_markers_hit`): sound emitters' posts, with their
    geometry unchanged, and now campfires.
  - **A campfire's marker** is an upright as tall as its flames, standing where the renderer puts its logs (its
    elevation, else the ground's height), within 0.55 m and sized with the fire.
  - **Order:** each object appears once, and water comes last as before. At the same depth, an object drawn now comes
    before one its "Show when" flags hide.
  - **Selection:** `press` keeps the selection if it's under the mouse, and otherwise takes the nearest. `release`
    without movement selects the next one.
  - **`ids_under`** serves right-click.
- `engine/studio.py`: `_open_menu` keeps the 3D selection when it is under the mouse.

Unchanged:

- the first click's choice;
- placing objects and models;
- Sculpt, Paint and Scatter, which take the click before any picking;
- keyboard shortcuts;
- the inspector and highlight code;
- `project_ops`;
- the game runtime;
- the project format.

There is no new selection subsystem: it is the same `press`, `drag_to` and `release` path, with one list instead of
one hit.

## Evidence (Mesh Studio's real window, its own mouse and keys)

`tooling/watchfire_r3_selection.py` builds a disposable copy of the M23B clearing containing:

- a lone campfire;
- two campfires on one spot, one burning and one not;
- a campfire hidden behind the cottage;
- two signs placed with Objects > Sign, one just behind the other.

Everything else is done in Studio with the mouse and keyboard. The table compares pristine `c65a65f` with the fix.

| Step | Before (`c65a65f`) | After |
|---|---|---|
| Click the lone campfire | nothing selected | Campfire 1, inspector shows it |
| Click where a fire is hidden behind the cottage | cottage | cottage, "1 of 2 here" |
| Turn the selected cottage +90 (inspector) | turns; the fire doesn't move | the same |
| Click there again | cottage | **Campfire 4**, the hidden fire; its box is drawn through the wall |
| Click the two overlapping signs, three times | Sign, Sign, Sign | Sign, **Sign_1**, Sign; inspector follows |
| Drag what is selected, then undo and redo | only it moves; undo and redo work | the same |
| Click the stacked campfires, twice | nothing, nothing | **Campfire 2** (Burning: On), then **Campfire 3** (Burning: Off) |
| Right-click there | selects the newest object | **keeps** Campfire 3; its menu |
| Click empty ground | deselects | deselects |
| Sculpt, Paint, Scatter: click on a campfire | brush stroke, nothing selected | the same |
| Save, close, reopen | positions kept | the same |

Pictures: `before_2_signs_click_2.png`, `before_4_stack_click_1.png`, `after_1_click_lone_campfire.png`,
`after_1d_click_again_the_hidden_fire.png`, `after_2_signs_click_2.png`, `after_4_stack_click_2.png`. The reports are
`before_c65a65f_report.json` and `after_fix_report.json`.

## Tests

- **`tests/test_hd2d_structure_editing.py`** (fast) gains
  `test_pick_all_lists_everything_the_ray_meets_nearest_first_each_once`:
  - a person, the platform and a person behind it come back in that order, each once;
  - `pick` equals the first;
  - an upward ray finds nothing.
- **`tests/test_studio_3d_selection_gpu.py`** (GL-gated) runs the real-window scenario above. Its 7 tests cover:
  - a campfire selected by clicking;
  - front first, then a click again for what it hides, with a structure turned while selected;
  - signs taking turns, with the inspector following;
  - a drag moving only the selection, with undo and redo;
  - stacked campfires, each with its own settings, and right-click keeping the choice;
  - empty ground deselecting, and the terrain brushes never selecting;
  - save and reopen.

  Against the `c65a65f` engine files, 5 of the 7 fail. The 2 that pass are the unchanged behaviours (drag with
  undo/redo, and save/reopen). The empty-ground test fails there only because the old engine can't list what's under
  the mouse; its deselect and brush behaviour is the same. The new `pick_all` unit test fails too, because the
  function doesn't exist there. See `before_tests_on_c65a65f_engine.txt`.

## Compatibility and limits

- **Clicking the selected object again without moving now selects the next object behind it, when there is one.**
  Before, it did nothing. Pressing and dragging is unchanged: it moves the selection.
- **Picking is a little more work:** every structure the ray crosses is now tested against its triangles, not only
  until the nearest one is found. `pick_ms` is still recorded.
- **A campfire's marker is a simple upright,** not its drawn logs and flames. Clicks just beside the flames can miss,
  or can count.
- **Objects hidden by their "Show when" flags:** a campfire is still in the list, after drawn ones at the same depth.
  A pictured object whose sprite isn't drawn is still not pickable in 3D, as before (`renderer._sprites()`).
- **Deferred:**
  - water is still reached only as the last item;
  - there is no object list or search panel;
  - Esc after a right-click still clears the selection (a separate polish item from the trial).
