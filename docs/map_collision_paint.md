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
