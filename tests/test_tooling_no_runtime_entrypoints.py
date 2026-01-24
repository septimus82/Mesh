from __future__ import annotations

import importlib
import importlib.abc
import sys
from types import ModuleType


class _BlockRuntimeEntry(importlib.abc.MetaPathFinder):
    def __init__(self, blocked: set[str]) -> None:
        self._blocked = blocked
        self.hit: list[str] = []

    def find_spec(self, fullname, path=None, target=None):
        if fullname in self._blocked:
            self.hit.append(fullname)
            raise ModuleNotFoundError(f"Blocked runtime import: {fullname}")
        return None


def test_tooling_does_not_import_runtime_entrypoints() -> None:
    blocked = {"engine.game", "engine.editor_controller"}
    blocker = _BlockRuntimeEntry(blocked)
    sys.meta_path.insert(0, blocker)
    try:
        importlib.import_module("engine.tooling.validate_all")
        importlib.import_module("mesh_cli.verify")
        importlib.import_module("engine.tooling.perf_command")
    finally:
        sys.meta_path.remove(blocker)

    assert not blocker.hit, f"Blocked runtime imports attempted: {blocker.hit}"
