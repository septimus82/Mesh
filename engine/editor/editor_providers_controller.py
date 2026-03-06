from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, cast

from engine.editor.scene_lint_model import build_scene_lint_issues


class EditorProvidersController:
    """Centralizes provider payload construction for editor overlays."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def get_project_explorer_payload(
        self,
        viewport_h: int,
        row_h: float,
        overscan: int = 5,
    ) -> dict[str, Any]:
        explorer = getattr(self._editor, "project_explorer", None)
        if explorer and hasattr(explorer, "get_provider_payload"):
            return cast(Dict[str, Any], explorer.get_provider_payload(viewport_h, row_h, overscan))
        return {}

    def get_project_explorer_context_menu_payload(self) -> dict[str, Any]:
        explorer = getattr(self._editor, "project_explorer", None)
        if explorer and hasattr(explorer, "get_context_menu_payload"):
            return cast(Dict[str, Any], explorer.get_context_menu_payload())
        return {}

    def get_problems_panel_payload(
        self,
        viewport_h: int,
        row_h: float,
        overscan: int = 5,
    ) -> dict[str, Any]:
        problems = getattr(self._editor, "problems", None)
        if problems and hasattr(problems, "refresh_structured_diagnostics"):
            problems.refresh_structured_diagnostics()
        if problems and hasattr(problems, "get_provider_payload"):
            return cast(
                Dict[str, Any],
                problems.get_provider_payload(viewport_height=viewport_h, row_height=row_h, overscan=overscan),
            )
        return {}

    def get_palette_problems(self, scene_data: Any, window: Any) -> List[Any]:
        """Get problems for the Find Everything palette."""
        problems = getattr(self._editor, "problems", None)
        if problems and problems.issues:
            return list(problems.issues)

        if not isinstance(scene_data, dict):
            return []

        repo_root = getattr(window, "repo_root", None)
        if not isinstance(repo_root, Path):
            return []

        def resolver(prefab_id: str) -> bool:
            try:
                from engine.prefabs import get_prefab_manager

                manager = get_prefab_manager()
                return bool(manager.get_prefab(prefab_id))
            except Exception:
                return False

        return build_scene_lint_issues(scene_data, repo_root, prefab_resolver=resolver)
