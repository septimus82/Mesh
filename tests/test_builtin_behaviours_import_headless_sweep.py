from __future__ import annotations

import ast
import importlib
import importlib.abc
import sys
from pathlib import Path

import pytest

import engine.behaviours


class ArcadeBlocker(importlib.abc.MetaPathFinder):
    """Blocks any import starting with 'arcade'."""
    def find_spec(self, fullname, path, target=None):
        if fullname == "arcade" or fullname.startswith("arcade."):
             raise ModuleNotFoundError(f"Arcade is purposely blocked for headless testing: {fullname}")
        return None


_PREVIOUSLY_MISSING_BEHAVIOURS = {
    "ActionListRunner",
    "DialogueRunner",
    "FleeFromTarget",
    "Interactable",
    "ListenForEvent",
    "MessageOnZoneEnter",
    "NpcSchedule",
    "PatrolPath",
    "QuestHook",
    "Timer",
    "TriggerVolume",
    "Wander",
}


def _calls_register_behaviour(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "register_behaviour":
            return True
        if isinstance(func, ast.Attribute) and func.attr == "register_behaviour":
            return True
    return False


def _register_behaviour_modules() -> set[str]:
    behaviours_dir = Path(engine.behaviours.__file__).resolve().parent
    infrastructure = {"__init__.py", "base.py", "registry.py", "saveable.py", "utils.py"}
    modules: set[str] = set()
    for path in behaviours_dir.glob("*.py"):
        if path.name in infrastructure:
            continue
        if _calls_register_behaviour(path):
            modules.add(f"engine.behaviours.{path.stem}")
    return modules


@pytest.mark.fast
def test_builtin_modules_cover_every_register_behaviour_module() -> None:
    missing = _register_behaviour_modules() - set(engine.behaviours._BUILTIN_MODULES)
    assert missing == set()


def test_builtin_behaviours_import_headless_sweep():
    """
    Verifies that ALL builtin behaviours can be imported when 'arcade' is missing.
    This ensures that tooling (like verify-all) can inspect behaviour metadata
    without crashing due to eager runtime dependencies.
    """

    # 1. Capture strict list of modules to check
    builtin_modules = engine.behaviours._BUILTIN_MODULES
    assert len(builtin_modules) > 0, "No builtin modules defined?"

    # 2. Setup Headless Environment (Destructive Sys Patching)
    original_modules = sys.modules.copy()
    original_meta_path = sys.meta_path[:]

    # Clean out existing arcade modules
    for key in list(sys.modules.keys()):
        if key == "arcade" or key.startswith("arcade."):
            del sys.modules[key]

    # Install blocker
    sys.meta_path.insert(0, ArcadeBlocker())

    try:
        # 3. Sweep imports
        for module_name in builtin_modules:
            # Force reload/import
            if module_name in sys.modules:
                del sys.modules[module_name]

            try:
                importlib.import_module(module_name)
            except ImportError as e:
                # If the error mentions arcade or our specific message
                err_str = str(e).lower()
                if "arcade" in err_str:
                    pytest.fail(f"Behaviour module '{module_name}' failed to import headless. \nError: {e!r}")
                else:
                    # If it failed for another reason (e.g. strict dependency elsewhere), raise it
                    raise

        # 4. Verify Registry Population logic works
        # Ensure registry is clean/fresh for this check
        if "engine.behaviours.registry" in sys.modules:
             # We want to keep the registry module but reset its contents
             # or just rely on load_builtin_behaviours logic.
             # Actually, simpler to just run the load function now that modules are imported.
             pass

        # This function should be idempotent and safe
        engine.behaviours.load_builtin_behaviours(force=True)

        from engine.behaviours.registry import list_behaviours
        behaviours = list_behaviours()

        assert len(behaviours) > 0, "Registry should be populated after sweep"

        names = {b.name for b in behaviours}
        # Check for stable/common behaviours
        assert "TriggerZone" in names, "TriggerZone should be present"
        assert "Animator" in names, "Animator should be present"
        assert _PREVIOUSLY_MISSING_BEHAVIOURS <= names

        # force=True should remain safe after modules have already been imported
        # directly or indirectly.
        engine.behaviours.load_builtin_behaviours(force=True)
        names_after_force = {b.name for b in list_behaviours()}
        assert names_after_force == names

    finally:
        # Restore environment
        sys.meta_path[:] = original_meta_path
        # We don't necessarily restore sys.modules fully because that's hard,
        # but we definitely want to remove the broken/mocked modules if any.
        # In a pytest run, this test should ideally be isolated, but resetting
        # helps.

        # Ideally we restore the exact dictionary:
        sys.modules.clear()
        sys.modules.update(original_modules)
