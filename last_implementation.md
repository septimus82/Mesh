I have implemented the Editor Asset Browser.

**Features:**
- **Indexing (`engine/asset_index.py`)**: Scans `assets/` folder, creating `AssetRow` records with deterministic sorting.
- **Overlay (`engine/ui_overlays/asset_browser_overlay.py`)**: Split-pane UI (List + Details), Search Bar, Kind Filter (Image/Audio/JSON/All).
- **Integration**:
  - `EditorController` manages active state, selection cursor, and filtering.
  - `WorkspaceSettings` persists `asset_browser_open`, `asset_browser_filter`, and `asset_browser_kind`.
  - `Input` handles `Ctrl+Shift+A` toggle and keyboard navigation (Up/Down/PgUp/PgDn, Tab/Shift+Tab for filter cycle).
- **Tests**:
  - `tests/test_asset_index_contract.py`: Verifies deterministic scanning and filtering logic.
  - Regression tests maintenance (`test_game_facade_guard`, `test_release_web_demo_contract`).
- **Verification**: `verify-all` passed cleanly.

**Usage:**
- `Ctrl+Shift+A` to toggle.
- Type to search.
- Tab to cycle kind filters.
- Arrow keys to navigate.
