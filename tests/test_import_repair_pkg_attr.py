from __future__ import annotations

import sys
import types


def test_repair_package_submodule_attr_fixes_stale_package_attr() -> None:
    # Import canonical module object A.
    import engine
    import engine.editor_controller as canonical

    from engine.import_tools import repair_package_submodule_attr

    a = canonical

    # Simulate stale package attribute / sys.modules mismatch:
    # - sys.modules points to a new dummy module object B
    # - engine.editor_controller attribute still points at A (stale)
    b = types.ModuleType("engine.editor_controller")

    old_sys = sys.modules.get("engine.editor_controller")
    old_attr = getattr(engine, "editor_controller", None)

    try:
        sys.modules["engine.editor_controller"] = b
        engine.editor_controller = a

        repair_package_submodule_attr("engine", "editor_controller")

        assert engine.editor_controller is sys.modules["engine.editor_controller"]
        assert engine.editor_controller is b
    finally:
        # Restore to canonical A to avoid leaking state to later tests.
        if old_sys is not None:
            sys.modules["engine.editor_controller"] = old_sys
        else:
            sys.modules.pop("engine.editor_controller", None)

        if old_attr is not None:
            setattr(engine, "editor_controller", old_attr)
        else:
            try:
                delattr(engine, "editor_controller")
            except Exception:
                pass
