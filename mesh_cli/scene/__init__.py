"""Scene command group implementation.

This package provides backward-compatible access to many private handler/helper
functions from the old monolithic `mesh_cli.py` by resolving names lazily from
submodules.
"""

from __future__ import annotations

from .entrypoints import handle, register

__all__ = ["handle", "register"]


def __getattr__(name: str):
    import importlib

    for module_suffix in (
        "backgrounds",
        "common",
        "entities",
        "macro",
        "ops",
        "prefab_overrides",
        "stamp",
        "tilemap",
    ):
        mod = importlib.import_module(f"{__name__}.{module_suffix}")
        if hasattr(mod, name):
            return getattr(mod, name)
    raise AttributeError(name)
