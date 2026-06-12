from __future__ import annotations

from typing import Any

from engine.i18n import tr


def scan_scene_problems(self):
    """Scan current scene JSON for issues."""
    from pathlib import Path  # noqa: PLC0415

    scene = getattr(getattr(self.window, "scene_controller", None), "_loaded_scene_data", None)

    repo_root = self._get_repo_root()
    if not isinstance(repo_root, Path):
        repo_root = Path(repo_root)

    resolver = getattr(self, "_prefab_resolver", None)
    if not callable(resolver):
        def resolver(prefab_id: str) -> bool:
            try:
                from engine.prefabs import get_prefab_manager  # noqa: PLC0415
                manager = get_prefab_manager()
                return bool(manager.get_prefab(prefab_id))
            except Exception:  # noqa: BLE001  # REASON: prefab resolver failures should degrade to a missing prefab result without breaking diagnostics scans
                return False

    issues = self.problems.scan_scene(scene, repo_root, resolver)
    message = tr("UI_PROBLEMS_SCANNED")
    feedback = getattr(self, "feedback", None)
    if feedback is not None:
        feedback.info(message, ttl=2.5)
    else:
        hud = getattr(self.window, "player_hud", None)
        toaster = getattr(hud, "enqueue_" "toast", None) if hud is not None else None
        if callable(toaster):
            toaster(message, seconds=2.5)
    return len(issues)


def get_filtered_problems(self):
    return self.problems.get_filtered_issues()


def _clamp_problems_selection(self):
    # Managed by content controller
    pass


def apply_selected_problem_fix(self):
    return self._apply_selected_problem_fix(advance=False)


def apply_fix_all_safe(self):
    return self._apply_all_safe_problem_fixes()


def _apply_selected_problem_fix(self, *, advance: bool):
    return self.problems.apply_selected_fix(self, advance=advance)


def _apply_all_safe_problem_fixes(self):
    return self.problems.apply_all_safe_fixes(self)


def _apply_scene_fix_update(self, new_scene: dict[str, Any]):
    self.problems._apply_scene_fix_update(self, new_scene)


def _refresh_after_scene_fix(self):
    self.problems._refresh_after_scene_fix(self)


def _problems_handle_mouse_click(self, x: float, y: float, button: int):
    return self.problems.handle_mouse_click(self, x, y, button)

def bind_diagnostics_bridge_methods(cls: Any) -> None:
    cls.scan_scene_problems = scan_scene_problems
    cls.get_filtered_problems = get_filtered_problems
    cls._clamp_problems_selection = _clamp_problems_selection
    cls.apply_selected_problem_fix = apply_selected_problem_fix
    cls.apply_fix_all_safe = apply_fix_all_safe
    cls._apply_selected_problem_fix = _apply_selected_problem_fix
    cls._apply_all_safe_problem_fixes = _apply_all_safe_problem_fixes
    cls._apply_scene_fix_update = _apply_scene_fix_update
    cls._refresh_after_scene_fix = _refresh_after_scene_fix
    cls._problems_handle_mouse_click = _problems_handle_mouse_click
