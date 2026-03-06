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
_HELPER_NAMES: tuple[str, ...] = (
    "build_empty_row",
    "build_status_row",
    "compose_list_rows",
)

_TARGET_OVERLAYS: tuple[Path, ...] = (
    Path("engine/ui_overlays/find_everything_overlay.py"),
    Path("engine/ui_overlays/scene_browser_overlay.py"),
    Path("engine/ui_overlays/keybinds_overlay.py"),
    Path("engine/ui_overlays/asset_browser_overlay.py"),
)

# Intentionally empty. Add only temporary exceptions as:
# {"engine/ui_overlays/example_overlay.py": {"compose_list_rows"}}
_ALLOWLIST_MISSING_HELPERS: dict[str, set[str]] = {}


def _path_key(path: Path) -> str:
    return path.as_posix()


def _token_present(source: str, token: str) -> bool:
    return re.search(rf"\b{re.escape(token)}\b", source) is not None


def test_widget_overlay_list_row_helper_allowlist_is_valid_and_not_stale() -> None:
    valid_paths = {_path_key(path) for path in _TARGET_OVERLAYS}
    stale_paths = sorted(set(_ALLOWLIST_MISSING_HELPERS.keys()) - valid_paths)
    assert not stale_paths, f"stale allowlist overlay paths: {stale_paths}"

    for path_key, helper_names in sorted(_ALLOWLIST_MISSING_HELPERS.items()):
        unknown_helpers = sorted(set(helper_names) - set(_HELPER_NAMES))
        assert not unknown_helpers, f"{path_key}: unknown helper allowlist entries: {unknown_helpers}"


def test_widgetized_overlays_reference_shared_list_row_helpers() -> None:
    for rel_path in _TARGET_OVERLAYS:
        abs_path = _REPO_ROOT / rel_path
        source = abs_path.read_text(encoding="utf-8")

        assert any(token in source for token in _HELPER_MODULE_TOKENS), (
            f"{rel_path.as_posix()}: missing widget_overlay_helpers module reference"
        )

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
