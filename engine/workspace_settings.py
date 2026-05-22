"""Workspace settings persistence."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from engine import json_io
_LOG = logging.getLogger(__name__)


def _get_default_repo_root() -> Path:
    """Lazy import to avoid import-time resolution."""
    from engine.repo_root import get_repo_root
    return get_repo_root()


def resolve_workspace_path(repo_root: Path | None = None) -> Path:
    """Resolve the workspace.json path, using repo_root or defaulting to get_repo_root()."""
    root = repo_root if repo_root is not None else _get_default_repo_root()
    return root / "workspace.json"


@dataclass
class WorkspaceSettings:
    entity_panels_open: bool = False
    command_palette_open: bool = False
    scene_switcher_open: bool = False
    scene_browser_open: bool = False
    asset_browser_open: bool = False
    asset_browser_filter: str = ""
    asset_browser_kind: str = "All"
    outliner_search: str = ""
    assets_search: str = ""
    history_search: str = ""
    problems_search: str = ""
    project_search: str = ""
    project_explorer_recents: list[dict[str, str]] = field(default_factory=list)
    light_occluder_tool: str | None = None  # "light", "occluder", or None
    outliner_focus: str = "outliner"  # "outliner" or "inspector"
    last_scene_id: str | None = None
    last_camera_center: list[float] | None = None
    left_dock_tab: str = "Outliner"  # "Project", "Scene", or "Outliner"
    right_dock_tab: str = "Inspector"  # Allowed values from engine.editor.dock_tab_registry.RIGHT_DOCK_TABS.
    dock_left_w: int = 320  # Left dock width
    dock_right_w: int = 320  # Right dock width
    # Dock collapse / maximize state
    dock_left_collapsed: bool = False
    dock_right_collapsed: bool = False
    viewport_maximized: bool = False
    # Ghost originals settings (for alt-drag duplicate visual feedback)
    ghost_originals_enabled: bool = True
    ghost_originals_alpha: int = 90  # 0..255
    ghost_originals_dim_scale: float = 0.65  # 0.0..1.0
    # HD-2D defaults preset (null = disabled, or "soft", "crisp", "noir", "dreamy")
    hd2d_default_preset_id: str | None = None
    # HD-2D batch paste radius in pixels (16..512)
    hd2d_batch_radius_px: int = 96
    # Debug panel event monitor filters
    debug_event_type_filter: str = ""
    debug_event_entity_id: str = ""
    debug_event_limit: int = 20

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkspaceSettings:
        # Safe unpacking with defaults
        # Clamp ghost alpha to 0..255
        raw_alpha = data.get("ghost_originals_alpha", 90)
        ghost_alpha = max(0, min(255, int(raw_alpha) if isinstance(raw_alpha, (int, float)) else 90))
        # Clamp ghost dim scale to 0..1
        raw_scale = data.get("ghost_originals_dim_scale", 0.65)
        ghost_scale = max(0.0, min(1.0, float(raw_scale) if isinstance(raw_scale, (int, float)) else 0.65))

        return cls(
            entity_panels_open=bool(data.get("entity_panels_open", False)),
            command_palette_open=bool(data.get("command_palette_open", False)),
            scene_switcher_open=bool(data.get("scene_switcher_open", False)),
            scene_browser_open=bool(data.get("scene_browser_open", False)),
            asset_browser_open=bool(data.get("asset_browser_open", False)),
            asset_browser_filter=str(data.get("asset_browser_filter", "")),
            asset_browser_kind=str(data.get("asset_browser_kind", "All")),
            outliner_search=str(data.get("outliner_search", "")),
            assets_search=str(data.get("assets_search", data.get("asset_browser_filter", ""))),
            history_search=str(data.get("history_search", "")),
            problems_search=str(data.get("problems_search", "")),
            project_search=str(data.get("project_search", "")),
            project_explorer_recents=_coerce_recent_payloads(data.get("project_explorer_recents", [])),
            light_occluder_tool=data.get("light_occluder_tool"),
            outliner_focus=str(data.get("outliner_focus", "outliner")),
            last_scene_id=data.get("last_scene_id"),
            last_camera_center=data.get("last_camera_center"),
            left_dock_tab=str(data.get("left_dock_tab", "Outliner")),
            right_dock_tab=str(data.get("right_dock_tab", "Inspector")),
            dock_left_w=int(data.get("dock_left_w", 320)),
            dock_right_w=int(data.get("dock_right_w", 320)),
            dock_left_collapsed=bool(data.get("dock_left_collapsed", False)),
            dock_right_collapsed=bool(data.get("dock_right_collapsed", False)),
            viewport_maximized=bool(data.get("viewport_maximized", False)),
            ghost_originals_enabled=bool(data.get("ghost_originals_enabled", True)),
            ghost_originals_alpha=ghost_alpha,
            ghost_originals_dim_scale=ghost_scale,
            hd2d_default_preset_id=_coerce_hd2d_default_preset_id(data.get("hd2d_default_preset_id")),
            hd2d_batch_radius_px=_coerce_hd2d_batch_radius_px(data.get("hd2d_batch_radius_px", 96)),
            debug_event_type_filter=str(data.get("debug_event_type_filter", "")),
            debug_event_entity_id=str(data.get("debug_event_entity_id", "")),
            debug_event_limit=_coerce_debug_event_limit(data.get("debug_event_limit", 20)),
        )


def get_workspace_path(repo_root: Path) -> Path:
    return repo_root / "workspace.json"


def load_workspace(repo_root: Path) -> WorkspaceSettings:
    """Load workspace settings from the project root."""
    path = get_workspace_path(repo_root)
    if not path.exists():
        return WorkspaceSettings()

    try:
        data = json_io.read_json(path)
        if not isinstance(data, dict):
            return WorkspaceSettings()
        return WorkspaceSettings.from_dict(data)
    except Exception as e:
        _LOG.warning("Failed to load workspace settings: %s", e)
        return WorkspaceSettings()


def save_workspace(repo_root: Path, settings: WorkspaceSettings) -> None:
    """Save workspace settings to the project root."""
    path = get_workspace_path(repo_root)
    try:
        data = asdict(settings)
        json_io.write_json_atomic(path, data)
    except Exception as e:
        _LOG.error("Failed to save workspace settings: %s", e)


def _coerce_recent_payloads(raw: Any, *, limit: int = 8) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, str]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        rel_path = entry.get("rel_path")
        label = entry.get("label")
        if not isinstance(kind, str) or kind not in ("scene", "asset", "path"):
            continue
        if not isinstance(rel_path, str) or not rel_path.strip():
            continue
        if not isinstance(label, str) or not label.strip():
            continue
        result.append({"kind": kind, "rel_path": rel_path, "label": label})
        if len(result) >= limit:
            break
    return result


def _coerce_hd2d_default_preset_id(raw: Any) -> str | None:
    """Coerce and validate HD2D default preset ID.

    Returns None if invalid, otherwise returns a valid preset ID string.
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    preset_id = raw.strip().lower()
    if not preset_id:
        return None
    # Only accept known preset IDs
    if preset_id in ("soft", "crisp", "noir", "dreamy"):
        return preset_id
    return None


def _coerce_hd2d_batch_radius_px(raw: Any) -> int:
    """Coerce and clamp HD2D batch radius to valid bounds (16..512).

    Returns default (96) if invalid, otherwise returns clamped value.
    """
    if raw is None:
        return 96
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 96
    # Clamp to valid range
    return max(16, min(512, value))


def _coerce_debug_event_limit(raw: Any) -> int:
    """Coerce debug event limit to a non-negative integer (default 20)."""
    if raw is None:
        return 20
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 20
    return max(0, value)
