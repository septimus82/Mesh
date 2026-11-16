# Mesh Studio: a wheel notch no longer rebuilds the editor

Creator-facing responsiveness. Baseline `3bc48d40` (`redesign/visual-editor`). Evidence:
`docs/reviews/studio_panel_scroll_evidence/`. The earlier finding this follows: `docs/reviews/gpu_test_time.md`.

## 1. The bottleneck, reproduced on the current head

Real hidden Studio windows, Windows 11, physical GPU, Python 3.13, 1280x720 (both panels visible), three runs.
Two projects: the HD-2D starter (two rooms, 45 structures, 6 lights, an elder with an eleven-line conversation), and
the 2D adventure template with the same conversation. Each interaction is measured as the person makes it: the
input handler, then the next update and the next drawn frame, Studio's UI drawn apart from the scene.

Before the change **every** wheel notch over a side panel ran `Studio._rebuild()`: both panels and the top bar,
every row of them, in view or not.

| one wheel notch, HD-2D project | handler | UI layout and draw | scene | to the drawn frame (median / p95) | widgets made | listener bindings |
|---|---|---|---|---|---|---|
| Inspector, a conversation | 252 ms | 102 ms | 7 ms | 362 / 483 ms | 161 | 3,271 |
| Inspector, Look | 174 ms | 72 ms | 4 ms | 249 / 342 ms | 138 | 2,794 |
| Inspector, one light's settings | 209 ms | 68 ms | 4 ms | 281 / 423 ms | 143 | 2,940 |
| Inspector, the model browser | 165 ms | 62 ms | 5 ms | 234 / 329 ms | 140 | 2,896 |
| Tools, Environment (1100x620) | 196 ms | 73 ms | 4 ms | 274 / 412 ms | 148 | 3,072 |

The scene is 4 to 8 ms of each: this is UI construction on the CPU, not rendering. About 30% of the handler is
arcade binding listeners to the new widgets (about 3,000 bindings a notch).

The other interactions rebuild too, and are left as they are by this change (section 6): selecting another object
186 ms, switching an Inspector tab 174 ms, a tools category 139 ms, a property toggle 382 ms (the rebuild, then the
edit and the room reloaded), a lighting control 451 ms, a resize 304 ms to the frame, a room switch 366 ms. Typing
a character is 0.8 ms.

Full tables, both projects, every interaction, medians, p95 and maxima: `before_after.md`.

## 2. The change: a notch shows other rows of the rows the panel has

`_left_panel` and `_right_panel` already build every row of a panel and hand them to `_scrolled`, which shows the
ones that fit from the panel's scroll on. The rows out of view were built and thrown away, a notch later built
again.

Now `_scrolled` remembers, for each side, the rows it was given, the box it showed them in and the space it kept
above them. A wheel notch calls `_scroll_panel`, which commits what is typed (as before) and then
`_rewindow(side)`:

1. takes that side's box out of the window's tree and takes its rows out of the box (arcade stops listening to them
   for that box);
2. leaves no box being typed in and no button looking pressed or pointed at, as after a rebuild;
3. runs `_scrolled` again over the same rows at the new scroll and puts the new box where the old one was, in the
   same place among its parent's children;
4. keeps tooltips, the tile palette and the import preview only where their widgets are now in view.

The other panel, the top bar, the status line and the rows' own widgets are not touched. A row of a long list
(`LazyRow`, the model browser) is made the first time it is shown and kept with its panel's rows.

Subtree replacement was the right tool, not in-place scrolling: arcade lays a box's children out from its child
list, so "other rows" is another child list; and `_refresh_top_bar` already replaces one subtree of the same root.
What had to be checked, and is tested: a removed box must have its children removed too (`UIBoxLayout.remove`
unbinds its listeners; `clear` does not), and the new box must go back at the old index (a menu or question is
drawn over the panels). Nothing has to ask arcade to draw: the new box is given its place by the next layout, and
arcade answers any widget's change of place by clearing and drawing its whole surface (section 3).

### When everything is built again (the invalidation rules)

`_rewindow` refuses, and the notch rebuilds as every notch used to, when the rows kept may not be what a rebuild
would make now:

| condition | why |
|---|---|
| a box holds text typed and not committed (taken or refused) | its commit may change what any row shows |
| the project's revision is not the one the rows were built from | an edit, undo or redo with no rebuild after it |
| another room | |
| the window is not the size they were laid out for | the rows that fit differ |
| the 3D renderer's own limits changed (what it can't draw on this computer) | panels say so; no edit changes it |
| a top-bar-only refresh happened since (`_refresh_top_bar`: a live sculpting stroke) | the panels were left as built before it |
| the window lost the keyboard since | files in the project's folder may differ when the person is back |
| a menu or a question is open over the panels | a rebuild draws it again, on top |
| play mode; rows never built or no longer in the window | |

`_rebuild` itself stays the one place rows are built, and every one of its existing callers is unchanged: a
selection, a tab, a category, a click, an edit, a resize still rebuild both panels.

### State ownership

- `_windows[side] = (rows, box, reserve)`: set by `_scrolled`, emptied at the start of every `_rebuild`.
- `_rows_as_of`: the stamp (`_rows_stamp()`) the rows were built from; set at the end of `_rebuild`, cleared by
  `_refresh_top_bar` and `on_deactivate`.
- `_fields`, `_focusable`, `_held`: unchanged in meaning (every box of the built rows, in view or not).
  `_flush_fields`, `_settle_fields` and `_rebuild_keeping_typed` are not changed.
- `_tips_built`, `_spaces_built`: every tooltip and drawn-over slot the rows have; `hd2d.tips`, `_sheet_space` and
  `_import_space` are those of them in view (`_only_shown`, shared by `_rebuild` and `_rewindow`).
- A widget is "on screen" when it is in the window's tree (`widget.get_ui_manager()`), at any depth. `_on_screen`
  asked `parent is not None`, which is true of a slot inside a row that is not shown.

No widget outlives the `_rebuild` that follows the one that made it, and none is moved between UI managers.

## 3. Four things the verification found

**The test driver's "is this box on screen".** `StudioDriver.type_into` and one assertion in
`studio_workflow_polish.py` asked `field.parent is not None`. That was true of a box in a row out of view only by
accident: the row had been garbage-collected, and arcade's `parent` is a weak reference. With rows kept, the
dialogue acceptance test typed into a box that was not on screen and failed. Both now ask
`field.get_ui_manager() is not None`: the same answer as before on the old code (checked: the whole GPU lane
passes with them), and the right one on the new. **This is a change to a shared test driver; the reviewer should
weigh it.** It changes no latency and no assertion's meaning.

**Live state that is not the project's.** `tests/test_dof_studio_gpu.py` sets the renderer's "depth of field is not
available on this computer" and scrolls to read the panel's note. Kept rows did not have the note; a rebuild on
every notch used to hide that the panel was stale until then. The renderer's limits are now part of the stamp, and
losing the keyboard forgets the rows (the model, picture and sound lists read the project's folder). Other live
state a panel reads without a rebuild following (section 7) stays as built until the next action, as it already
did between any two rebuilds.

**A box that has been pointed at.** arcade repaints a text box's background from its own style when the mouse
enters or leaves it, replacing Studio's colour until the box is built again. A kept box showed that; `_rewindow`
restores Studio's colour (`_field`'s), so a kept panel is drawn as a rebuilt one.

**A line that did nothing.** `_rewindow` first ended with `self.ui.trigger_render()`. Taking it out was one of the
deliberate faults, and no test failed. Not a missing test: arcade's `trigger_full_render`, which every widget runs
when its place changes, walks up to the `UIManager` and asks for exactly that, and the box `_scrolled` returns is
always new and always placed by the next layout (traced: the manager's flag is set from the layout on every
notch). The line is removed rather than kept unproven, the fault retired with it, and a test added that had been
missing either way: several notches in a row with nothing built between, drawn as a rebuild draws.

## 4. Correctness evidence

**Every selective refresh in the existing acceptance tests, checked against a rebuild.** A pytest plugin
(`panel_verify_plugin.py.txt`, not part of the product) wraps `_rewindow`: after each one it snapshots Studio
(every widget's kind, text, place, size, enabled state, style, hover and press state; scroll; scrollbars; tooltips;
palette and preview slots; boxes and their texts; pictures), does a real `_rebuild()`, snapshots again, and fails
the test on any difference. Results in section 8.

**New real-window tests**, `tests/test_studio_panel_scroll_gpu.py` (28):

- a notch over the Inspector, and over the Tools, makes at most the two "more above / below" lines, rebuilds
  nothing, and leaves the other panel's and the top bar's very widgets in place;
- at every scroll position of five panels (a conversation, Look, one light, the model browser, the Tools), with the
  mouse over one of the panel's controls, Studio is what a rebuild at that scroll makes, and the panel is drawn
  pixel for pixel the same;
- several notches one after another, down and back, with nothing built between, in the Inspector and in the
  Tools: drawn pixel for pixel as a rebuild draws;
- both ends are reached, every line of the conversation comes into view, a notch past an end does nothing;
- a control scrolled into view is clicked where it is shown; a control scrolled away and back is the same widget,
  does its own action, and undo and redo follow;
- tooltips are where their buttons are and nowhere else; the import preview is drawn only while its row is in view;
  a long list's rows are made once;
- boxes: typed text is committed once, to its own property, by the wheel (and that notch rebuilds); a box only
  clicked is left, nothing committed, and typing then goes nowhere; a box scrolled out and back keeps its text and
  commits to its own property; a refused value stays in its box through scrolling, blocks leaving, and Esc puts
  back what was there; Ctrl+S after scrolling saves what was typed;
- invalidation: another object, an edit behind the panels, a top-bar-only refresh, the renderer's limits, the
  window losing the keyboard, a menu, a resize, play and back;
- lifetime: no widget and no listener left behind by scrolling or by switching tools and tabs.

**Deliberate faults** (`faults.json`): section 8.

## 5. Before and after

Same workload, same machine, baseline and branch run alternately, three runs each (`before_after.md`,
`bench_before_*.json`, `bench_after_*.json`).

| measurement, HD-2D project | before | after |
|---|---|---|
| Inspector scroll, handler, median / p95 | 252 / 376 ms | **11 / 14 ms** |
| Inspector scroll, to the drawn frame, median / p95 | 362 / 483 ms | **85 / 94 ms** |
| Tools scroll, handler, median / p95 | 196 / 337 ms | **8 / 10 ms** |
| Tools scroll, to the drawn frame, median / p95 | 274 / 412 ms | **44 / 48 ms** |
| widgets made per notch | 138 to 161 | 2 or 3 |
| listener bindings per notch | 2,794 to 3,271 | 120 to 167 |
| full rebuilds per notch | 1 | 0 |
| CPU in the handler per notch | 165 to 252 ms | 8 to 11 ms (-94% to -96%) |
| allocated in the handler per notch | 1.7 to 2.9 MB | 39 to 87 kB |
| traced memory after the scrolling workload | 58.6 MB | 58.7 MB |
| live widgets with a long Inspector open | 129 | 140 (the rows out of view, kept) |
| dialogue GPU acceptance, local | 146.4 s | **86.9 s** |
| lighting-controls GPU acceptance, local | 165.5 s | **101.6 s** |

The 2D project: Inspector scroll 187 / 365 ms to 10.1 / 11.4 ms in the handler, 257 / 434 ms to 53 / 59 ms to the
frame.

One Tools notch in each run of 24 took 127 to 133 ms in the handler (the run's maximum; the others 7 to 10 ms;
before the change the maximum was 346 ms). No rebuild was counted in it. Which notch it is and why was not
investigated; the Tools are measured in a newly opened window with no warm-up, so the first notch is the likely
one.

What is left of a notch, 40 to 70 ms, is arcade laying the whole UI out again and rendering all of it to its
surface (about 27 ms and 46 ms under a profiler, for 134 widgets): it does that whenever any widget moves, a
hovered button included. That is arcade's, and outside this change.

**No interaction got slower.** Means over the three runs, handler, before to after: selecting another object
200.1 to 196.1 ms; an Inspector tab 195.2 to 189.9; a tools category 153.4 to 147.6; a property toggle 405.9 to
406.0; a lighting control 479.2 to 472.1; a resize 22.9 to 23.2 (322.2 to 315.1 to the frame). The two with six
samples a run moved both ways with the project: a room switch +5% in the HD-2D project and -11% in the 2D one; a
scroll with typed text +0% and +6%. Their code paths are the ones before the change (a rebuild; a commit and a
rebuild).

## 6. What this change does not do

- Clicks, selections, tabs, categories, edits and resizes rebuild as before. Those are where the remaining cost
  is (125 to 240 ms each); narrowing them needs per-panel invalidation of what each handler changes, which is a
  larger change to who owns what and should be designed on its own.
- A wheel notch with typed text still rebuilds twice (the commit's own rebuild, then the notch's), as before.
- arcade's full relayout and re-render on any change (above).

## 7. Limits

- **Live state the panels read that is neither the project's nor in the stamp** stays as built across scrolling
  until the next action. Found and covered: the renderer's limits, and (through focus) the project's folder. Not
  found by any test, and not covered if they exist: anything else a row reads that changes while Studio keeps the
  keyboard and nothing rebuilds. Before this change a notch refreshed such a row by accident.
- A kept button that was the last one clicked stays arcade's "active widget" (a flag arcade keeps; it does nothing
  for a button). A rebuilt one is not. For boxes, where the flag means "being typed in", it is cleared.
- Widgets in rows out of view keep the place they were last drawn at. Nothing in Studio reads it (everything asks
  the window's tree), and the two test helpers that did were corrected (section 3). A new helper that takes
  `studio._focusable[key].rect` without asking whether the box is in the tree would click the wrong place.
- Timings are one desktop's. CI figures are in the pull request.

## 8. Verification results

Local, on the code as committed (Windows 11, Python 3.13, a physical GPU), one process at a time:

| check | result |
|---|---|
| `tests/test_studio_panel_scroll_gpu.py` | 28 passed (105 s alone) |
| the GPU lane (`-m gl`, `-W error`, strict markers) | 564 passed, 1 skipped (1,721 s) |
| the same lane with the verifier (section 4) | 1,150 selective refreshes each compared with a rebuild: **0 differences**; 3 more refused and rebuilt |
| deliberate faults (`faults.json`) | **20 of 20 caught**; the unfaulted run passes |
| fast tier | 6,136 passed, 7 skipped |
| full default suite | 11,969 passed, 581 skipped; 3 failed, the known local failures of `tests/test_ci_shards_plugin.py` (this machine's environment, not this change) |
| ruff gate, mypy gate | ok |

The verifier's lane reports 16 failed tests, all in the new module (`verifier_lane_expected_failures.txt`): they
are the tests that assert a notch rebuilds nothing or keeps the very widgets, and the verifier rebuilds after every
notch. The 548 other tests of the lane pass with it.

The faults: every notch rebuilding as before; the stamp ignored, and each of its parts left out (revision, window
size, renderer's limits); a top-bar-only refresh, the window losing the keyboard, and an open menu not counting;
typed text committed without a rebuild, and not committed; a box left being typed in; hover and press state left;
arcade's repaint of a box left; tooltips and slots not looked at again; the box put back last; the rows left in
the old box; the left panel treated as the right; a long list's rows made again; the old "has a parent" test for
on screen; the palette and preview slots kept where a row was.

**The GPU lane's own time.** The new module is 132 s of the lane here; the dialogue and lighting-controls
acceptance tests are 124 s shorter between them. The lane is about as long as it was: this change is for the
person scrolling, and takes nothing off CI.

CI and Extended on the pull request's head: in the pull request.
