from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


_REPO_ROOT = Path(__file__).resolve().parents[1]

_HELPER_MODULE_TOKENS: tuple[str, ...] = (
    "engine.ui_overlays.widget_overlay_helpers",
    ".widget_overlay_helpers",
)
_HELPER_NAME = "resolve_preserved_selection_index"

_TARGET_FILES: tuple[Path, ...] = (
    Path("engine/editor/editor_ui_flow_controller.py"),
    Path("engine/ui_overlays/scene_browser_overlay.py"),
    Path("engine/editor/editor_keybinds_controller.py"),
    Path("engine/editor/editor_asset_browser_controller.py"),
)

# Intentionally empty. Add only temporary exceptions as:
# {"engine/editor/example.py": {"resolve_preserved_selection_index"}}
_ALLOWLIST_MISSING: dict[str, set[str]] = {}


def _path_key(path: Path) -> str:
    return path.as_posix()


def _token_present(source: str, token: str) -> bool:
    return re.search(rf"\b{re.escape(token)}\b", source) is not None


def test_selection_helper_allowlist_is_valid_and_not_stale() -> None:
    valid_paths = {_path_key(path) for path in _TARGET_FILES}
    stale_paths = sorted(set(_ALLOWLIST_MISSING.keys()) - valid_paths)
    assert not stale_paths, f"stale allowlist paths: {stale_paths}"

    for path_key, helper_names in sorted(_ALLOWLIST_MISSING.items()):
        unknown_helpers = sorted(set(helper_names) - {_HELPER_NAME})
        assert not unknown_helpers, f"{path_key}: unknown helper allowlist entries: {unknown_helpers}"


def test_widgetized_flows_reference_shared_selection_preserve_helper() -> None:
    for rel_path in _TARGET_FILES:
        abs_path = _REPO_ROOT / rel_path
        source = abs_path.read_text(encoding="utf-8")

        assert any(token in source for token in _HELPER_MODULE_TOKENS), (
            f"{rel_path.as_posix()}: missing widget_overlay_helpers module reference"
        )

        present = _token_present(source, _HELPER_NAME)
        missing = set() if present else {_HELPER_NAME}

        allowed_missing = set(_ALLOWLIST_MISSING.get(_path_key(rel_path), set()))
        unexpected_missing = sorted(missing - allowed_missing)
        assert not unexpected_missing, (
            f"{rel_path.as_posix()}: missing helper references not allowlisted: {unexpected_missing}"
        )

        stale_allowlist_entries = sorted(allowed_missing - missing)
        assert not stale_allowlist_entries, (
            f"{rel_path.as_posix()}: stale allowlist entries (helper now present): {stale_allowlist_entries}"
        )
