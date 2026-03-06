from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


_REPO_ROOT = Path(__file__).resolve().parents[1]

_HELPER_MODULE_TOKEN = "engine.ui_overlays.widget_overlay_helpers"
_HELPER_NAMES: tuple[str, ...] = (
    "apply_text_input",
    "apply_backspace",
    "apply_nav_key",
    "apply_enter",
    "apply_mouse_scroll",
    "apply_mouse_press",
)

# Ratcheted set of widgetized overlay/controller pairs using helper forwarding.
_TARGET_CONTROLLERS: tuple[Path, ...] = (
    Path("engine/editor/editor_search_controller.py"),         # FindEverythingOverlay
    Path("engine/editor/editor_scene_browse_controller.py"),   # SceneBrowserOverlay
    Path("engine/editor/editor_keybinds_controller.py"),       # KeybindsOverlay
    Path("engine/editor/editor_asset_browser_controller.py"),  # AssetBrowserOverlay
)

# Intentionally empty. Add only temporary exceptions as:
# {"engine/editor/example.py": {"apply_nav_key"}}
_ALLOWLIST_MISSING_HELPERS: dict[str, set[str]] = {}


def _path_key(path: Path) -> str:
    return path.as_posix()


def _token_present(source: str, token: str) -> bool:
    return re.search(rf"\b{re.escape(token)}\b", source) is not None


def test_widget_overlay_helper_allowlist_is_valid_and_not_stale() -> None:
    valid_paths = {_path_key(path) for path in _TARGET_CONTROLLERS}
    stale_paths = sorted(set(_ALLOWLIST_MISSING_HELPERS.keys()) - valid_paths)
    assert not stale_paths, f"stale allowlist controller paths: {stale_paths}"

    for path_key, helper_names in sorted(_ALLOWLIST_MISSING_HELPERS.items()):
        unknown_helpers = sorted(set(helper_names) - set(_HELPER_NAMES))
        assert not unknown_helpers, f"{path_key}: unknown helper allowlist entries: {unknown_helpers}"


def test_widgetized_controllers_reference_shared_forwarding_helpers() -> None:
    for rel_path in _TARGET_CONTROLLERS:
        abs_path = _REPO_ROOT / rel_path
        source = abs_path.read_text(encoding="utf-8")
        assert _HELPER_MODULE_TOKEN in source, f"{rel_path.as_posix()}: missing helper module reference"

        present_helpers = {name for name in _HELPER_NAMES if _token_present(source, name)}
        missing_helpers = set(_HELPER_NAMES) - present_helpers

        allowed_missing = set(_ALLOWLIST_MISSING_HELPERS.get(_path_key(rel_path), set()))
        unexpected_missing = sorted(missing_helpers - allowed_missing)
        assert not unexpected_missing, (
            f"{rel_path.as_posix()}: missing helper references not allowlisted: {unexpected_missing}"
        )

        stale_allowlist_entries = sorted(allowed_missing - missing_helpers)
        assert not stale_allowlist_entries, (
            f"{rel_path.as_posix()}: stale allowlist entries (helper now present): {stale_allowlist_entries}"
        )
