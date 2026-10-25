# Mesh HD-2D starter kit: provenance and rights

Everything in this folder is original work made for Mesh by Mesh's own scripts. It contains no third-party art,
models, fonts or sounds. It is licensed like the rest of the Mesh repository (see `pyproject.toml`), and it ships
with Mesh for every creator to use in their own games: the HD-2D RPG template copies it into new projects.

| What | Made by |
|---|---|
| `models/*.glb` (14 models) | `tooling/hd2d_assets/build_starter_kit.py`, run in headless Blender 4. It uses `build_cottage.py`, `build_stairs.py` and `blender_kit.py`. Collision objects are tagged `mesh_collision`. |
| The models' textures (embedded in the GLBs), `textures/grass.png`, `textures/dirt.png` | `tooling/hd2d_assets/pixel_textures.py`: drawn in code with PIL, 32 x 32 px, from fixed seeds. |
| `previews/*.png` | `engine/hd2d/thumbnail.py`: Mesh's CPU preview of each model. |
| `catalog.json` | `tooling/hd2d_assets/make_starter_kit.py`: names, categories, notes, licence line, collision facts. |

**Rebuilding.** The kit is deterministic: rebuilding writes the same bytes.

```
py -3.13 tooling/hd2d_assets/make_starter_kit.py --blender D:/program/blender.exe
```

**The template's other files.** The template also uses these files of Mesh's own:

- **Characters:** `assets/sprites/hd2d_hero.png`, `hd2d_villager.png` and `hd2d_merchant.png`, Mesh's HD-2D
  character style, and `starter_sign.png` (`tooling/make_starter_art.py`; see `docs/starter_art.md`).
- **The door:** `assets/sprites/door.png`.
- **Interface sounds:** `assets/sounds/ui_open.wav`, `ui_close.wav`, `ui_click.wav` and `ui_hover.wav`. These are
  tones synthesised by `tooling/generate_sounds.py`, and the shipped files are byte-identical to its output.

It does not use the unverified legacy sprites (`animated_player.png`, `sproutling.png`, `shelltide.png`).
