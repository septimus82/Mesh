"""Editor state definitions and constants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import engine.optional_arcade as optional_arcade

# Tool modes
TOOL_MODE_MOVE = "MOVE"
TOOL_MODE_PATH = "PATH"
TOOL_MODE_ZONE = "ZONE"

# Transform submodes (for MOVE tool mode)
TRANSFORM_MODE_MOVE = "move"
TRANSFORM_MODE_ROTATE = "rotate"
TRANSFORM_MODE_SCALE = "scale"

# Entity panel focus constants
ENTITY_PANEL_FOCUS_OUTLINER = "outliner"
ENTITY_PANEL_FOCUS_INSPECTOR = "inspector"

# Entity panel field definitions
ENTITY_PANEL_FIELDS: List[dict[str, str]] = [
    {"key": "mesh_name", "label": "Mesh Name", "kind": "string"},
    {"key": "interact_label", "label": "Interact Label", "kind": "string"},
    {"key": "x", "label": "X", "kind": "float"},
    {"key": "y", "label": "Y", "kind": "float"},
    {"key": "rotation_deg", "label": "Rotation", "kind": "float"},
    {"key": "tags", "label": "Tags", "kind": "tags"},
]

# Scene switcher limits
SCENE_SWITCHER_RECENT_LIMIT = 8


@dataclass(slots=True)
class EditorDirtyState:
    """Tracks whether the scene has unsaved changes."""
    is_dirty: bool = False


@dataclass(slots=True)
class EditorPlaySession:
    """Tracks editor play-from-here session state."""
    is_playing: bool = False
    return_scene_id: str | None = None
    return_camera_pos: tuple[float, float] | None = None
    return_selection: optional_arcade.arcade.Sprite | None = None
    spawn_mode: str = "camera_center"


@dataclass(slots=True)
class EditorBuildSession:
    """Tracks an editor-launched build process."""
    is_running: bool = False
    output_path: str | None = None
    stderr_log_path: str | None = None


@dataclass(slots=True)
class EditorTourSession:
    """Tracks the first-launch tour modal state."""
    is_active: bool = False
    current_step: int = 0
