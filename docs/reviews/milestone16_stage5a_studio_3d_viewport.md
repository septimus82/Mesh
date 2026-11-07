# Milestone 16, Stage 5A: HD-2D Visual Editing in Mesh Studio

**Verdict: PASS.** When you open an HD-2D room in Mesh Studio, you now see the real 3D room, and you can edit its
structures without touching JSON:

- The canvas shows the Blender structures, pixel-art textures, characters, ground, lighting and shadows. It is drawn
  by the same renderer as Play, through the editor's own camera.
- A click picks in 3D. Characters and structures are separate kinds of selection.
- You can drag a structure across the ground (snapped to 0.5 m), raise it, turn it, and type exact values in metres
  and degrees.
- You can place another copy of a model from the project's `.glb` files, with a preview before it commits.
- Undo, redo, save and reopen work, and F4 plays the edited room.

Every change is one shared `project_ops` operation. That is the same path Mesh Studio, `mesh author` and AI tools use
through the existing review workflow.

The full workflow (Part H) was run in a hidden window, driven only by window input events: mouse, keys, and clicks
on Studio's own buttons.

Branch `feature/m16-stage5a-studio-3d`, from `redesign/visual-editor` at `6b04b6f`, with a draft PR to
`redesign/visual-editor`. **Not merged; it is for owner review.** Stage 5B and Stage 6 have not been started.

## Part A: Stage 4 integration

| Step | Result |
|---|---|
| #354 | 30 files: the lighting work, its tests, tools and evidence. Nothing else. Head `18c22ad`, mergeable. |
| CI | Required checks are green. The full `tests` job has **the identical 26 failures** of the [#352](https://github.com/septimus82/Mesh/issues/352) baseline, in both runs. |
| Final checks | HD-2D fast tests 446 passed. HD-2D GPU tests (Stages 2–4) 17/17. |
| Merge | `6b04b6f`. The merged tree is identical to the PR head. |
| #344 / `main` | Still a draft / untouched. |
| #351, #352 | Still tracked. Not suppressed or re-baselined. |

## Part B: Architecture

All of Studio's editing paths already exist, and the 3D view reuses them.

- **Editing through operations.** Every Studio edit is `Studio._edit(lambda scene: ops.X(scene, ...))`.
  - It produces whole-project snapshots in `Project.edit_scene`: one undo step per edit, with Ctrl+Z / Ctrl+Y.
  - It ends with `_after_change`, which reloads the room through `window.load_scene`.
  - That reload already rebuilds `window.hd2d_renderer`, the one Play uses, because `configure_hd2d_scene` runs on
    every load.
  - Studio simply never drew it in edit mode.
- **AI tools.** They reach the same `project_ops` functions through `engine/authoring.py`.
  - A public op with a `(scene, …) -> Doc | tuple[Doc, str]` signature is registered automatically for MCP
    (`authoring_operations`, `propose_changes`, `apply_changes`) and for `mesh author`.
  - Proposals are dry-run, summarised in words, and accepted by the person in Studio's AI panel.
- **The design** therefore adds no new editor and no new framework:

```
Studio.on_draw (edit mode)
  ├─ 2D room:     unchanged (scene_controller.draw, the 2D canvas and overlays)
  └─ HD-2D room:  Hd2dView.draw()  ->  window.hd2d_renderer.draw(camera=editor camera, viewport=canvas, overlay=grid/boxes)
Studio mouse / keys / wheel  ->  Hd2dView (only while the room is HD-2D; 2D rooms take the old code)
Hd2dView edits               ->  Studio._edit(ops.place_structure / set_structure / remove_structure)  -> undo, save, reload
AI (MCP) proposals            ->  authoring (same ops; model file checked)  -> Studio AI panel -> Accept
```

### Changes

| Where | What |
|---|---|
| `engine/hd2d/renderer.py` | `Camera` gains `yaw`, plus `forward` / `right` / `ray`. The game camera keeps yaw 0, so it is unchanged. `draw(camera=, viewport=, overlay=)` draws into Studio's canvas with any camera and an overlay pass. Billboards face whichever camera is drawing. **Live structures**: `set_live_ids` takes the one being dragged out of the static batch, and `set_live` moves it every frame (shadows included). `set_preview` shows the model about to be placed. `draw_lines` draws the overlay lines through one reused buffer. `gl_objects()` lists every GPU object the renderer holds. |
| `engine/hd2d/picking.py` (new) | 3D picking. A ray from the camera through the mouse is tested against every structure's placed **drawn triangles** (Möller–Trumbore, bounding-box prefilter, cached per transform) and every character's billboard quad. The nearest hit wins, as `Hit(kind="structure"\|"sprite")`. It also provides the structure placement matrix, bounding boxes, and ray / ground-plane intersection. |
| `engine/studio_hd2d.py` (new) | `Hd2dView`: the editor camera, canvas drawing, picking, dragging, the structure inspector, the model list and placement, keys and tooltips. Used only while the open room is HD-2D. |
| `engine/studio.py` | About 60 lines of hooks: draw, left and right panel, mouse press/drag/release/motion/wheel, keys, WASD, reload, select. In an HD-2D room, a click on the map means the 3D ground under the mouse, so object placement and the right-click menu work in 3D. `accept_ai` selects a structure the AI placed. `_after_change` warns when a change buries a character. |
| `engine/project_ops.py` | `place_structure`, `set_structure` and `remove_structure`, plus the lookups `structures`, `find_structure` and `unique_structure_id`. They are pure, deep-copying and validated by `parse_hd2d`. There are clear errors for: not an HD-2D room, a model that isn't a `.glb`, duplicate ids, positions outside the room's ground, bad numbers or scale. Rotation is normalised to 0–360. |
| `engine/authoring.py` | A `model` argument is checked against the project's files (`model_problem`: exists, and is a usable GLB) before any op runs. The review summary now describes structures in words, metres and degrees. |
| `engine/hd2d/glb.py` | `model_problem(root, model)`, shared by Studio and authoring. |

- **Coordinates:** Mesh px throughout, 32 px = 1 m. The inspector shows metres and degrees.
- **Edit vs Play cameras:** the editor's camera lives in the view, and the game's camera lives in each renderer.
  Editing never changes the game's camera.

## Part C to F: The editing workflow

**Opening an HD-2D room.** The canvas shows the 3D room exactly as Play draws it:
- the renderer, lighting and shadows are the same;
- the overlays are a faint 1 m ground grid, a yellow box around the selected structure (dimmed where something hides
  it), a blue box on a selected character, and a cyan box on a model being placed.

**Camera** (left panel, "3D view"):

| Action | Button | Mouse or key |
|---|---|---|
| Turn left / right | Turn left / Turn right | Q / E |
| Tilt | Tilt up / Tilt down | |
| Reset to the whole room | Reset view | Home |
| Frame the selection | Frame it | F |
| Zoom | | Wheel |
| Pan | | Middle-drag, or WASD / arrow keys (relative to the view) |

- Every button has a short tooltip, drawn beside it on hover.
- The keys work only when no text field is being typed in. Studio's shortcuts (F4, Ctrl+S/Z/Y/C/V, Delete, Esc) keep
  their meanings.

**Selecting.**
- A click picks the nearest thing under the mouse in 3D.
  - A **structure** opens the structure inspector.
  - A **character or object** opens Studio's ordinary object inspector, and can be dragged on the ground at its own
    elevation, through the existing `move_entity`.
  - A character behind a structure isn't picked through it.
- Empty ground deselects. Esc lets go.

**Structure inspector.**
- It shows the id, the model, and fields for **X (m), Y (m), Height (m), Turn (degrees) and Scale**.
- Buttons: **Turn −90 / +90 / +15**, **Raise / Lower 0.5 m**, **Snap 0.5 m On/Off** and **Delete**.
- Dragging the structure moves it on its ground plane, snapped to 0.5 m. It moves live and commits once on release,
  as one undo step.

**Placing.**
- "Add a structure…" lists the project's `.glb` files. That is a simple list; the full asset browser is Stage 5B.
- Picking one makes it follow the mouse on the ground as a preview. A click places it, through `place_structure`,
  with a unique stable id from the file name (`stone_crossing`, `stone_crossing_2`, …). Esc cancels.
- Its Blender collision and floors come with the model. The new structure's floors are named `<id>/<collider>`.

**A safety net.** Overlapping structures, or covering a character, are allowed: it can be intentional. But if any
change leaves a character unable to stand where it is, Studio says so in the status bar, naming the character. That
covers drag, inspector, placement, AI acceptance and undo.

## Part G: Shared authoring

- **One path.** Studio's view calls only `Studio._edit(ops.…)`. AI tools call the same three ops through
  `authoring`. They were registered automatically, with no new framework and no direct writes behind Studio.
- **Atomic.** A proposal or batch is one `transaction` and one undo step. `"@0"` references the id created earlier in
  a batch.
- **Errors.** Errors are refused before anything changes, for example:
  - `There is no model 'assets/models/missing.glb' in the project (a .glb file, as Blender exports it).`
  - `Structure 'crossing' would stand at (156.2 m, 12.0 m), outside the room's ground (32 x 24 m).`
- **Review.** MCP clients read structures with `read_project` (the rooms include `settings.hd2d.structures`) and
  propose with `propose_changes`. The review panel shows lines such as:

  ```
  Start: places structure 'stone_crossing_2' (assets/models/stone_crossing.glb) at (25.0 m, 5.0 m)
  Start: moves structure 'stone_crossing' (7.0 m, 20.0 m) -> (9.0 m, 20.0 m, turned 180 degrees)
  ```

## Part H: The workflow, proven

`tooling/hd2d_studio_demo.py check` opens Stage 3/4's lit crossing (`hd2d_floors_demo.py build`) in Mesh Studio, in a
hidden window. It works the room only through window input events. The results are in `studio_check.json`, and the
pictures are in `docs/reviews/milestone16_stage5a_evidence/`.

| # | Step | Result |
|---|---|---|
| 1–2 | Open the room in Studio | The 3D view is active, with the structure `crossing`, 2 lamps and shadows on (`01_studio_3d_view.png`). |
| 3 | Click the player, then the platform | Player → object `start_player_…`. Platform → structure `crossing`, with its inspector (`02_structure_selected.png`). |
| 4 | Drag it, then click "Turn +90" | Moved 512, 384 → **576, 416** px (+2 m, +1 m, snapped), then **rotation 90°** (`03_moved_and_turned.png`). |
| 5 | Ctrl+Z, Ctrl+Z | First the turn is undone, then the move: **back to the original**. |
| 6 | Ctrl+Y, Ctrl+Y | **Moved and turned again.** |
| 7 | Ctrl+S | Saved; the project is no longer dirty. |
| 8 | Close Studio, reopen it | Structure at **576, 416, 90°** (`04_reopened.png`). |
| 9 | F4 | Play starts with the HD-2D renderer. |
| 10 | Arrow keys | The player is **blocked by the moved platform's new side**, then walks around it: right to 27 m, up to 13 m, left. They can stand at every stop (`05_play_walking_around.png`). |
| 11 | F4 | Back in edit mode, in the 3D view (`06_back_in_edit.png`). |
| + | "Add a structure…", pick `stone_crossing.glb`, move, click | The preview showed (`07_placing_preview.png`). The new structure **`stone_crossing`** is at 7 m, 20 m with **its 7 Blender floors** (`stone_crossing/col_bridge_deck`, …) (`08_second_copy.png`). Undo removes it, and redo restores it. |
| + | An AI proposes two structure changes, and the person clicks Accept | The summary is in words. Both were applied as one step, and the new structure is selected. A missing model was refused, with the message above. The new structure covers the player's start, so Studio warned: *Careful: Player can't stand there now (inside a structure)* (`09_after_ai_proposal.png`). |

**The same transform is used for drawing, collision and floors.** After reopening:

- the renderer's placement matrix and the picking matrix are identical;
- the collision world says the moved and turned west platform's top is at **2.0 m, floor
  `crossing/col_platform_west`**, where the model's (−6, 0) lands after the turn;
- a ray straight down hits the **drawn** geometry there at **2.0 m**.

**Edit / Play / Edit GPU lifecycle.** The edit view's renderer held 36 GPU objects before Play. After Play and Stop,
**all 36 are deleted**.

- The window's overall counts still rise by about 4 textures, framebuffers and programs per Play/Stop. These come
  from the **2D lighting layer of any room with scene `lights`**, not from HD-2D.
- Evidence:
  - A plain 2D room with the same two lights shows the same rise.
  - The same 2D room without lights does not.
  - Instrumenting `Hd2dRenderer.__init__` and `release` shows every HD-2D renderer released, with all its objects.
- Those 2D objects are freed later by garbage collection rather than explicitly. That is a pre-existing 2D-lighting
  behaviour, worth its own issue. I didn't change it in this stage.

## Performance

Hidden 1280×720 Studio window, RTX 4070, the lit crossing:

| | Median | p95 |
|---|---|---|
| 3D canvas draw (renderer into the canvas, shadows included) | **2.2 ms** | 9.2 ms |
| 3D pick (ray against 810 drawn triangles and the billboards) | **0.5 ms** | |
| Click selecting a structure (pick + inspector rebuild + redraw) | 284 ms | |
| Click selecting an object, Studio's existing path, for comparison | 316 ms | |
| Committing an edit (op, undo step, room reload with the renderer rebuilt, inspector) | 289 ms | |
| A whole Studio frame (UI and 3D canvas) | 15.9 ms | |

- **Click cost:** a selection click costs the same as Studio's existing 2D object selection. It is Studio's inspector
  rebuild; the 3D pick is half a millisecond.
- **Drag cost:** dragging is cheap. The dragged structure is drawn live, and the batch is rebuilt once at the start of
  the drag.
- **Commit cost:** committing reloads the room, as every Studio edit does. A cheaper partial rebuild is possible
  later.

## Tests and regression

| Check | Result |
|---|---|
| Fast tier (`tooling.test_tiers tier0`, `-W error`) | **4,437 passed, 0 failed** (8 skipped) |
| Targeted (Studio, project_ops, authoring, MCP, proposals, HD-2D, lighting, shadows, player, save/persistence, scene loader, lifecycle, tick, undo, behaviours, docs, templates) | **2,663 passed, 0 failed** (77 skipped are GL-gated, run in the GPU tier) |
| GPU tier (`MESH_GL_SMOKE=1`, every GL-gated file) | **88 passed, 1 failed, 1 skipped**. The failure is #351, which also fails on the base. The skip is the NumPy-gated Stage 1 lab. The HD-2D movement, lighting, save/load, Stage 2–4 and new Studio tests are all included. |
| New `tests/test_hd2d_structure_editing.py` (fast, 14) | The ops and their errors. AI registration and the catalogue. Summaries in words. Model-file checks. `authoring.apply` on a real project, as one undo step. The editor camera keeps the game's view at yaw 0, and its rays hit their target. Picking places structures exactly as drawn, and tells characters from structures, front from behind. |
| New `tests/test_hd2d_studio_gpu.py` (GPU, 8) | The whole Part H workflow above, the transform agreement, the lifecycle, the AI proposal and the burying warning, and responsiveness. |
| 2D Studio acceptance (`tooling/visual_polish_check.py`, hidden Studio and game) | **10/10** |
| Type gate / ruff gate / `type: ignore` | ok / ok / 0 |

- **Unchanged 2D paths:** 2D rooms take Studio's old code paths unchanged: drawing, input, panels and camera.
- **Filtered warning:** `test_hd2d_studio_gpu.py` filters one existing Studio deprecation warning (`UIInputText … use
  the style dict`). It comes from Studio's text fields, which no earlier GPU test had built.

## Known limitations

- **Each committed edit reloads the room**, about 0.3 s, like every Studio edit. A partial renderer rebuild would make
  it instant.
- **No manipulator gizmos.** Turning, raising and scaling are buttons and fields, and dragging moves only along the
  ground. Height-plane dragging and on-canvas handles are later work.
- **Structures may overlap each other.** Placement checks the room's ground bounds, not overlaps. A buried character
  is warned about, not refused.
- **The placement list is every `.glb` in the project**, with no thumbnails, catalogue or folders. That is Stage 5B.
- **The 2D map tools don't apply in the 3D view:** tile painting, the 2D grid and 2D handles. HD-2D rooms have no
  painted tilemap.
  - Objects are placed and dragged on the ground at elevation 0, or at their own elevation.
  - Lights are still edited from the Lighting panel's lists, with no 3D light gizmos.
- **Character sun shadows rotate with the editor camera** when it is turned, because billboards face the camera.
  Play's camera doesn't turn.
- **The camera** has fixed limits: 15–85° tilt and 4–120 m distance. It is perspective only in the editor.
- **Separate finding:** 2D lighting layers, in any room with `lights`, are freed by garbage collection rather than
  explicitly across Play/Stop. This is pre-existing and not HD-2D, as shown above.

## What I did not do

- No Stage 5B: no asset browser and no structure catalogue.
- No Stage 6: no HD-2D template or starter pack.
- No geometry or UV editing, no Blender synchronisation, no lighting gizmos, no bloom or depth of field.
- Stage 5A is not merged, and nothing went into `main`.
- **Filesystem:**
  - Work happened only in this task's worktree (`D:\Games\Mesh-s5a`) and in new, named scratchpad folders.
  - Builders refuse to write into existing folders, and the check tools never delete.
  - Your projects, stash, settings and untracked files were not touched.
- **Desktop:** no visible windows, no OS input, no focus taken.
