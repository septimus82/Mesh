"""Project scaffolding utilities for Mesh Engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .logging_tools import get_logger
from . import json_io

_LOG = get_logger("engine.project_scaffold")


def validate_new_project_target(root: Path) -> tuple[bool, str]:
    """Check if the target directory is valid for a new project.
    
    Returns:
        (valid, error_message)
    """
    if not root.exists():
        return True, ""
        
    if not root.is_dir():
        return False, f"Target path exists and is not a directory: {root}"
        
    # Allowed existing files (e.g. .git, .gitignore, .vscode)
    # But for safety, simplest check is empty directory (ignoring common dotfiles)
    ignored = {".git", ".gitignore", ".vscode", ".idea", ".DS_Store"}
    items = [item for item in root.iterdir() if item.name not in ignored]
    if items:
        # Check if it's just empty directories possibly? 
        # For now, strict emptiness for files.
        return False, f"Target directory is not empty: {root}"
        
    return True, ""


def create_project(root: Path, name: str, template_id: str = "blank") -> None:
    """Create a new Mesh project structure at the given root."""
    from .project_templates import apply_template

    _LOG.info("Creating new project '%s' at %s (template=%s)", name, root, template_id)
    
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    
    # Create directory structure
    dirs = [
        "packs/core_regions/scenes",
        "packs/core_regions/worlds",
        "assets/images",
        "assets/sounds",
        "assets/music",
        "assets/data",
        "artifacts",
    ]
    
    for d in dirs:
        (root / d).mkdir(parents=True, exist_ok=True)
        
    # Create default config.json
    config: dict[str, Any] = {
        "version": 1,
        "project_name": name,
        "width": 1280,
        "height": 720,
        "title": f"{name}",
        "start_scene": "packs/core_regions/scenes/start.json",
        "main_menu_scene": None,
        "world_file": "packs/core_regions/worlds/main.json",
        "lighting_enabled": True
    }
    
    json_io.write_json_atomic(root / "config.json", config)
    
    # Create a simple placeholder world
    world = {
        "id": "main",
        "name": "Main World",
        "initial_scene_key": "start",
        "scenes": [
            {
                "key": "start",
                "path": "packs/core_regions/scenes/start.json",
                "map_location": {"x": 0, "y": 0}
            }
        ]
    }
    json_io.write_json_atomic(root / "packs/core_regions/worlds/main.json", world)

    # Apply template (writes start.json and others)
    apply_template(root, template_id)
    
    _LOG.info("Project created successfully.")
