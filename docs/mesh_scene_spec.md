# Mesh Scene Specification

This document describes the JSON format consumed by Mesh Engine when loading a scene. All paths are relative to the project root (for example `scenes/test_scene.json`). The loader is lenient when it can be, but supplying valid data keeps runtime surprises to a minimum.

## Top-Level Structure

A Mesh scene JSON file is an object with the following keys:

| Key | Type | Required | Description |
| --- | ---- | -------- | ----------- |
| `name` | string | no | Friendly identifier shown in logs. Defaults to `"<unnamed>"`. |
| `version` | integer | no | Reserved for future schema upgrades. Defaults to `1`. |
| `description` | string | no | Free-form description for humans. |
| `settings` | object | no | Visual / world-size settings. Defaults are filled by the loader. |
| `layers` | array | no | Sprite layers rendered in order. Default layers are `background`, `entities`, `foreground`. |
| `collision_rules` | object | no | Optional overrides for tag-to-tag collision checks. |
| `tilemap` | object | no | Optional Tiled map configuration (see below). |
| `background_layers` | array | no | Optional image-based parallax layers rendered behind the tilemap. |
| `sensors` | array | no | Optional sensor/trigger definitions (AABB zones). |
| `entities` | array | **yes** | The sprites that appear in the scene. Empty list by default. |

Any additional top-level keys are ignored but reported as warnings by the validator.

## Sensors Object

`sensors` defines a list of trigger zones.

```json
"sensors": [
    {
        "id": "gate_trigger",
        "rect": [100, 200, 50, 50],
        "tags": ["checkpoint"],
        "enabled": true
    }
]
```

| Field | Type | Default | Description |
| ----- | ---- | ------- | ----------- |
| `id` | string | **required** | Unique identifier for logic hooks. |
| `rect` | array | **required** | `[x, y, w, h]` center-x, center-y, width, height. |
| `tags` | array | `[]` | List of string tags for filtering. |
| `enabled` | bool | `true` | Whether the sensor is active initially. |

## Settings Object

`settings` configures ambient properties for the whole scene. Recognized fields:

| Field | Type | Default | Notes |
| ----- | ---- | ------- | ----- |
| `background_color` | string | `dark_blue_gray` | Must match a name from `arcade.color`. |
| `world_width` | number | unset | Optional virtual bounds for the world. When omitted and a tilemap is present, the loader derives it from `tilemap.width * tilemap.tilewidth`. |
| `world_height` | number | unset | Optional virtual bounds for the world. When omitted and a tilemap is present, the loader derives it from `tilemap.height * tilemap.tileheight`. |
| `render_sort_mode` | string | `"y_sort"` | Controls entity draw ordering: `"y_sort"` (default) or `"explicit_z"`. See _HD-2D Render Sorting_ below. |
| `shadows_enabled` | bool | `true` | Enable HD-2D sprite drop shadows. Set to `false` to disable all shadows in the scene. |
| `shadows_contact_enabled` | bool | `true` | Enable contact shadows (smaller, darker layer under base shadow). Only applies when `shadows_enabled` is true. |
| `shadows_ao_enabled` | bool | `false` | Enable AO (ambient occlusion) shadow ring (larger, subtle halo). Optional, off by default. |
| `depth_tint_enabled` | bool | `false` | Enable depth-based sprite tinting for atmospheric depth. |
| `depth_tint_strength` | number | `0.35` | Tint intensity (0 = none, 1 = full effect). |
| `depth_tint_near_color` | array | `[255,255,255,255]` | RGBA color for near objects (neutral by default). |
| `depth_tint_far_color` | array | `[180,180,200,255]` | RGBA color for far objects (subtle blue/dark by default). |
| `depth_tint_layer_range` | array | `[-10, 10]` | Expected render_layer range for normalization. |
| `depth_tint_z_range` | array | `[-100, 100]` | Expected depth_z range for normalization. |
| `outline_enabled` | bool | `false` | Enable faux sprite outline/rim light. |
| `outline_color_rgba` | array | `[0,0,0,90]` | RGBA outline color (alpha drives base strength). |
| `outline_strength` | number | `0.5` | Outline strength multiplier (0.0 to 1.0). |
| `outline_radius_px` | number | `1` | Outline radius in pixels. |
| `outline_near_factor` | number | `0.6` | Depth boost factor (near sprites get stronger outlines). |
| `camera` | object | unset | Optional advanced camera settings (see below). |

Unknown settings fields are preserved in memory so future systems can read them.

### Themed Encounter Spawns

Scenes can opt into themed spawns by setting `settings.use_theme_spawns=true` along with `settings.region_theme` / `settings.encounter_set_id`.
To force a variant patch onto themed spawns only, set `settings.theme_spawn_variant_id` (for example `"mini_boss"`).
Candidate-level `variant_id` entries inside the encounter set take precedence over the scene-level override.

```json
"settings": { "use_theme_spawns": true, "region_theme": "void", "encounter_set_id": "void_encounters", "theme_spawn_variant_id": "mini_boss" }
```

### Camera Settings Object

`settings.camera` configures how the window camera behaves.

| Field | Type | Default | Notes |
| ----- | ---- | ------- | ----- |
| `lerp_factor` | number | 5.0 | Base smoothing speed when following targets. |
| `padding` | number | 0.0 | Extra inset applied before clamping to bounds. |
| `bounds.left/right/top/bottom` | numbers | unset | Explicit world-space rectangle that constrains the camera center. |
| `zoom.initial` | number | 1.0 | Starting zoom value when the scene loads. |
| `zoom.target` | number | matches `initial` | Default zoom target before behaviours override it. |
| `zoom.speed` | number | 5.0 | How quickly zoom eases toward the target. |
| `zoom.min` / `zoom.max` | number | 0.25 / 4.0 | Clamp range for zoom overrides. |
| `areas` | array | [] | Optional camera areas (see below). |

Each entry in `areas` is an object with:

- `name`: Friendly identifier (optional, auto-generated when omitted).
- `x`, `y`, `width`, `height`: Required numeric bounds (world coordinates).
- `priority`: Higher numbers win if multiple areas overlap.
- `zoom`: Optional zoom override while the target is inside.
- `lerp_factor`: Optional smoothing override while inside the area.
- `padding`: Extra inset applied on top of the global padding while inside the area.

## HD-2D Render Sorting

Mesh Engine supports HD-2D style deterministic render ordering for entities. This ensures consistent draw order across frames and sessions.

### Sort Modes

Set `settings.render_sort_mode` to control how entities are sorted:

| Mode | Sort Key | Use Case |
| ---- | -------- | -------- |
| `y_sort` (default) | `(render_layer, y_position, entity_id)` | Classic top-down RPGs where lower y = further back. |
| `explicit_z` | `(render_layer, depth_z, y_position, entity_id)` | HD-2D / 2.5D games with manual depth control. |

### Entity Render Fields

- **`render_layer`** (int, default `0`): Primary depth tier. Lower values draw first (further back). Use for separating ground, characters, and foreground elements.
- **`depth_z`** (float, default `0.0`): Fine depth value within a render layer. Only affects ordering in `explicit_z` mode. Useful for layering objects at the same y-position.

Example:

```json
"settings": { "render_sort_mode": "explicit_z" },
"entities": [
  { "name": "floor_tile", "sprite": "assets/tile.png", "x": 100, "y": 50, "render_layer": -10, "depth_z": 0 },
  { "name": "hero", "sprite": "assets/hero.png", "x": 100, "y": 50, "render_layer": 0, "depth_z": 0 },
  { "name": "tree_canopy", "sprite": "assets/tree.png", "x": 100, "y": 50, "render_layer": 10, "depth_z": 0 }
]
```

### Sprite Drop Shadows

HD-2D scenes automatically render multi-layer blob shadows under sprites to enhance depth perception and grounding. Shadows are drawn BEFORE sprites in the deterministic render order.

**Multi-Layer Shadow System:**
1. **AO Shadow** (optional): Large, very low alpha ambient occlusion halo
2. **Base Shadow**: Standard blob shadow
3. **Contact Shadow** (default on): Smaller, darker, closer to feet for enhanced grounding

**Shadow Behavior:**
- Nearer entities (higher `render_layer` / `depth_z`) get larger, darker shadows
- Farther entities (lower `render_layer` / `depth_z`) get smaller, lighter shadows
- Shadows are ellipses positioned below the sprite center

**Scene-Level Control:**
- `settings.shadows_enabled`: Set to `false` to disable all shadows (default `true`)
- `settings.shadows_contact_enabled`: Enable contact shadows (default `true`)
- `settings.shadows_ao_enabled`: Enable AO shadow ring (default `false`)

**Per-Entity Control (Base Shadow):**
- `shadow_enabled`: Set to `false` to hide all shadows for this entity (default `true`)
- `shadow_scale`: Multiplier for shadow size (default `1.0`)
- `shadow_alpha`: Override shadow opacity from 0.0 to 1.0 (default computed from depth)
- `shadow_offset_y`: Override shadow Y offset in pixels (default computed from depth)

**Per-Entity Control (Contact/AO Shadows):**
- `shadow_contact_enabled`: Override scene setting for contact shadow (default follows scene)
- `shadow_contact_scale`: Override contact shadow scale (default `0.55` of base)
- `shadow_contact_alpha`: Override contact shadow alpha (default `1.35×` base alpha)
- `shadow_ao_enabled`: Override scene setting for AO shadow (default follows scene)

Example with shadow customization:

```json
"settings": {
  "shadows_enabled": true,
  "shadows_contact_enabled": true,
  "shadows_ao_enabled": false
},
"entities": [
  { "name": "flying_enemy", "x": 100, "y": 200, "shadow_offset_y": -20, "shadow_scale": 0.5 },
  { "name": "ghost", "x": 150, "y": 200, "shadow_enabled": false },
  { "name": "heavy_robot", "x": 200, "y": 200, "shadow_contact_scale": 0.7, "shadow_ao_enabled": true }
]
```

### Depth-Based Tinting

HD-2D scenes can optionally apply depth-based tinting to sprites for atmospheric depth effects. Farther objects (lower `render_layer` / `depth_z`) appear darker/desaturated, while nearer objects remain vivid.

**Scene-Level Control:**
- `depth_tint_enabled`: Set to `true` to enable (default `false`)
- `depth_tint_strength`: Intensity from 0.0 to 1.0 (default `0.35`)
- `depth_tint_near_color`: RGBA for near objects (default white `[255,255,255,255]`)
- `depth_tint_far_color`: RGBA for far objects (default subtle blue `[180,180,200,255]`)

**Per-Entity Control:**
- `depth_tint_enabled`: Override scene setting for this entity
- `depth_tint_strength`: Override tint strength for this entity

Example:

```json
"settings": {
  "depth_tint_enabled": true,
  "depth_tint_strength": 0.4,
  "depth_tint_far_color": [150, 150, 180, 255]
},
"entities": [
  { "name": "important_npc", "x": 100, "y": 200, "depth_tint_enabled": false },
  { "name": "background_decor", "x": 50, "y": 100, "render_layer": -5, "depth_tint_strength": 0.8 }
]
```

### Faux Sprite Outline (Rim Light)

HD-2D scenes can optionally draw a subtle outline behind sprites for readability. The outline draws multiple offset passes before the main sprite and fades with depth.

**Scene-Level Control:**
- `outline_enabled`: Set to `true` to enable (default `false`)
- `outline_color_rgba`: RGBA color for the outline
- `outline_strength`: 0.0 to 1.0 strength multiplier
- `outline_radius_px`: Pixel radius for offset passes
- `outline_near_factor`: Strength boost for near sprites

**Per-Entity Control:**
- `outline_enabled`: Override scene setting for this entity
- `outline_color_rgba`: Override outline color
- `outline_strength`: Override outline strength
- `outline_radius_px`: Override outline radius

## Background Planes (HD-2D Parallax)

Scenes can define image-based parallax background planes via `background_planes`. Planes are rendered behind all entities and tilemap layers, sorted deterministically by `(z, id)`.

Each entry is an object with:

| Field | Type | Required | Default | Description |
| ----- | ---- | -------- | ------- | ----------- |
| `id` | string | **yes** | — | Unique identifier within the scene. |
| `path` | string | **yes** | — | Image path (relative to repo root). |
| `z` | int | **yes** | — | Depth value. Lower values draw earlier (further "behind"). |
| `parallax` | number | no | `1.0` | Movement factor (clamped to `[0, 2]`). |
| `offset_x` | number | no | `0` | Horizontal offset in pixels. |
| `offset_y` | number | no | `0` | Vertical offset in pixels. |
| `repeat_x` | bool | no | `false` | Tile horizontally to fill the viewport. |
| `repeat_y` | bool | no | `false` | Tile vertically to fill the viewport. |

### Parallax Formula

Parallax is applied in screen space using the scene camera center:

```
screen_offset_px = -camera_center_world * parallax * zoom + offset
```

- `parallax=1.0` tracks the camera normally (moves 1:1 with the world).
- `parallax=0.0` locks the layer to the screen (static backdrop).
- Values between create the classic parallax depth effect.

Example:

```json
"background_planes": [
  { "id": "Sky", "path": "assets/bg/sky.png", "z": -1000, "parallax": 0.0, "repeat_x": true },
  { "id": "Mountains", "path": "assets/bg/mountains.png", "z": -900, "parallax": 0.3, "repeat_x": true },
  { "id": "Trees", "path": "assets/bg/trees.png", "z": -800, "parallax": 0.6, "repeat_x": true }
]
```

> **Migration note:** The legacy `background_layers` key is still supported for backwards compatibility but `background_planes` is preferred for new scenes.

## Background Layers (Legacy)

Scenes can optionally define image-based parallax background layers via `background_layers`. Layers are rendered behind the tilemap and entity layers, sorted deterministically by `(z, id)`.

Each entry is an object with:

- `id` (string, required): Unique identifier within the scene.
- `path` (string, required): Image path (relative to repo root).
- `z` (int, required): Lower values draw earlier (further "behind").
- `parallax` (number, optional; default `1.0`): Movement factor (clamped to `[0, 2]`).
- `repeat_x` (bool, optional; default `false`): Tile horizontally to fill the viewport.
- `repeat_y` (bool, optional; default `false`): Tile vertically to fill the viewport.

Parallax is applied in screen space using the scene camera center:

- `screen_offset_px = -camera_center_world * parallax * zoom`
- `parallax=1.0` tracks the camera normally; `parallax=0.0` locks the layer to the screen.

Example:

```json
"background_layers": [
  { "id": "Sky", "path": "assets/bg/sky.png", "z": -1000, "parallax": 0.2, "repeat_x": true },
  { "id": "Mountains", "path": "assets/bg/mountains.png", "z": -900, "parallax": 0.4, "repeat_x": true }
]
```

## Brushes

Tile brushes are small reusable patterns that can be applied onto a `tilemap.tile_layers[].tiles` grid via the CLI.
Store brush JSON files under `packs/*/brushes/*.json`.

Brush format:

```json
{
  "id": "corner_ruins_a",
  "w": 3,
  "h": 3,
  "mask_tile": -1,
  "tiles": [
    [12, 13, 14],
    [15, -1, 16],
    [17, 18, 19]
  ]
}
```

Rules:
- `tiles` must be `h` rows of `w` ints.
- `mask_tile` means "do not write" (defaults to `-1`).

Discovery and validation:

- List available brushes: `python -m mesh_cli brush list`
- Validate all brushes: `python -m mesh_cli brush validate-all`
- Preview a brush: `python -m mesh_cli brush preview packs/core_regions/brushes/corner_ruins_a.json`

Apply to a scene tile layer:

```bash
python -m mesh_cli scene tilemap brush scenes/example.json \
  --layer-id Ground \
  --brush packs/core_regions/brushes/corner_ruins_a.json \
  --x 10 --y 5 \
  --anchor tl
```

Example: place three corners via repeated calls:

```bash
# Top-left corner at (0,0)
python -m mesh_cli scene tilemap brush scenes/example.json \
  --layer-id Ground \
  --brush packs/core_regions/brushes/corner_ruins_a.json \
  --x 0 --y 0

# Top-right corner at (20,0)
python -m mesh_cli scene tilemap brush scenes/example.json \
  --layer-id Ground \
  --brush packs/core_regions/brushes/corner_ruins_a.json \
  --x 20 --y 0

# Bottom-left corner at (0,12)
python -m mesh_cli scene tilemap brush scenes/example.json \
  --layer-id Ground \
  --brush packs/core_regions/brushes/corner_ruins_a.json \
  --x 0 --y 12
```

By default the brush uses `(x,y)` as the top-left. Use `--anchor center` to place the brush centered on `(x,y)`.
Out-of-bounds writes are an error unless `--clip` is provided.

## Layers Array

Each entry is an object with at least a `name` field. Layers define sprite draw/update lists. The loader creates any missing layers on the fly; if the `layers` key is omitted, it injects the default trio:

```json
"layers": [
  { "name": "background" },
  { "name": "entities" },
  { "name": "foreground" }
]
```

Sprites can reference any layer name via their `layer` field. Unknown names create new sprite lists automatically.

## Collision Rules

`collision_rules` is a dictionary mapping `"tag_a:tag_b"` strings to booleans. Example:

```json
"collision_rules": {
  "player:terrain": true,
  "player:hazard": true,
  "enemy:terrain": true
}
```

Rules are order-independent. At runtime the engine sorts the pair (`player`, `terrain`) and stores a tuple key, so `"player:hazard"` and `"hazard:player"` are equivalent. Tags use `"<none>"` to refer to sprites without a tag. Pairs not listed fall back to `True` (collide).

## Tilemap Object

Scenes can reference an external Tiled JSON export to populate background/foreground layers plus collision sprites. The `tilemap` object supports the following keys:

| Field | Type | Required | Description |
| ----- | ---- | -------- | ----------- |
| `path` | string | **yes** | Path to a Tiled `.json` map. Either absolute or relative to the scene file. |
| `layers` | array | **yes** | List of layer descriptors that select which map layers to load. |

Each entry inside `layers` is an object with:

| Field | Type | Default | Notes |
| ----- | ---- | ------- | ----- |
| `name` | string | -- | Must match a layer name inside the Tiled map. |
| `draw` | bool | `true` | When false, the layer is skipped entirely (useful for collision-only layers). |
| `collision` | bool | `false` | Adds sprites from this layer to `solid_sprites` so movement behaviours treat them as blocking. |
| `collision_tag` | string | `terrain` | Tag applied to collision sprites (visible in dev tools and collision filtering). |
| `z` | string | `background` | Either `background` or `foreground`, controlling draw order relative to entity layers. |
| `properties` | object | `{}` | Default metadata merged into every tile spawned from this layer (overridden by Tiled layer / per-tile properties). |

Layer types:

- `tilelayer`: Tiles are converted into Arcade sprites using the associated tileset textures.
- `objectgroup`: Rectangle objects become invisible solid sprites sized to the placed object. Use these for precise collision geometry.

Limitations:

- Only orthogonal maps are supported.
- Tile layer data must be stored inline (`data` array) or CSV encoded without compression.
- Tile flips/rotations are logged but not fully respected (sprites are rendered unflipped for now).

Example snippet:

```json
"tilemap": {
  "path": "assets/tilemaps/demo_map.json",
  "layers": [
    { "name": "ground", "collision": true },
    { "name": "foreground", "z": "foreground" }
  ]
}
```

At runtime `GameWindow` draws background tile layers first, then entity layers, then any foreground tile layers. Collision-enabled tile layers automatically merge into the existing `solid_sprites` list so behaviours like `PlayerController` continue to interact with the world without modification.

### Tile Layer Overrides (multi-layer config)

Scenes can also provide `tilemap.tile_layers` (preferred) instead of legacy `tilemap.layers`. Each `tile_layers[]` entry may include a `tiles` array to override the underlying map layer tile data. The override array is a flattened row-major list of ints with length `map_width * map_height` (matching the referenced Tiled map dimensions).

The authoring CLIs (`mesh_cli scene tilemap fill-rect/clear-rect/paint`) operate in **tile coordinates** (not pixels) and use an **inclusive** rectangle convention: `[x0..x1] x [y0..y1]`.

Stamp templates (tile + entity patterns) live under `packs/*/stamps/*.json` (for example `packs/core_regions/stamps/basic_room_10x8.json`) and can be applied with `python -m mesh_cli scene stamp ...`.

Discoverability helpers:

- `python -m mesh_cli stamp list`
- `python -m mesh_cli stamp validate-all`
- `python -m mesh_cli stamp preview packs/core_regions/stamps/basic_room_10x8.json`
- Dry-run report (no writes): `python -m mesh_cli scene stamp-report scenes/foo.json --stamp packs/core_regions/stamps/basic_room_10x8.json --x 10 --y 10`

Macro assets (authoring shortcuts that create/update entities deterministically) live under `packs/*/macros/*.json`.

- List: `python -m mesh_cli macro list`
- Preview (metadata + optional diff counts when referenced by `worlds/main_world.json:macro_audit_cases`): `python -m mesh_cli macro preview packs/core_regions/macros/door_to_upper_hall.json`
- Apply to a scene: `python -m mesh_cli scene macro-apply scenes/foo.json --macro packs/core_regions/macros/door_to_upper_hall.json`
- Dry-run report (no writes): `python -m mesh_cli scene macro-report scenes/foo.json --macro packs/core_regions/macros/door_to_upper_hall.json`

`scene macro-report` JSON shape (keys are deterministic; lists are sorted as noted):

- `entity_changes[]` (sorted by `id`): `{id, action, prefab_id, name, tags, x, y, behaviours_added, behaviours_removed}`
- `config_changes[]` (sorted by `(id, behaviour, field)`): `{id, behaviour, field, before, after}`

Verify-all stamp audits (optional):

- Add `stamp_audit_cases` to your world JSON (for example `worlds/main_world.json`) to define a small curated list of stamp dry-runs.
- `python -m mesh_cli verify-all --artifacts artifacts` writes `artifacts/stamp_audit.json`, including full `entity_changes` plus the first 200 `tile_changes` (with a separate total count for churn control).

For in-scene authored grids (no external Tiled file), the tilemap section may also include:

- `tilemap.width` / `tilemap.height` (tile grid dimensions, ints > 0)
- `tilemap.tilewidth` / `tilemap.tileheight` (tile size in pixels, ints > 0)

Tooling helpers:

- Bootstrap a new scene file (tilemap + optional backgrounds/spawns): `python -m mesh_cli scene create ...`
- Initialize a blank grid + layers: `python -m mesh_cli scene tilemap init ...`
- Resize a grid deterministically: `python -m mesh_cli scene tilemap resize ...`
- Flood-fill a region safely: `python -m mesh_cli scene tilemap flood-fill ...`
- Add a scene to a world file: `python -m mesh_cli world add-scene worlds/main_world.json --key my_scene --path scenes/my_scene.json`
- Link two scenes via deterministic `SceneTransition` entities: `python -m mesh_cli world link-scenes worlds/main_world.json --from-key a --to-key b --from-scene scenes/a.json --to-scene scenes/b.json ...`

Example workflow (blank grid then stamp a room):

```bash
python -m mesh_cli scene tilemap init scenes/foo.json --width 40 --height 30 --tile-w 16 --tile-h 16 --layer Ground:-100 --layer Walls:-50 --fill Ground:5
python -m mesh_cli scene stamp scenes/foo.json --stamp packs/core_regions/stamps/basic_room_10x8.json --x 10 --y 10
```

Example workflow (bootstrap a new scene + wire into a world):

```bash
python -m mesh_cli scene create scenes/foo.json --width 40 --height 30 --tile-w 16 --tile-h 16 --layer Ground:-100 --layer Walls:-50 --collision-layer Ground --spawn default:80:80
python -m mesh_cli world add-scene worlds/main_world.json --key foo --path scenes/foo.json
python -m mesh_cli world link-scenes worlds/main_world.json --from-key door_field --to-key foo --from-scene scenes/door_field.json --to-scene scenes/foo.json --from-x 480 --from-y 64 --to-x 32 --to-y 64 --from-spawn default --to-spawn default --bidirectional
```

Example workflow (one-command room scaffold):

```bash
python -m mesh_cli room scaffold \
  --world worlds/main_world.json \
  --from-scene scenes/door_field.json \
  --door-macro packs/core_regions/macros/door_to_upper_hall.json \
  --to-scene scenes/foo.json \
  --to-stamp packs/core_regions/stamps/basic_room_10x8.json \
  --grid 40x30 \
  --tile 16x16 \
  --layers Ground:-100,Walls:-50 \
  --collision-layer Ground \
  --stamp-origin 10,10 \
  --spawn-id foo_entry \
  --anchor cursor
```

Flood fill is bounded by `--max-tiles` (default 5000). If the fill would exceed this, the command errors unless `--clip` is provided, in which case it writes the first `max_tiles` visited by a deterministic BFS traversal (fixed neighbor order).

### Tile Properties

- The loader surfaces Tiled layer/object `properties` and per-tile tileset properties on every spawned sprite as `sprite.mesh_tile_properties`.
- Recognized keys today:
  - `tile_tag` / `tag` (string) -- overrides the sprite's collision tag, enabling rule-based filtering per tile or per layer.
  - `tile_damage` / `damage_per_second` (number) -- applies continuous damage (per second) to colliding sprites that expose a `Health` behaviour. The engine multiplies the value by `dt`, so `18` equates to 18 HP/sec.
- Scene-level layer configs can also supply a `properties` object to seed defaults before the Tiled data overrides them.
- Example: the demo red hazard tiles ship with `{ "tile_tag": "hazard", "tile_damage": 18 }`, making them dangerous without bespoke behaviours.

## Entity Objects

Each entry in `entities` describes a sprite. The loader clones `DEFAULT_ENTITY` inside `engine/scene_loader.py`, so missing optional fields are patched in. Required fields are marked with **bold**.

| Field | Type | Required | Default | Notes |
| ----- | ---- | -------- | ------- | ----- |
| `name` | string | no | `null` | Used for debugging and lookups (`find_sprite_by_name`). |
| `sprite` | string | **yes** | `assets/placeholder.png` | File path loaded via `AssetManager`. |
| `x` | number | **yes** | none | Horizontal world position in pixels. |
| `y` | number | **yes** | none | Vertical world position in pixels. |
| `scale` | number | no | `1.0` | Sprite scaling factor. |
| `rotation` | number | no | `0` | Degrees, clockwise. |
| `layer` | string | no | `"entities"` | Must match a layer name or one will be created. |
| `render_layer` | integer | no | `0` | Draw order tier for HD-2D sorting. Lower values draw earlier (further back). |
| `depth_z` | number | no | `0.0` | Fine depth value within a render layer (used by `explicit_z` mode). |
| `shadow_enabled` | bool | no | `true` | Enable drop shadow for this entity. Set to `false` to hide shadow. |
| `shadow_scale` | number | no | `1.0` | Multiplier for shadow size (0.5 = half size, 2.0 = double). |
| `shadow_alpha` | number | no | auto | Override shadow opacity (0.0 to 1.0). Default is computed from depth. |
| `shadow_offset_y` | number | no | auto | Override shadow Y offset in pixels. Default is computed from depth. |
| `shadow_contact_enabled` | bool | no | scene | Enable contact shadow for this entity. Defaults to scene setting. |
| `shadow_contact_scale` | number | no | `0.55` | Contact shadow scale relative to base (smaller = tighter). |
| `shadow_contact_alpha` | number | no | auto | Override contact shadow alpha (0.0 to 1.0). Default is 1.35× base. |
| `shadow_ao_enabled` | bool | no | scene | Enable AO shadow for this entity. Defaults to scene setting (usually false). |
| `depth_tint_enabled` | bool | no | `true` | Enable depth tinting for this entity (when scene tinting is on). |
| `depth_tint_strength` | number | no | scene | Override tint strength for this entity (0.0 to 1.0). |
| `outline_enabled` | bool | no | scene | Enable faux outline for this entity. Defaults to scene setting. |
| `outline_color_rgba` | array | no | scene | Override outline color (RGBA). |
| `outline_strength` | number | no | scene | Override outline strength (0.0 to 1.0). |
| `outline_radius_px` | number | no | scene | Override outline radius in pixels. |
| `tag` | string\|null | no | `null` | Arbitrary label used by collision filtering and DevTools. |
| `solid` | bool | no | `false` | Solid sprites are added to `GameWindow.solid_sprites` for movement blocking. |
| `behaviours` | array | no | `[]` | Behaviour declarations (see below). |
| `behaviour_config` | object | no | `{}` | Map of behaviour names to config objects (see below). |
| `patrol_points` | array | no | `[]` | Used by `PatrolBehaviour`. |
| `patrol_speed` | number | no | `80.0` | Patrol helper default. |
| `follow_target` | string\|null | no | `null` | Used by `FollowBehaviour`. |
| `follow_speed` | number | no | `100.0` | Follow helper default. |
| `dialogue` | object | no | `{}` | Optional data block consumed by the `Dialogue` behaviour (`speaker`, `lines`, `nodes`, `start`, `auto_start`, `once`). |
| `dialogue_lines` | array | no | `[]` | Legacy helper (list of strings/dicts) merged into `dialogue.lines` when provided. |
| `sprite_sheet` | object | no | `{}` | Sprite sheet slicing instructions (see below). |
| `animations` | object | no | `{}` | Named animation clips referencing sprite-sheet frames. |
| `movement_state` | string | no | unset | Runtime helper set by behaviours (e.g., `"idle"`, `"walk"`). |
| `animation_state` | string | no | `"idle"` | Current animation state (read/written at runtime). |
| `animation_frame_rate` | number | no | `8.0` | Fallback FPS when a clip omits `fps`. |
| `animation_blend` | number | no | `0.0` | Default cross-fade duration (seconds) used when switching states. |
| `animation_root_motion` | bool\|number\|object | no | `false` | Enables event-driven root motion; see _Animation events & root motion_. |
| `trigger_radius` | number\|null | no | `null` | `TriggerZone` helper value. |
| `trigger_target` | string\|null | no | `null` | `TriggerZone` target name. |
| `on_trigger` | string\|null | no | `null` | Event label for `TriggerZone`. |
| `require_flags` | array | no | `[]` | Load-time gate: entity spawns only if all required flags are true (player is never filtered). |
| `forbid_flags` | array | no | `[]` | Load-time gate: entity spawns only if all forbidden flags are false (player is never filtered). |

### Entity Flag Gating

- Entities can be conditionally omitted at load time via `require_flags` and/or `forbid_flags`.
- The gate uses `GameWindow.get_flag(name, default=False)`.
- Safety: player entities are always created even if the authored payload incorrectly gates them.

```json
{
  "id": "reward_loot_200_160_0_0",
  "prefab_id": "torch_wisp",
  "behaviours": [],
  "require_flags": ["demo.reward_claimed"],
  "x": 200,
  "y": 160
}
```

### Dialogue Nodes

- `dialogue.lines` remains the quickest way to script linear exchanges.
- For branching conversations, define `dialogue.nodes` (object keyed by node ID) plus an optional `dialogue.start` pointer.
- Each node accepts `speaker`, `text`, `choices[]`, and `next` (fallback when no choice is provided).
- Choice dictionaries support:
  - `text` (required)
  - `next` (node ID to visit next) or `end` to close the conversation
  - `require_flags` / `forbid_flags` (arrays or comma-separated strings) to gate availability
  - `once` (bool) to hide the choice after it fires once
  - `set_flags`, `clear_flags`, `inc_counters` to mutate `GameWindow.game_state`
  - `event` (string or `{ type, payload }`) plus optional `event_payload` to emit Mesh events when the choice resolves
- Disabled choices remain visible (greyed out) until their `require_flags` are satisfied so players know which quests unlock new lines.
- The behaviour emits helper events:
  - `dialogue_line` (existing) for every rendered line
  - `dialogue_choice` when a choice resolves (payload includes `entity`, `owner`, `node`, `choice_id`, `choice_text`, `next`, `actor`)
  - `dialogue_choice_cursor` whenever the highlighted choice changes

### Global Game State

- `GameWindow` owns a `GameState` dataclass with three public dictionaries:
  - `flags[str] -> bool`
  - `counters[str] -> float`
  - `values[str] -> Any`
- Helper methods keep interaction ergonomic and future-proof:
  - `set_flag(name, value=True)` / `get_flag(name, default=False)`
  - `inc_counter(name, amount=1.0)` / `get_counter(name, default=0.0)`
- Behaviours can stash arbitrary data under `game_state.values[...]`. The engine reserves `values.next_spawn_point` for cross-scene spawn hand-offs.
- `SetGameStateOnEvent` is a declarative behaviour that listens for Mesh events (such as `scene_transition`) and updates flags/counters without custom code.

### Quest data & journal overlay

- Narrative progress lives outside the scene file in `assets/data/quests.json`. Each quest entry lists ordered stages, optional start/complete triggers, and a reward payload. See `docs/quests.md` for the schema and QuestManager helper APIs.
- `GameWindow.quest_manager` loads the JSON file at boot, keeps per-save progress in `game_state.values.quests`, and emits helper events (`quest_stage_started`, `quest_stage_completed`, `quest_completed`) so scenes can flip flags or spawn content when objectives advance.
- The Quest Log overlay is bound to the `show_quests` action (default `Q`). It blocks player input while visible and shows every quest with its current objective plus an `X/Y objectives complete` counter.
- The Inventory overlay is bound to the `show_inventory` action (default `TAB`). It mirrors `game_state.values.inventory` using `assets/data/items.json`, so designers can verify pickups or quest rewards without leaving the runtime.

### Spawn Markers & SceneTransitions

- To reposition the player when a new scene loads, place an entity with `"tag": "spawn_point"` and a `"spawn_id": "my_marker"` field anywhere in the destination scene.
- When a `SceneTransition` behaviour fires it calls `GameWindow.set_next_spawn_point(spawn_id)` and then `request_scene_change`. During the next `load_scene` call the runtime searches for a matching spawn marker and moves the player sprite to that marker's coordinates before gameplay resumes.
- Spawn IDs are case-insensitive, can reuse the entity's `name`, and are logged to the console when no matching marker exists.
- Combine spawn markers with `ConditionalActivator` to keep blockers hidden until the relevant quest flags flip, or with `SetGameStateOnEvent` to track which doors have been used.

### Behaviour Entries

`behaviours` declares which runtime components attach to the sprite. Each entry is either:

1. A string (shorthand): `"PlayerController"` -> `{ "type": "PlayerController" }`.
2. An object with both a `type` and a `params` object (preferred).

```json
{
  "behaviours": [
    "PlayerController",
    {
      "type": "Health",
      "params": {
        "max_hp": 5
      }
    }
  ]
}
```

#### Validation rules

- `type` must match a behaviour registered through `engine.behaviours.registry.register_behaviour`.
- `params` must be an object (or omitted). Each key is checked against the behaviour's `PARAM_DEFS`.
  - Unknown keys produce warnings such as:
    `Entity 'Slime': behaviour[0] Health received unknown param "hp" (did you mean "max_hp"?)`.
  - Type mismatches also warn or error:
    `Entity 'GuardA': behaviour[1] Patrol param "patrol_speed" must be float, got string ("fast")`.
- Inline fields outside `params` are still accepted for backwards compatibility. The loader rewrites them into the behaviour config map, but new content should supply everything inside `params` to keep validation accurate.

Behaviour metadata (type names, parameter lists, defaults, descriptions) ships from the engine at runtime, so CLI tools stay synchronized with custom behaviours without editing this spec.

The engine merges values in this order: explicit `behaviours[].params` -> `behaviour_config` map -> legacy top-level fields. This ensures console edits survive hot reloads while still honoring scene-specified overrides.

### Behaviour Config Map

`behaviour_config` is an object keyed by behaviour name. Each value is another object whose keys/values match the behaviour's `config_fields`. Example:

```json
"behaviour_config": {
  "Health": {
    "max_hp": 10,
    "invulnerable": false
  },
  "Patrol": {
    "patrol_speed": 60.0
  }
}
```

Use the dev console (`entity beh list/set/reload`) to inspect and tweak these entries at runtime. When both the config map and inline behaviour entries provide a field, the inline value wins.

### Behaviour Metadata Lookup

Use the dev console (`behaviour <name>`) or `engine.behaviours.registry.list_behaviours()` to inspect available behaviours, their descriptions, and configuration fields. The validator will warn when a referenced behaviour is unknown.

### SequencePlayer Step Schema

`SequencePlayer` consumes a `steps` array where each entry is a dictionary containing at least a `type`. Supported step types today:

- `wait`: `{ "type": "wait", "duration": 1.0 }` pauses for the requested number of seconds.
- `move_to`: `{ "type": "move_to", "x": 200, "y": 220, "speed": 90, "tolerance": 2.0 }` moves the owning sprite toward a coordinate. Optional fields include `relative` (treat `x`/`y` as offsets) and `dx`/`dy` offsets.
- `dialogue`: `{ "type": "dialogue", "speaker": "Guide", "lines": ["..."], "line_duration": 1.5, "wait_for_close": false }` feeds entries into the DialogueBox. Lines auto-advance unless `wait_for_close` is true. Provide `post_wait` to hold the last line on screen before continuing or `lock_player_input: false` to temporarily hand control back to the player.
- `signal`: `{ "type": "signal", "event": "sequence_complete", "payload": { "sequence": "intro" } }` emits a Mesh event.
- `wait_for_event`: `{ "type": "wait_for_event", "event": "door_opened", "field": "door", "value": "north", "timeout": 5.0 }` blocks the sequence until a matching event arrives (or the optional timeout elapses).

Sequences can auto-start, respond to Mesh events, or remain dormant until triggered via future behaviours. While active, the behaviour can lock player input through `GameWindow.lock_player_input`, ensuring PlayerController ignores movement until the cutscene completes.

### Example Entity

```json
{
  "name": "Hazard",
  "x": 650,
  "y": 250,
  "sprite": "assets/placeholder.png",
  "scale": 0.7,
  "layer": "entities",
  "tag": "hazard",
  "behaviours": [
    {
      "type": "DamageOnTouch",
      "target_name": "Player",
      "damage": 2.0
    }
  ]
}
```

### Sprite Sheet Animation

Sprite-based animation is handled by `engine/animation.AnimationFactory`. Any entity can opt in by providing a sprite sheet description alongside its base texture path:

```json
{
  "sprite": "assets/sprites/animated_player.png",
  "sprite_sheet": {
    "frame_width": 64,
    "frame_height": 64,
    "margin": 0,
    "spacing": 0,
    "columns": 4,
    "rows": 2
  }
}
```

You can scaffold these fields from a spritesheet image using:

`python -m mesh_cli sprite import-sheet assets/sprites/animated_player.png --prefab-id player_anim --frame-w 64 --frame-h 64 --anim idle:0-3:8 --out assets/prefabs.json`

Or import directly from an Aseprite JSON export (frame tags become animations):

`python -m mesh_cli sprite import-aseprite assets/sprites/animated_player.json --prefab-id player_anim --out assets/prefabs.json`

`frame_width` and `frame_height` are required positive integers so the loader can slice the sheet consistently regardless of the image's true dimensions. The remaining fields are optional and default to zero (or unlimited for `columns`/`rows`).

For `import-aseprite`, export with array or hash frame format, trimming disabled, and uniform frame sizes in a grid layout. Frame durations are averaged to derive FPS per tag.

### Animation events & root motion

- Clip-level `events` still require `{ "frame": <int>, "label": "name" }`, but you can now attach arbitrary extra keys. The runtime copies those keys onto the emitted `animation_event` payload so tooling or behaviours can react without new API.
- Entities may opt into movement driven by those payloads via `animation_root_motion`:
  - Accepts `true`/`false`, a numeric scale (used as a multiplier), or an object `{ "enabled": true, "labels": ["stride"], "space": "local", "collision": true, "scale": 1.0 }`.
  - When enabled, events that include `move`, `displacement`, or `dx`/`dy` automatically translate the sprite (rotated into world space when `space` is `local`).
  - Root motion respects solid collisions by default; set `collision: false` or override per-event via `"move_collision": false` to bypass.
  - Use `labels` to whitelist which event names are allowed to impart motion; omit it to accept any payload that declares a displacement.
- Applied motion is reported back on the event payload (`root_motion: { dx, dy }`) and the `position` field reflects the post-move coordinates.

### Animation Clips

`animations` is a map of `state_name -> clip config`. Each config supports:

- `frames` (array<int>) -- Required list of frame indices sourced from the sprite sheet.
- `fps` / `frame_rate` (number) -- Optional per-clip speed (defaults to `animation_frame_rate`).
- `loop` (bool) -- Whether the clip restarts after reaching the end.
- `blend` (number) -- Optional override for how long (seconds) to cross-fade when entering this clip. Falls back to the entity's `animation_blend` or zero.
- `events` (array) -- Optional list of `{ "frame": <index>, "label": "event_name" }` entries. Events fire every time the playhead lands on the specified frame (including loops) and route through `GameWindow.emit_signal("animation_event", ...)`.
- `transition` (object \| string \| number) -- Optional per-clip transition override. Use `{ "mode": "snap" }` (or the string `"snap"`) to bypass blending, or `{ "hold": 0.25 }` to freeze the final frame for 0.25s after a non-looping clip completes. Numbers act as shorthand for hold durations; legacy `transition_mode` + `hold` keys remain accepted.

Hold timers only apply after a non-looping clip hits its final frame. The animator keeps displaying that frame (and suppresses blending) until the timer expires, giving reaction poses a bit of breathing room before locomotion retakes control. Snap transitions simply skip any cross-fade so quick attacks or impacts feel immediate.

Example clip with an event marker that lines up with the hit frame of an attack:

```json
"attack": {
  "frames": [4, 5, 6, 7],
  "fps": 12,
  "loop": false,
  "blend": 0.2,
  "transition": { "mode": "snap", "hold": 0.2 },
  "events": [
    { "frame": 3, "label": "attack_contact" }
  ]
}
```

Named animation clips live in the matching `animations` object:

```json
"animations": {
  "idle":  { "frames": [0, 1, 2, 3], "fps": 4, "loop": true },
  "walk":  { "frames": [4, 5, 6, 7], "fps": 8, "loop": true },
  "attack": { "frames": [8, 9, 10], "fps": 10, "loop": false }
}
```

- `frames` is required and contains zero-based indices into the sliced sprite sheet.
- `fps` (optional) overrides the play speed for that clip. When omitted, the engine falls back to `animation_frame_rate` (default `8.0`).
- `loop` (optional) defaults to `true`.
- `transition` lets you mark clips as snap (skip blending) or request final-pose holds after they finish, helping hit reactions and attacks land crisply.
- Shorthand entries like `"idle": [0, 1, 2]` still work and inherit the default fps/loop values.

The runtime picks a default state using `default_animation`, then `animation_state`, then the first key inside `animations`. Behaviours (such as `PlayerController`) can update `mesh_entity_data["animation_state"]` every frame to switch clips; `GameWindow._update_animation_stage` forwards that state to the `AnimationPlayer` before it advances time. This keeps the system behaviour-driven and agnostic to the sprite size.

Behaviours request states with simple priorities so higher-level actions briefly override locomotion without extra glue. Out of the box:

- `PlayerController` updates `movement_state` + base `animation_state` (`"idle"`, `"walk"`) and pulses `"interact"` when the interact key fires.
- Any `on_damage` call (tile hazards, `DamageOnTouch`, etc.) applies `"attack"` on the source and `"hit"` on the target for a short window.

Author clips named after these defaults (e.g., `animations.hit`, `animations.interact`) to get instant feedback, then layer in additional behaviours for bespoke states.

> Legacy note: `behaviours/animator.py` continues to support per-frame texture lists for UI elements or one-off effects, but sprite-sheet-driven entities should prefer the declarative `sprite_sheet` + `animations` schema.

## Validation Expectations

When a scene is loaded or validated:

- Missing required numeric/string fields on an entity produce errors.
- Unknown behaviour names produce errors.
- Field type mismatches (e.g., `x` provided as a string) produce errors.
- Unexpected keys generate warnings so you can catch typos.
- Behaviour config is cross-checked against its schema, but unknown config keys remain allowed.

See `engine/scene_loader.py` and the CLI validator (`python -m engine.tooling.scene_validate path/to/scene.json`) for the authoritative validation logic.

## Main Menu Settings

The engine configuration (`config.json`) supports a `main_menu_scene` field. When set, the engine boots into this scene instead of `start_scene`.

- `main_menu_scene`: Path to the main menu scene file (e.g., `scenes/main_menu.json`).

### Layers

Layers are declared up front and mapped to `arcade.SpriteList` instances inside the engine (`background`, `entities`, `foreground`). Entities select a layer via `layer`; unknown layers are auto-created (with a warning) which keeps the format flexible.

## Asset References & Refactoring

Scene files reference assets via relative paths (e.g. `assets/sprites/hero.png`). The Editor's Project Explorer supports **Safe Refactoring** for these paths:

-   **Renaming/Moving** an asset automatically updates all matching string references in `.json` scene files.
-   **Deleting** an asset warns if it is referenced by any scene.
-   Refactoring is atomic (Two-Phase Commit) and includes a preview of affected files.

