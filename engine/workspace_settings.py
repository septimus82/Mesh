"""Workspace settings persistence."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

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
    light_occluder_tool: str | None = None  # "light", "occluder", or None
    outliner_focus: str = "outliner"  # "outliner" or "inspector"
    last_scene_id: str | None = None
    last_camera_center: list[float] | None = None
    left_dock_tab: str = "Outliner"  # "Scene" or "Outliner"
    right_dock_tab: str = "Inspector"  # "Inspector", "Assets", or "History"
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
        )


def get_workspace_path(repo_root: Path) -> Path:
    return repo_root / "workspace.json"


def load_workspace(repo_root: Path) -> WorkspaceSettings:
    """Load workspace settings from the project root."""
    path = get_workspace_path(repo_root)
    if not path.exists():
        return WorkspaceSettings()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
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
        # Sort keys for determinism
        text = json.dumps(data, indent=2, sort_keys=True)
        path.write_text(text + "\n", encoding="utf-8")
    except Exception as e:
        _LOG.error("Failed to save workspace settings: %s", e)
