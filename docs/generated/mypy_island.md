# Typing Safety Island

The **typing safety island** is a two-tier mypy approach:

1. **Baseline ratchet** (`mypy-gate`): Prevents new errors project-wide, but allows existing known errors in legacy monoliths via `tooling/mypy_baseline.txt`.

2. **Strict island** (`mypy-island`): Zero-tolerance strict typing on curated, stable subsystems that should remain fully typed.

## Island Modules

The island currently covers these well-typed subsystems:

| Category | Module | Purpose |
|----------|--------|---------|
| Input Routing | `engine/capture_mouse_router_model.py` | Mouse event routing model |
| Input Routing | `engine/capture_key_router_model.py` | Keyboard event routing model |
| Input Routing | `engine/capture_runtime_focus_model.py` | Focus management model |
| Save Schema | `engine/save_runtime/schema.py` | Versioned save data schema |
| Physics | `engine/physics_model.py` | Physics state model |
| Physics | `engine/sensors_model.py` | Sensor state model |
| Physics | `engine/physics_broadphase_key_model.py` | Broadphase key model |
| Editor | `engine/editor/project_explorer_rank_model.py` | Project explorer ranking |
| Animation | `engine/sprite_animator.py` | Sprite animation runtime |
| Pathfinding | `engine/nav_grid.py` | Navigation grid |
| Pathfinding | `engine/astar.py` | A* pathfinding |

## Expanding the Island

To add a module to the strict island:

1. **Check current typing status**:
   ```bash
   python -m mypy --strict path/to/module.py
   ```

2. **Fix any type errors** – the island enforces:
   - `--warn-return-any`
   - `--warn-unused-ignores`
   - `--no-implicit-optional`

3. **Add to the island list** in `tooling/mypy_island.py`:
   ```python
   TYPED_ISLAND_MODULES: tuple[str, ...] = (
       # ... existing modules ...
       "engine/your_new_module.py",
   )
   ```

4. **Verify**:
   ```bash
   python -m tooling.mypy_island
   ```

## Running the Checks

```bash
# Run just the island check
python -m tooling.mypy_island

# List island modules
python -m tooling.mypy_island --list

# Full verify-all (includes island check)
python -m mesh_cli verify-all --out-dir artifacts
```

## Design Rationale

- **`--follow-imports=skip`**: Only checks the island modules themselves, not their dependencies. This allows the island to grow incrementally without requiring perfect typing across the entire import graph.

- **Separate from baseline**: The island is additive protection. The baseline prevents new errors anywhere; the island prevents any errors in curated modules.

- **Model files first**: The island focuses on pure data models and algorithms (routers, schemas, physics models, pathfinding) which are easiest to type strictly and benefit most from type safety.
