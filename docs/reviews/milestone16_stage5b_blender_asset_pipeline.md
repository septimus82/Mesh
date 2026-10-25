# Milestone 16 Stage 5B: Blender asset pipeline and HD-2D asset management

**Verdict:** pending (this document starts as the design; results are added as the stage is built).

The goal: **Blender → export GLB → import into Mesh Studio → preview → place → edit → play**, for ordinary
creators, without hand-editing JSON or copying files.

## Starting point (what already exists, and is reused)

| Piece | Where | Reused for |
|---|---|---|
| GLB reader (static meshes, embedded PNG textures, samplers, `mesh_collision` extras) | `engine/hd2d/glb.py` (`load_glb`, `GlbError`, `model_problem`, `contained`) | validating an import, its preview and its report |
| One path rule for HD-2D assets | `engine/hd2d/settings.py` `asset_path`, plus `glb.contained` (links followed) | where an imported model may live |
| Scene representation | `settings.hd2d.structures[]`: `{id, model, x, y, elevation, rotation, scale}` | unchanged; instances keep pointing at a model path |
| Placing and editing structures | `project_ops.place_structure` / `set_structure` / `remove_structure`, through `Studio._edit` (one undo step) and `authoring` (AI) | "Place in scene", AI placement |
| The 3D view, ghost preview, picking | `engine/studio_hd2d.py` (`Hd2dView`, `start_placing`, `set_preview`) | placing from the browser |
| File imports into a project | `Project.import_sprite` / `import_tileset` (`engine/studio_project.py`): slugged names, never overwrite, written straight away (not undo) | the same pattern for models |
| Import panel | `Studio._import_panel`: typed path (Enter applies) + Browse... (`ask_path`), live check, preview, Import / Cancel | the model import panel |
| Thumbnails | `Studio._thumbs` + `_draw_previews` (PIL images drawn over the UI, cached textures) | model thumbnails |
| Shared authoring + AI review | `engine/authoring.py` (ops from `project_ops`, `_bind` checks `model`), `engine/studio_ai.py` (stage, then a person accepts) | AI reads the catalogue, places and transforms; the person accepts |

Nothing like a per-asset catalogue or provenance record exists yet (the repo has `NOTICE` files and a build
provenance record, not per-asset metadata); Studio has no model import (it told creators to export into `assets/`).

## Architecture

**One asset module, no parallel system.** `engine/hd2d/catalog.py` is the project's structure catalogue and the only
code that writes model files into a project. `Project.import_model` / `reimport_model` call it (beside
`import_sprite` and `import_tileset`); Mesh Studio's panels call the Project; AI tools read the catalogue and place
through the existing `place_structure`.

**Storage.**

- Models are copied to `assets/models/<id>.glb`.
- Their previews go to `assets/models/previews/<id>.png`.
- The catalogue is `assets/models/catalog.json`:

```json
{"schema_version": 1, "models": [{
  "id": "cottage", "model": "assets/models/cottage.glb", "name": "Cottage", "category": "Buildings",
  "preview": "assets/models/previews/cottage.png", "scale": 1.0, "rotation": 0.0, "pixels": "sharp",
  "collision": {"solid": 1, "floor": 0, "wall": 4}, "floors": ["floor"],
  "notes": "", "license": "CC0 (made for this project)",
  "source": {"file": "D:/art/cottage.glb", "sha256": "…", "imported": "2026-10-25T12:00:00Z"}}]}
```

- **Everything in an entry is optional except `id` and `model`.** A `.glb` that is in the project but not in the
  catalogue (every Stage 1–5A project) is listed with defaults (its file name, category "Uncatalogued"), and works
  exactly as before.
- **Older scenes are unaffected:** they still name the model path, and nothing about them changes.
- **Instances share one file:** every placed copy names the same `model` path, so there is no per-instance copy, and
  the renderer already reads each model once per room.

**Import** (`catalog.import_model(root, source, …)`):

1. **Validate the source file first, where it is.** `load_glb` must read it (the same reader as the game). The
   report lists:
   - parts, triangles, bounds in metres;
   - materials and textures (size and filtering);
   - colliders by kind and name (the floor identities);
   - anything unsupported, refused with the reader's message.
2. **Refuse:** anything that isn't a readable `.glb`; an unsafe or out-of-project destination (`asset_path` +
   `contained`); a name that would overwrite another model. An existing id gets a numbered id (`cottage_2`); the
   same bytes as an already imported model are reported as "already imported as …".
3. **Pixel art.** With "keep pixels sharp" (the default), a texture that Blender exported as *Linear* gets a
   NEAREST sampler in the stored copy. Only the GLB's JSON chunk changes; the binary data is untouched. The report
   says which textures changed. Blender's default image interpolation is Linear, so without this a creator's
   PixelLab texture comes out blurred.
4. **Stage everything, then commit.** The model copy, the preview PNG and the catalogue entry are all written beside
   their targets under temporary names, checked (the copy is read back with `load_glb`), and only then moved into
   place. Any failure removes the temporary files and leaves the project as it was.

**Reimport** (`catalog.reimport_model(root, id, source)`): explicit, from the asset's details ("Reimport from
Blender...", defaulting to the recorded source file).

1. **Check first.** The new file is validated like an import. Before anything is written, it is compared with the
   current model:
   - colliders added, removed or changed kind;
   - floor identities (`<structure>/<node>`) gained or lost;
   - bounds;
   - in every room that uses the model, characters that stood validly and no longer would, and navigation cells
     lost (`engine.hd2d.world.World` with the old and new models).
2. **Swap safely.** The same staging as an import, plus backups of the files it replaces (the model, its preview,
   the catalogue), restored if any step fails.
3. **Instances keep their ids and transforms.** Scenes aren't edited at all.
4. **Studio reloads the room.** That rebuilds the renderer and the world, which releases the old GPU objects (Stage 2
   ownership) and reads the new geometry and collision together. If the room then fails to build, the previous
   files are restored and the room is reloaded again.

**Browser.** Studio's "Add a structure..." panel becomes the **Models** browser:

- import, search (name, category, notes);
- rows with a thumbnail, name, category and how many copies are placed in this room;
- the selected model's details: a larger preview, its facts, collision, provenance and properties;
- **Place in scene** (the existing ghost placement, now using the model's default turn and scale);
- **Reimport**.

The 2D picture picker no longer lists model previews.

**Thumbnails** are drawn on the CPU (`engine/hd2d/thumbnail.py`): a small z-buffered rasteriser over the model's own
textured triangles, from the view the editor opens with. They are made once at import or reimport and saved as
PNGs, so the browser costs no GPU work and no extra renderer, and tests can check them without OpenGL.

**AI.**

- `read_project` gains `models`: the catalogue as listed (id, model path, name, category, collision, default turn
  and scale, missing or unusable).
- Any change's `model` may name a catalogue id instead of a path (`_bind` resolves it, then validates as before).
- AI tools place and transform through `place_structure` / `set_structure`, as proposals the person accepts in
  Studio's review panel.
- There is deliberately no AI file import: AI can't write or overwrite project files, or accept its own proposals.

## Status

Design written before implementation. The sections below are filled in as the stage is built.
