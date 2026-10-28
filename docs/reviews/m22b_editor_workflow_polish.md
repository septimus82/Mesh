# Milestone 22B: editor workflow polish (Ctrl+S while typing, a scrolling left panel)

Two Mesh Studio defects found while building Lakeside Village. M22B is based on `redesign/visual-editor` at `c42cec0` (#410).

Every check below drives the real Studio in a hidden window with its own input events: clicks, typing, key presses and the mouse wheel. The tool is `tooling/studio_workflow_polish.py`, with phases `ctrl_s` and `left`. It ran on the unchanged base for the "before" record and again after the change. Evidence is in `m22b_evidence/`.

## 1. Ctrl+S while a field is being edited

### Before (base `c42cec0`, `before_ctrl_s.json`)

`Studio.on_key_press` handled every key itself while a field was focused (`_typing()`), and Ctrl+S was not one it knew.

- **Camera pitch:** typed 38, pressed Ctrl+S. Nothing happened: the message stayed "Editing Meadow.", the file kept 30, and the room reopened with 30.
- **Sound emitter volume:** typed 35, pressed Ctrl+S. Nothing was saved (the file kept 0.8), while a stale "Saved 1 file(s)." from an earlier Save stayed on screen.
- **Invalid text:** typed "loud" with a rename waiting, pressed Ctrl+S: ignored. After Esc and Ctrl+S, `save()` committed "loud", which was refused ("Volume: a number from 0 to 100."). The panel rebuilt with the old 80, and `save()` went on to write the rename and say "Saved 1 file(s).". The typed value was silently lost, under a success message.

The cause of the last one: `_flush_fields()` marked every field committed *before* running its commit, and ignored whether the commit refused the value. `save()` then saved regardless.

### The change (`engine/studio.py`)

- **Ctrl+S while typing** calls `save()` and then re-focuses the same box (it's found again by its key after the panel rebuilds). The key never reaches the held-key set, so S doesn't move the 3D view.
- **`_flush_fields()` returns whether every changed field was accepted.** A commit that refuses says why through `_say(ok=False)`, as every Studio commit does (`_edit`'s OpError, the number fields' range checks). `_say` counts those, so a refusal is seen without changing any commit.
  - A refused field is not marked committed.
  - If its commit rebuilt the panel, the box comes back with what was typed, still uncommitted. This holds only in the same room, panel and selection.
- **`save()` returns a result.** When a field was refused it writes nothing (other changes included) and says "Not saved. *reason* Correct the box, or click it and press Esc to put back what it was." It returns False, and the close-window "Save" choice then doesn't close.
- **Esc in a refused box** puts back what the box had and says "Put back as it was.". Esc elsewhere is unchanged.
- **Undo and redo are unchanged.** A committed field is still one undo step, as with Enter.
- **Every Studio text box now has a key.** The two behaviour-parameter boxes (numbers and text; lists) had none, and got one in M22B, so a refused value is kept in any box.

### After (`after_ctrl_s.json`)

- **Camera pitch:** 38, then Ctrl+S, without leaving the box. Studio's own save ran exactly once and said "Saved 1 file(s).". The box was still focused with 38, the file had 38, and the 3D view was unchanged right after and 20 frames later. Closed and reopened: 38.
- **Sound emitter volume:** 35, then Ctrl+S: the file had 0.35, and the box stayed focused.
- **Invalid "loud" with a rename waiting, then Ctrl+S:** "Not saved. Volume: a number from 0 to 100. …" in red. The box still showed "loud", focused. The room was still unsaved, and neither the rename nor the volume was written.
- **Esc:** "Put back as it was." and the box showed 35. **Ctrl+S then** saved the rename ("Stream") with nothing unsaved. **Undo** brought the name back to "Brook" and marked the room unsaved, as before.

## 2. The left panel scrolls

### Before (`before_left.json`, `before_left_*.png`)

The test project was a starter project with an HD-2D room, 14 more rooms and 30 more objects.

| Window | Left-panel buttons built | Below the window |
|---|---|---|
| 1280 × 720 | 75 | 56 |
| 640 × 480 | 75 | 63 |

- **No way to reach them:** the wheel over the panel did nothing, there was no "more below" sign, and the last object couldn't be reached at either size.
- **Still clickable out of view:** buttons below the window were still in the UI. A click event at "Extra object 29"'s position below the window armed it.

### The change (`engine/studio.py`, no new UI framework)

- **The left panel collects its rows in the right panel's own `Rows`** and shows them through the same `_scrolled()`: only the rows that fit, from its own scroll position (`left_scroll`), with "^ N more above" and "v N more below" lines.
  - The Map section and the 3D view's sections (camera, Camera and sun..., Wind and motion, Models, Sculpt and paint) add their rows to it one by one, so they scroll row by row.
  - Rows out of view are never built, so nothing out of view can be clicked.
- **The mouse wheel** over the left panel scrolls it and never the view. Over the 2D tile palette it still scrolls the palette. Over the right panel it scrolls only the right panel.
- **Out-of-view leftovers removed:** the 3D view's tooltips, and the palette's hit area, only count what is on screen. So a scrolled-out button shows no tooltip, and a scrolled-out palette takes no clicks.
- **The scroll position** survives rebuilds and room switches, clamped to the new content.
- **A resized window** now lays the panels out again on the next frame (deferred while a box is being typed in). Before, Studio kept the rows for the old size.
- **The test drivers** (`tooling/hd2d_studio_demo.py` `button`/`type_into`, `tooling/hd2d_room_studio._press`) scroll whichever panel holds a control, down and then back up, as a person would.

### After (`after_left.json`, `after_left_*.png`)

| Window | Left-panel buttons built | Below the window |
|---|---|---|
| 1280 × 720 | 17 | 0 |
| 640 × 480 | 10 | 0 |

At both sizes:
- "Extra object 29" isn't in the UI before scrolling, and a click below the window arms nothing.
- One wheel turn over the panel scrolled it, with the 3D view and the right panel's scroll unchanged.
- "Extra object 29" was then reached and armed.

Also checked:
- **Tooltips:** "Turn left" shows its tooltip. Once scrolled out, the same spot shows the tooltip of the button now there ("Reset view").
- **The 2D palette** (a 16-row tileset showing 2 rows): the wheel over the palette moved it down one row and left the panel alone. The wheel over the room list scrolled the panel and left the palette alone.

## Tests

- `tests/test_studio_workflow_polish_gpu.py`, 6 GPU tests (`MESH_GL_SMOKE=1`; integration) on the two tool phases:
  - Ctrl+S in a camera field (saved once, focus kept, view unmoved, reopened);
  - Ctrl+S in a sound emitter's field;
  - invalid text, then Esc, then undo;
  - the left panel at 1280 × 720 and at 640 × 480;
  - tooltips and the 2D palette.
- **Ordinary 2D editing, undo and redo, Play and Stop, saving:** the existing Studio GPU suites, run with the changed drivers (see Gates).

## Gates

- **Default selection:** 10,050 passed, 203 skipped.
- **GPU tier** (`MESH_GL_SMOKE=1`, every GL-gated test): 207 passed and 1 failed. The failure was `test_hd2d_studio_gpu.py`'s "opened" step, which counted "Models..." as offered only if it was built at once. At 1280 × 720 it is now scrolled out of view, as it was below the window before. The check now scrolls to it, as a person would, and that module passes (8 of 8).
- **Headless Studio, HD-2D, project-operation and contract tests:** 670 passed.
- **Ruff gate:** ok. **mypy:** 73 (baseline).
- **Timing:** no timing budget or baseline was changed. The new tests are GPU and `integration` tests, outside the timed `pytest-fast` step.

## Left alone (recorded in `m22_studio_usability_backlog.md`)

- **The 2D palette's height** still comes from an estimate that predates scrolling (2 rows with many rooms or objects). Making it larger changes every 2D room's layout.
