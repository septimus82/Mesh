from __future__ import annotations

from .entry import DEFAULT_SMOKE_SCENE, DEFAULT_SMOKE_TICKS, run_runtime_scene

# Authoritative import-boundary list for runtime-only entrypoints.
# Any module matching one of these prefixes is considered editor-only.
FORBIDDEN_EDITOR_PREFIXES: tuple[str, ...] = (
    "engine.editor",
    "engine.editor_controller",
    "engine.editor_runtime",
    "engine.ui_overlays",
    "engine.command_palette_registry_actions",
)


def is_forbidden_editor_import(module_name: str) -> bool:
    name = str(module_name or "")
    for prefix in FORBIDDEN_EDITOR_PREFIXES:
        if name == prefix or name.startswith(prefix + "."):
            return True
    return False


__all__ = [
    "DEFAULT_SMOKE_SCENE",
    "DEFAULT_SMOKE_TICKS",
    "FORBIDDEN_EDITOR_PREFIXES",
    "is_forbidden_editor_import",
    "run_runtime_scene",
]
