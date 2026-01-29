"""Editor workspace controller logic.

Handles:
- Workspace save/load
- Editor settings
- Recent projects/files
"""

from __future__ import annotations

import collections
import json
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from pathlib import Path

from engine.workspace_settings import load_workspace, save_workspace, WorkspaceSettings
from engine.logging_tools import get_logger

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController

logger = get_logger(__name__)

# Constants extracted from EditorController or inferred
SCENE_SWITCHER_RECENT_LIMIT = 10

class EditorWorkspaceController:
    """Manages workspace state, settings, and file operations."""

    def __init__(self, controller: EditorModeController) -> None:
        self.controller = controller
        
        # Workspace state
        self.workspace_data: WorkspaceSettings = WorkspaceSettings()
        self.workspace_file: str = "workspace.json"
        
        # Recent state
        self.recent_projects: List[str] = []
        self.recent_scenes: List[Any] = []
        
    def load_workspace_settings(self) -> None:
        """Load workspace settings from disk."""
        try:
            repo_root = getattr(self.controller.window, "repo_root", None)
            if repo_root:
                file_path = repo_root / self.workspace_file
                if file_path.exists():
                    self.workspace_data = load_workspace(file_path)
                    logger.info("Loaded workspace settings from %s", file_path)
            
            # Load recents from workspace data if present
            # workspace_data is a dataclass, use attribute access
            recents = getattr(self.workspace_data, "recent_projects", None)
            if isinstance(recents, list):
                self.recent_projects = [str(r) for r in recents if isinstance(r, str)]
            
            # Load scene recents
            scene_recents = getattr(self.workspace_data, "recent_scenes", None)
            if isinstance(scene_recents, list):
                self.recent_scenes = [str(r) for r in scene_recents if isinstance(r, str)]
                
        except Exception as e:
            logger.error("Failed to load workspace settings: %s", e)
            self.workspace_data = WorkspaceSettings()

    def save_workspace_settings(self) -> None:
        """Save workspace settings to disk."""
        try:
            repo_root = getattr(self.controller.window, "repo_root", None)
            if not repo_root:
                return
                
            # Update data with current state
            setattr(self.workspace_data, "recent_projects", self.recent_projects)
            setattr(self.workspace_data, "recent_scenes", self.recent_scenes)
            
            file_path = repo_root / self.workspace_file
            save_workspace(file_path, self.workspace_data)
            logger.info("Saved workspace settings to %s", file_path)
        except Exception as e:
            logger.error("Failed to save workspace settings: %s", e)

    def add_recent_project(self, path: str) -> None:
        """Add a project path to recent projects list."""
        if not path:
            return
            
        # Normalize
        path = str(path).replace("\\", "/")
        
        # Remove if exists (to move to top)
        if path in self.recent_projects:
            self.recent_projects.remove(path)
            
        self.recent_projects.insert(0, path)
        
        # Limit
        if len(self.recent_projects) > 10:  # arbitrary limit, matching typical
            self.recent_projects = self.recent_projects[:10]
            
        self.save_workspace_settings()

    def add_recent_scene(self, path: str) -> None:
        """Add a scene path to recent scenes list."""
        if not path:
            return
            
        # Normalize
        path = str(path).replace("\\", "/")
        
        # Remove if exists (to move to top)
        if path in self.recent_scenes:
            self.recent_scenes.remove(path)
            
        self.recent_scenes.insert(0, path)
        
        # Limit
        if len(self.recent_scenes) > SCENE_SWITCHER_RECENT_LIMIT:
            self.recent_scenes = self.recent_scenes[:SCENE_SWITCHER_RECENT_LIMIT]
            
        self.save_workspace_settings()
        """Add a scene path to recent scenes list."""
        if not path:
            return

        # Simple structure for now, matching typical usage
        entry = {
            "path": str(path).replace("\\", "/"),
            "timestamp": time.time()
        }
        
        # Remove existing by path matching
        self.recent_scenes = [
            s for s in self.recent_scenes 
            if s.get("path") != entry["path"]
        ]
        
        self.recent_scenes.insert(0, entry)
        if len(self.recent_scenes) > SCENE_SWITCHER_RECENT_LIMIT:
            self.recent_scenes = self.recent_scenes[:SCENE_SWITCHER_RECENT_LIMIT]
