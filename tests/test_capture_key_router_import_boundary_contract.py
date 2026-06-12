"""Import boundary policy tests for keyboard router handlers.

These tests enforce that:
1. Per-scope key handler modules are only imported by the router
2. The router is the single choke point for key dispatch
3. The router has a minimal, stable public API

This mirrors the structure of mouse router boundary tests.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest


def _get_input_runtime_path() -> Path:
    """Get the path to engine/input_runtime/."""
    return Path("engine/input_runtime")


def _iter_python_files(root: Path) -> Iterator[Path]:
    """Iterate over all .py files in a directory tree."""
    for filepath in root.rglob("*.py"):
        yield filepath


# ---------------------------------------------------------------------------
# Per-scope handler modules (must only be imported by router)
# ---------------------------------------------------------------------------

PER_SCOPE_KEY_HANDLER_MODULES: tuple[str, ...] = (
    "capture_key_router_handlers_ui",
    "capture_key_router_handlers_global",
    "capture_key_router_handlers_tile_paint",
    "capture_key_router_handlers_entity_paint",
    "capture_key_router_handlers_entity_select",
    "capture_key_router_handlers_editor",
    "capture_key_router_handlers_authoring",
    "capture_key_router_handlers_palette",
)

# Modules allowed to import the per-scope handlers
ALLOWED_KEY_HANDLER_IMPORTERS: tuple[str, ...] = (
    "capture_key_router.py",  # The router (single choke point)
)


@pytest.mark.fast
def test_per_scope_key_handlers_only_imported_by_router() -> None:
    """Per-scope key handler modules can only be imported by the router.
    
    This enforces the router as the single choke point for key dispatch.
    Any other module wanting to trigger key actions must go through
    the router's public API.
    
    Allowed importers:
    - capture_key_router.py (the router itself)
    - test_*.py files (tests are always allowed)
    """
    engine_root = _get_input_runtime_path().parent
    violations: list[str] = []

    for filepath in _iter_python_files(engine_root):
        filename = filepath.name

        # Tests are always allowed
        if filename.startswith("test_"):
            continue
        # Allowed importers
        if filename in ALLOWED_KEY_HANDLER_IMPORTERS:
            continue

        try:
            content = filepath.read_text(encoding="utf-8")
        except Exception:
            continue

        # Check each line for imports
        for lineno, line in enumerate(content.splitlines(), 1):
            for handler_module in PER_SCOPE_KEY_HANDLER_MODULES:
                # Match import patterns
                if (f"import {handler_module}" in line or
                    f"from engine.input_runtime import {handler_module}" in line or
                    f"from engine.input_runtime.{handler_module}" in line):
                    try:
                        rel_path = filepath.relative_to(engine_root.parent)
                    except ValueError:
                        rel_path = filepath
                    violations.append(
                        f"  {rel_path}:\n"
                        f"    line {lineno}: {line.strip()[:70]}\n"
                        f"    imports:  {handler_module}\n"
                        f"    allowed:  Only {', '.join(ALLOWED_KEY_HANDLER_IMPORTERS)}"
                    )

    if violations:
        pytest.fail(
            "Import boundary violation: per-scope key handlers imported outside router:\n\n"
            + "\n\n".join(violations[:10])
            + (f"\n\n... and {len(violations) - 10} more violations" if len(violations) > 10 else "")
            + "\n\n  hint: Use route_and_dispatch() from capture_key_router instead."
        )


# ---------------------------------------------------------------------------
# Router public API contract
# ---------------------------------------------------------------------------

ROUTER_PUBLIC_API: tuple[str, ...] = (
    "route_and_dispatch",  # Main entry point
)


@pytest.mark.fast
def test_key_router_has_route_and_dispatch() -> None:
    """Key router must expose the main dispatch function."""
    from engine.input_runtime import capture_key_router

    assert hasattr(capture_key_router, "route_and_dispatch"), (
        "capture_key_router.py must have route_and_dispatch() function"
    )
    assert callable(capture_key_router.route_and_dispatch), (
        "route_and_dispatch must be callable"
    )


@pytest.mark.fast
def test_key_router_uses_model_for_routing() -> None:
    """Key router must use the model for route resolution."""
    source = Path("engine/input_runtime/capture_key_router.py").read_text(encoding="utf-8")

    # Must import from capture_key_router_model
    assert "capture_key_router_model" in source, (
        "Key router must import from capture_key_router_model"
    )

    # Must use resolve_route or build_route_table
    assert "resolve_route" in source or "build_route_table" in source, (
        "Key router must use resolve_route or build_route_table from model"
    )


# ---------------------------------------------------------------------------
# Handler module structure tests
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_handler_modules_have_dispatch_function() -> None:
    """Each handler module should have a dispatch_* or _handle_* function pattern."""
    input_runtime = _get_input_runtime_path()

    missing_dispatch: list[str] = []

    for handler_module in PER_SCOPE_KEY_HANDLER_MODULES:
        filepath = input_runtime / f"{handler_module}.py"
        if not filepath.exists():
            continue

        source = filepath.read_text(encoding="utf-8")

        # Check for dispatch pattern
        has_dispatch = "def dispatch_" in source or "def _handle_" in source
        if not has_dispatch:
            missing_dispatch.append(handler_module)

    if missing_dispatch:
        pytest.fail(
            f"Handler modules missing dispatch functions: {missing_dispatch}\n"
            f"Each handler should have dispatch_* or _handle_* functions."
        )


@pytest.mark.fast
def test_handler_modules_no_direct_window_mutation() -> None:
    """Handler modules should not directly mutate window state outside actions.
    
    This is a soft check that documents existing patterns.
    New code should avoid these patterns - use actions instead.
    """
    input_runtime = _get_input_runtime_path()

    # Known existing patterns - these are grandfathered in
    # New code should not add more of these
    KNOWN_MUTATIONS: dict[str, list[str]] = {
        "capture_key_router_handlers_ui": ["window.command_palette_enabled = "],
        "capture_key_router_handlers_global": ["window.show_debug = "],
    }

    suspicious_patterns = [
        "window.show_debug = ",  # Direct debug toggle
        "window.command_palette_enabled = ",  # Direct palette toggle
    ]

    new_violations: list[str] = []

    for handler_module in PER_SCOPE_KEY_HANDLER_MODULES:
        filepath = input_runtime / f"{handler_module}.py"
        if not filepath.exists():
            continue

        source = filepath.read_text(encoding="utf-8")
        known_for_module = KNOWN_MUTATIONS.get(handler_module, [])

        for pattern in suspicious_patterns:
            if pattern in source and pattern not in known_for_module:
                new_violations.append(f"{handler_module}: contains '{pattern}'")

    # Fail only on NEW violations
    if new_violations:
        pytest.fail(
            "New direct state mutation patterns found:\n"
            + "\n".join(new_violations)
            + "\n\nHint: Use actions instead of direct state mutation."
        )


# ---------------------------------------------------------------------------
# Size ratchets for handler modules
# ---------------------------------------------------------------------------

HANDLER_SIZE_LIMITS: dict[str, int] = {
    "capture_key_router_handlers_ui": 800,
    "capture_key_router_handlers_global": 600,
    "capture_key_router_handlers_tile_paint": 400,
    "capture_key_router_handlers_entity_paint": 400,
    "capture_key_router_handlers_entity_select": 400,
    "capture_key_router_handlers_editor": 400,
    "capture_key_router_handlers_authoring": 400,
    "capture_key_router_handlers_palette": 400,
}


@pytest.mark.fast
def test_handler_module_size_ratchets() -> None:
    """Handler modules must not exceed size limits.
    
    This prevents individual handlers from becoming god modules.
    If you need to exceed a limit, split into smaller modules.
    """
    input_runtime = _get_input_runtime_path()
    oversized: list[str] = []

    for handler_module, max_lines in HANDLER_SIZE_LIMITS.items():
        filepath = input_runtime / f"{handler_module}.py"
        if not filepath.exists():
            continue

        lines = [
            line for line in filepath.read_text(encoding="utf-8").splitlines()
            if line.strip()  # Non-empty lines
        ]

        if len(lines) > max_lines:
            oversized.append(
                f"  {handler_module}.py: {len(lines)} lines > {max_lines} limit"
            )

    if oversized:
        pytest.fail(
            "Handler modules exceed size limits:\n" + "\n".join(oversized)
            + "\n\nHint: Split large handlers into smaller scope-specific modules."
        )


# ---------------------------------------------------------------------------
# Model/Router separation test
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_model_has_no_handler_imports() -> None:
    """The key router model must not import handler modules.
    
    Model is pure data/logic. Handlers are side-effect modules.
    This separation enables testing the model without arcade.
    """
    model_path = Path("engine/input_runtime/capture_key_router_model.py")
    source = model_path.read_text(encoding="utf-8")

    for handler_module in PER_SCOPE_KEY_HANDLER_MODULES:
        assert handler_module not in source, (
            f"Model imports handler module {handler_module}. "
            f"Model must be pure - no handler imports."
        )
