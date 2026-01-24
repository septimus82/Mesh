I have implemented the **Asset Placement Mode** with a ghost preview overlay in the editor.

**Key Features Implemented:**

1.  **Placement Mode State**:
    *   Modified `EditorController` to track `asset_place_active` and `asset_place_path`.
    *   Selecting an image in the asset browser now enters "Placement Mode" instead of spawning immediately.
    *   The Asset Browser closes automatically upon activation.

2.  **Ghost Preview Overlay**:
    *   Created `engine/asset_place_overlay.py`: Draws a semi-transparent (alpha 128) preview of the asset at the mouse cursor.
    *   Integrated into `EditorController.draw_world` to render in world space.
    *   Supports grid snapping (`snap_world_point`).

3.  **Input Handling**:
    *   **Mouse Left Click**: Places the asset at the snapped cursor position (persists in placement mode allowing "stamping" multiple copies).
    *   **Enter Key**: Places the asset once at the current mouse position.
    *   **Right Click / Esc**: Exits placement mode.
    *   Implemented via `engine/editor_runtime/input.py` and `engine/editor_controller.py`.

4.  **Testing**:
    *   Created `tests/test_asset_place_mode_contract.py`.
    *   Verified interaction flow: Activation -> State Change -> Input -> Placement -> Cancellation.
    *   Verified ID determinism and scene modifications increment correctly.
    *   **Status**: `pytest` passed.

**Verification**:
*   `python -m pytest -q` passed (including new tests).
*   `python -m tooling.mypy_gate` passed.
*   `python -m mesh_cli verify-all` passed 100%.

The feature is headless-safe and maintains existing editor behavior for non-image assets.