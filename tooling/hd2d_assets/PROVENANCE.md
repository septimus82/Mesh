# HD-2D demonstration and test assets: provenance

Everything in this folder is original work, made for the Mesh project by its scripts here. It contains no
third-party art or models, and it is licensed like the rest of the repository (see `pyproject.toml`).

| File | Made by | How |
|---|---|---|
| `textures/*.png` (timber, plaster, shingles, floorboards, cobbles) | `pixel_textures.py` | Drawn in code with PIL from small palettes: 32 x 32 px, one tile per metre, seamless, deterministic (fixed seeds) |
| `cottage.glb` | `build_cottage.py` | Built and exported by Blender 4 (headless) from those textures; collision objects tagged `mesh_collision` |
| `cottage_v2.glb` | `build_cottage.py --v2` | The same cottage after an edit: a porch, a hearth and a chimney (Stage 5B's reimport demonstration) |
| `stairs.glb` | `build_stairs.py` | A modular staircase section; its textures are deliberately left at Blender's default Linear interpolation |
| `stone_crossing.glb` | `build_crossing.py` | Stage 3's crossing, with the Stage 1 lab textures (`tooling/hd2d_lab/textures.py`) |

**Rebuilding.** From the repo root, with Blender at `D:\program\blender.exe` (any Blender 4 works):

```
py -3.13 tooling/hd2d_assets/pixel_textures.py
blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_cottage.py -- tooling/hd2d_assets/cottage.glb
blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_cottage.py -- tooling/hd2d_assets/cottage_v2.glb --v2
blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_stairs.py -- tooling/hd2d_assets/stairs.glb
```

When a creator imports one of these through Mesh Studio, it records the same facts per model: its source file,
SHA-256, import time and a licence line, in the project's `assets/models/catalog.json`.
