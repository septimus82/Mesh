from __future__ import annotations

from .main import create_parser, main


def __getattr__(name: str):
    """Lazy attribute access for backward compatibility with the old single-file CLI.

    Many tests and tooling helpers import private handler functions from `mesh_cli`.
    We keep those names working by resolving them from `mesh_cli.*` modules on demand.
    """
    import importlib

    # If a request matches a top-level CLI module name, prefer importing that module.
    # This avoids collisions with subpackages like `mesh_cli.scene` exporting a `macro` attribute.
    if name in {
        "legacy",
        "legacy_impl",
        "reports",
        "scene",
        "verify",
        "room",
        "macro",
        "stamps",
        "world",
        "pipeline",
        "plan",
        "assets",
        "authoring",
        "prefabs",
        "qa",
        "misc",
        "ai",
        "build",
        "debug",
        "release",
    }:
        try:
            return importlib.import_module(f"{__name__}.{name}")
        except ModuleNotFoundError:
            pass

    for module_suffix in (
        "legacy_impl",
        "reports",
        "scene",
        "verify",
        "room",
    ):
        mod = importlib.import_module(f"{__name__}.{module_suffix}")
        if hasattr(mod, name):
            return getattr(mod, name)
    raise AttributeError(name)


__all__ = ["create_parser", "main"]
