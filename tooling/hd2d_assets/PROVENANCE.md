# HD-2D demonstration and test assets: provenance

Everything in this folder is original work, made for the Mesh project by its scripts here. It contains no
third-party art or models, and it is licensed like the rest of the repository (see `pyproject.toml`).

| File | Made by | How |
|---|---|---|
| `textures/*.png` (timber, plaster, shingles, floorboards, cobbles; grass, dirt, rock, crate, barrel, iron, awning, lantern for the starter kit) | `pixel_textures.py` | Drawn in code with PIL from small palettes: 32 x 32 px, one tile per metre, seamless, deterministic (fixed seeds) |
| `cottage.glb` | `build_cottage.py` | Built and exported by Blender (headless) from those textures; collision objects tagged `mesh_collision` |
| `cottage_v2.glb` | `build_cottage.py --v2` | The same cottage after an edit: a porch, a hearth and a chimney (Stage 5B's reimport demonstration) |
| `stairs.glb` | `build_stairs.py` | A modular staircase section; its textures are deliberately left at Blender's default Linear interpolation |
| `house.glb` | `build_house.py` | M2-1's building: a 4 x 3 m stone house with a doorway and a flat slate-grey roof, built and exported by Blender 5.2.0 LTS (headless); collision objects tagged `mesh_collision`. Byte-identical on every rebuild |
| `house_v2.glb` | `build_house.py --v2` | The same house after an edit: north wall 1 m north, ridge 3.2 -> 3.9 m, terracotta roof (M2-1's reimport demonstration, `docs/reviews/m2_blender_building/`) |
| `house_reimport_evidence.py` | (script) | M2-1's evidence: imports `house.glb` into a new HD-2D RPG project, places it twice, reimports `house_v2.glb`, refuses a cut-off export, with hidden-window pictures |
| `stone_crossing.glb` | `build_crossing.py` | Stage 3's crossing, with the Stage 1 lab textures (`tooling/hd2d_lab/textures.py`) |
| `build_starter_kit.py`, `make_starter_kit.py` | (scripts) | Mesh's HD-2D starter kit (Stage 6A): the 14 models in `assets/hd2d_starter/models`, built by Blender from these textures, and their previews and catalogue; see `assets/hd2d_starter/PROVENANCE.md` |

**Rebuilding.** From the repo root, with Blender at `D:\program\blender.exe` (Blender 5.2.0 LTS wrote every committed export here: their glTF
`asset.generator` is `Khronos glTF Blender I/O v5.2.39`, and 5.2.0 rebuilds `cottage.glb` and the house byte for byte):

```
py -3.13 tooling/hd2d_assets/pixel_textures.py
blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_cottage.py -- tooling/hd2d_assets/cottage.glb
blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_cottage.py -- tooling/hd2d_assets/cottage_v2.glb --v2
blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_stairs.py -- tooling/hd2d_assets/stairs.glb
blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_house.py -- tooling/hd2d_assets/house.glb
blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_house.py -- tooling/hd2d_assets/house_v2.glb --v2
```

When a creator imports one of these through Mesh Studio, it records the same facts per model: its source file,
SHA-256, import time and a licence line, in the project's `assets/models/catalog.json`.
