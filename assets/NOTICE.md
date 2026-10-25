# Mesh's bundled files: provenance and licences

A pip-installed Mesh carries these files under `<prefix>/share/mesh-engine/` (`pyproject.toml`,
`[tool.setuptools.data-files]`; `docs/packaging.md`). New projects copy what they use from here.

| Files | What and where from | Licence |
|---|---|---|
| `config.json` | Mesh's default settings and input bindings | Mesh's own: Mesh's licence (`pyproject.toml`) |
| `assets/data/monster_*.json` | The monster template's species, moves and type chart | Mesh's own |
| `assets/sprites/starter_hero.png`, `starter_villager.png`, `starter_sign.png`, `hd2d_hero.png`, `hd2d_villager.png`, `hd2d_merchant.png` | Starter characters and sign, drawn in code by `tooling/make_starter_art.py` (`docs/starter_art.md`) | Mesh's own |
| `assets/sprites/door.png` | The door Mesh Studio puts in a room: a 64 × 64, five-colour drawing made for Mesh (with Mesh Studio, commit `156068c`) | Mesh's own |
| `assets/tilesets/starter.png`, `starter.json` | The starter tileset, drawn in code by `tooling/make_starter_tileset.py` | Mesh's own |
| `assets/sounds/*.wav`, `assets/music/dungeon_theme.wav` | Tones and a loop synthesised by `tooling/generate_sounds.py` and `tooling/generate_music.py` | Mesh's own |
| `assets/templates/*.png` | The launcher's template pictures, rendered from Mesh's own templates | Mesh's own |
| `assets/hd2d_starter/**` | The HD-2D starter kit: models built by Mesh's Blender scripts, pixel textures drawn in code, CPU previews | Mesh's own: see `assets/hd2d_starter/PROVENANCE.md` |
| `assets/branding/*` | The MeshMind Studios brand: Mesh Studio's application icon and the publisher's wordmark | © MeshMind Studios, all rights reserved; **not** covered by Mesh's code licence: see `assets/branding/NOTICE.md` |
| `assets/icons/*.png`, `assets/icons/lucide/*.svg` | Mesh Studio's button icons, from [Lucide](https://lucide.dev) (`lucide-static@1.61.0`) | ISC licence: the notice is `assets/icons/lucide/LICENSE`, kept with every copy (`assets/icons/NOTICE.md`) |

**Not bundled:** `assets/sprites/animated_player.png`, `sproutling.png` and `shelltide.png`. Their provenance is
unverified, so a pip-installed Mesh never ships them. No template's new project uses `animated_player.png`. The
developer-only monster template names the other two; in a pip install its creatures show Mesh's placeholder instead.
