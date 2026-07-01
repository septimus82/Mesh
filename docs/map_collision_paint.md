# Paintable passability (collision tilemap)

Use a **collision-only tilemap** over a parallax scene to block walkable areas without replacing background art.

## Open the editor (standalone projects)

From your project directory (the folder that contains `config.json`):

```bash
python -m mesh_cli edit .
# or
python main.py --edit
```

This launches Mesh pinned to that project — it does **not** open the dev project browser or follow `projects.json` `last_root`.

Optional scene override:

```bash
python -m mesh_cli edit . --scene packs/core_regions/scenes/start.json
```

## Paint blocked cells

1. Press **F4** if the editor is not already active (`mesh edit` opens it for you).
2. Press **G** to open the tile paint panel (or use the Tiles command).
3. Use **[** / **]** to select the collision layer (`blocked` on the spike start scene).
4. **Left-click** to paint solid cells; **right-click** to erase.
5. Painted collision-only layers show a faint red overlay in the editor; they stay invisible during play.
6. **Save** the scene (Ctrl+S or Save from the editor menu).
7. Play (`main.py` or **Play From Here** in the editor) — painted cells block movement; empty cells stay walkable.

## Scene format

The start scene references a minimal Tiled map plus inline painted data:

- `tilemap.path` — Tiled JSON with the collision layer (`blocked`)
- `tilemap.collision_layer_id` — `"blocked"`
- `tilemap.tile_layers[].draw: false` — no visible tile art at runtime
- `tilemap.tile_layers[].tiles` — painted GIDs (saved back into scene JSON)

Perimeter entity walls can remain for outer bounds; the tilemap is the interior passability layer.

## Aligning with RPG Maker MZ (Map002 / light test)

Your RMMZ **Map002** (`light test/data/Map002.json`) matches the spike parallax art:

| | RMMZ Map002 | Parallax images | Mesh spike |
|---|---|---|---|
| Art size | — | **1402×1122** | **1402×1122** |
| Grid | **29×24** tiles | 29.2×23.4 @ 48px | `world_width` / `world_height` |
| Tile size | **48×48** px | — | use **48** (not 32) for 1:1 alignment |
| Pixel coverage | 1392×1152 | — | slight margin vs 1402×1122 |

**How RMMZ paints collision on Map002**

- **Layer 0 (ground)** — impassable cells use tile id **1544** (Outside tileset, all passage flags blocked).
- **Layer 5 (regions)** — **region 1** blocks 5 extra cells (`SL_RegionCollisionMZ`).
- Total: **324 blocked**, **372 walkable** cells.

**Import into Mesh**

```bash
python tooling/import_rmmz_passability.py \
  --map "C:/Users/slebb/Documents/RMMZ/light test/data/Map002.json" \
  --scene packs/core_regions/scenes/start.json
```

This writes the `blocked` collision layer in scene JSON (`draw: false`, 1=solid). Re-run after editing ground/region layers in RMMZ.

Use `python -m mesh_cli edit .` to tweak imported cells, then save and play.
