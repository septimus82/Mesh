# Public API (v1)

Mesh guarantees compatibility only for symbols under `engine.public_api.*`.
Everything outside `engine.public_api` is internal and may change without notice.

## Supported Surface

### `engine.public_api.types`
- `EntityId`
- `ScenePath`
- `Vec2`

### `engine.public_api.assets`
- `get_project_root()`
- `resolve_asset_path(path, *, project_root=None)`

### `engine.public_api.runtime`
- `load_scene_payload(scene_path)`
- `run_game(main_scene_path, *, project_root=None)`

### `engine.public_api`
- Re-exports the curated symbols above.

## Template Game

See `examples/template_game/`.

Run:

```powershell
python examples/template_game/main.py
```

## Requesting API Additions

1. Add a wrapper/re-export in `engine/public_api/*`.
2. Update `tests/baselines/public_api_exports.txt`.
3. Add/update tests validating import contract and export ratchet.

