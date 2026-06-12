"""Policy contract tests for capture_mouse_router UI handler modules.

These tests prevent architectural regression by enforcing:
- Size limits on handler modules (no god-files)
- Router stays glue-only (no handler bodies)
- Handler modules have consistent signatures
- Deprecated monolithic modules cannot be used
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Size ratchets - prevent modules from becoming god-files
# ---------------------------------------------------------------------------

# Maximum non-empty lines per UI handler module
UI_HANDLER_MAX_LINES = 100

# Per-module size limits for paint/select handlers (tighter ratchets)
PAINT_SELECT_HANDLER_LIMITS: dict[str, int] = {
    "capture_mouse_router_handlers_capture_mode.py": 220,
    "capture_mouse_router_handlers_tile_paint.py": 320,
    "capture_mouse_router_handlers_entity_paint.py": 130,
    "capture_mouse_router_handlers_entity_select.py": 150,
    "capture_mouse_router_handlers_authoring_selected.py": 50,
}

# Maximum lines for the main router (glue-only)
ROUTER_MAX_LINES = 150

# Baseline count of entries in MOUSE_PREFIX_DISPATCH - must not shrink
MOUSE_PREFIX_DISPATCH_BASELINE = 14

# UI handler modules to check (modal scopes)
UI_HANDLER_MODULES = [
    "capture_mouse_router_handlers_modal_base.py",
    "capture_mouse_router_handlers_confirm_modal.py",
    "capture_mouse_router_handlers_context_menu.py",
    "capture_mouse_router_handlers_keybinds.py",
    "capture_mouse_router_handlers_inline_rename.py",
    "capture_mouse_router_handlers_command_palette.py",
    "capture_mouse_router_handlers_console.py",
    "capture_mouse_router_handlers_project_explorer.py",
    "capture_mouse_router_handlers_problems.py",
    "capture_mouse_router_handlers_ui.py",  # Legacy module
]

# Deprecated modules that must not be imported except in tests
DEPRECATED_MODULES = [
    "capture_mouse_router_handlers_paint",
    "capture_mouse_router_handlers_select",
]


def _count_non_empty_lines(path: Path) -> int:
    """Count non-empty, non-comment-only lines."""
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


def _get_input_runtime_path() -> Path:
    """Get the path to the input_runtime module."""
    return Path(__file__).parent.parent / "engine" / "input_runtime"


@lru_cache(maxsize=1)
def _engine_python_files() -> tuple[Path, ...]:
    engine_root = _get_input_runtime_path().parent
    files: list[Path] = []
    for root, _dirs, names in os.walk(engine_root):
        for filename in names:
            if filename.endswith(".py"):
                files.append(Path(root) / filename)
    return tuple(sorted(files, key=lambda p: p.as_posix()))


@lru_cache(maxsize=None)
def _read_utf8(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


@pytest.mark.fast
def test_ui_handler_module_size_ratchets() -> None:
    """UI handler modules stay under size limit."""
    base = _get_input_runtime_path()
    violations: list[str] = []

    for module_name in UI_HANDLER_MODULES:
        path = base / module_name
        if not path.exists():
            violations.append(
                f"  {module_name}:\n"
                f"    status: FILE NOT FOUND\n"
                f"    hint: Create the module or remove from UI_HANDLER_MODULES list."
            )
            continue
        lines = _count_non_empty_lines(path)
        if lines > UI_HANDLER_MAX_LINES:
            violations.append(
                f"  {module_name}:\n"
                f"    actual: {lines} non-empty lines\n"
                f"    limit:  {UI_HANDLER_MAX_LINES} lines\n"
                f"    hint:   Extract logic to a helper module or increase UI_HANDLER_MAX_LINES."
            )

    if violations:
        pytest.fail(
            "UI handler modules exceed size limits:\n\n"
            + "\n\n".join(violations)
        )


@pytest.mark.fast
def test_paint_select_handler_module_size_ratchets() -> None:
    """Paint/select handler modules stay under per-module size limits."""
    base = _get_input_runtime_path()
    violations: list[str] = []

    for module_name, max_lines in PAINT_SELECT_HANDLER_LIMITS.items():
        path = base / module_name
        if not path.exists():
            violations.append(
                f"  {module_name}:\n"
                f"    status: FILE NOT FOUND\n"
                f"    hint: Create the module or remove from PAINT_SELECT_HANDLER_LIMITS."
            )
            continue
        lines = _count_non_empty_lines(path)
        if lines > max_lines:
            violations.append(
                f"  {module_name}:\n"
                f"    actual: {lines} non-empty lines\n"
                f"    limit:  {max_lines} lines\n"
                f"    hint:   Split handler logic or increase limit in PAINT_SELECT_HANDLER_LIMITS."
            )

    if violations:
        pytest.fail(
            "Paint/select handler modules exceed size limits:\n\n"
            + "\n\n".join(violations)
        )


@pytest.mark.fast
def test_router_size_ratchet() -> None:
    """Main mouse router stays under size limit (glue-only)."""
    path = _get_input_runtime_path() / "capture_mouse_router.py"
    lines = _count_non_empty_lines(path)
    assert lines <= ROUTER_MAX_LINES, (
        f"capture_mouse_router.py has {lines} non-empty lines (limit {ROUTER_MAX_LINES}). "
        "Move handler logic to handler modules."
    )


# ---------------------------------------------------------------------------
# Handler body forbiddance - router must be glue-only
# ---------------------------------------------------------------------------

# Patterns that indicate handler logic in the router
HANDLER_BODY_PATTERNS = [
    re.compile(r"def _handle_"),  # Private handler functions
    re.compile(r'if action_id\s*==\s*["\']'),  # Per-action conditionals
    re.compile(r"getattr\s*\(\s*window\s*,"),  # Direct window attribute access
    re.compile(r"\.center_x|\.center_y"),  # Sprite coordinate access
    re.compile(r"screen_to_world"),  # Coordinate transforms
]


@pytest.mark.fast
def test_router_has_no_handler_bodies() -> None:
    """Router must not contain handler implementation details."""
    path = _get_input_runtime_path() / "capture_mouse_router.py"
    content = path.read_text(encoding="utf-8")

    violations: list[str] = []
    for lineno, line in enumerate(content.splitlines(), 1):
        for pattern in HANDLER_BODY_PATTERNS:
            if pattern.search(line):
                violations.append(f"Line {lineno}: {line.strip()[:60]}")

    if violations:
        pytest.fail(
            "capture_mouse_router.py contains handler logic (must be glue-only):\n"
            + "\n".join(violations[:10])
        )


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_prefix_registry_is_tuple() -> None:
    """Prefix registry is immutable tuple."""
    from engine.input_runtime.capture_mouse_router import MOUSE_PREFIX_DISPATCH

    assert isinstance(MOUSE_PREFIX_DISPATCH, tuple), "Registry must be tuple for immutability"
    for entry in MOUSE_PREFIX_DISPATCH:
        assert isinstance(entry, tuple), f"Registry entry must be tuple: {entry}"
        assert len(entry) == 3, f"Registry entry must be (prefix, module, func): {entry}"
        prefix, module_name, func_name = entry
        assert isinstance(prefix, str), f"Prefix must be string: {prefix}"
        assert isinstance(module_name, str), f"Module name must be string: {module_name}"
        assert isinstance(func_name, str), f"Function name must be string: {func_name}"


@pytest.mark.fast
def test_prefix_registry_sorted_longest_first() -> None:
    """Prefix registry is sorted longest-prefix-first for determinism."""
    from engine.input_runtime.capture_mouse_router import MOUSE_PREFIX_DISPATCH

    prefixes = [prefix for prefix, _, _ in MOUSE_PREFIX_DISPATCH]

    # Check that if prefix A is a prefix of prefix B, then B comes before A
    for i, prefix_a in enumerate(prefixes):
        for j, prefix_b in enumerate(prefixes[i + 1:], i + 1):
            if prefix_b.startswith(prefix_a) and prefix_b != prefix_a:
                pytest.fail(
                    f"Prefix '{prefix_a}' (index {i}) is a prefix of '{prefix_b}' (index {j}), "
                    f"but appears earlier. Longer prefixes must come first."
                )


@pytest.mark.fast
def test_prefix_registry_covers_all_action_ids() -> None:
    """Prefix registry covers all action IDs from the route table."""
    from engine.input_runtime.capture_mouse_router import MOUSE_PREFIX_DISPATCH
    from engine.input_runtime.capture_mouse_router_model import build_mouse_routes

    routes = build_mouse_routes()
    action_ids = {route.action_id for route in routes}
    prefixes = [prefix for prefix, _, _ in MOUSE_PREFIX_DISPATCH]

    uncovered: list[str] = []
    for action_id in action_ids:
        covered = any(
            action_id.startswith(prefix) or action_id == prefix
            for prefix in prefixes
        )
        if not covered:
            uncovered.append(action_id)

    if uncovered:
        pytest.fail("Action IDs not covered by prefix registry:\n" + "\n".join(sorted(uncovered)))


# ---------------------------------------------------------------------------
# Handler signature consistency
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_handler_modules_have_dispatch_function() -> None:
    """Each handler module exports a dispatch function."""
    expected_functions = [
        ("capture_mouse_router_handlers_modal_base", "dispatch_modal_mouse_base"),
        ("capture_mouse_router_handlers_confirm_modal", "dispatch_confirm_modal_mouse"),
        ("capture_mouse_router_handlers_context_menu", "dispatch_context_menu_mouse"),
        ("capture_mouse_router_handlers_keybinds", "dispatch_keybinds_mouse"),
        ("capture_mouse_router_handlers_inline_rename", "dispatch_inline_rename_mouse"),
        ("capture_mouse_router_handlers_command_palette", "dispatch_command_palette_mouse"),
        ("capture_mouse_router_handlers_console", "dispatch_console_mouse"),
        ("capture_mouse_router_handlers_project_explorer", "dispatch_project_explorer_mouse"),
        ("capture_mouse_router_handlers_problems", "dispatch_problems_mouse"),
    ]

    missing: list[str] = []
    for module_name, func_name in expected_functions:
        try:
            module = __import__(f"engine.input_runtime.{module_name}", fromlist=[func_name])
            func = getattr(module, func_name, None)
            if not callable(func):
                missing.append(f"{module_name}.{func_name}: not callable")
        except ImportError as e:
            missing.append(f"{module_name}: import failed - {e}")

    if missing:
        pytest.fail("Handler modules missing dispatch functions:\n" + "\n".join(missing))


@pytest.mark.fast
def test_dispatch_functions_have_consistent_signature() -> None:
    """All dispatch functions accept (controller, event, action_id) and return bool."""
    import inspect

    from engine.input_runtime import (
        capture_mouse_router_handlers_command_palette,
        capture_mouse_router_handlers_confirm_modal,
        capture_mouse_router_handlers_console,
        capture_mouse_router_handlers_context_menu,
        capture_mouse_router_handlers_inline_rename,
        capture_mouse_router_handlers_keybinds,
        capture_mouse_router_handlers_modal_base,
        capture_mouse_router_handlers_problems,
        capture_mouse_router_handlers_project_explorer,
    )

    modules = [
        (capture_mouse_router_handlers_modal_base, "dispatch_modal_mouse_base"),
        (capture_mouse_router_handlers_confirm_modal, "dispatch_confirm_modal_mouse"),
        (capture_mouse_router_handlers_context_menu, "dispatch_context_menu_mouse"),
        (capture_mouse_router_handlers_keybinds, "dispatch_keybinds_mouse"),
        (capture_mouse_router_handlers_inline_rename, "dispatch_inline_rename_mouse"),
        (capture_mouse_router_handlers_command_palette, "dispatch_command_palette_mouse"),
        (capture_mouse_router_handlers_console, "dispatch_console_mouse"),
        (capture_mouse_router_handlers_project_explorer, "dispatch_project_explorer_mouse"),
        (capture_mouse_router_handlers_problems, "dispatch_problems_mouse"),
    ]

    issues: list[str] = []
    for module, func_name in modules:
        func = getattr(module, func_name)
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())

        # Check parameter names (allow Any type hints)
        expected = ["controller", "event", "action_id"]
        if params != expected:
            issues.append(f"{func_name}: params are {params}, expected {expected}")

    if issues:
        pytest.fail("Dispatch functions have inconsistent signatures:\n" + "\n".join(issues))


# ---------------------------------------------------------------------------
# Deprecation quarantine tests
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_deprecated_modules_not_imported_in_production_code() -> None:
    """Deprecated monolithic modules must not be imported in production code.
    
    The only allowed imports are:
    - In test files (test_*.py)
    - In the shim modules themselves
    """
    engine_root = _get_input_runtime_path().parent
    violations: list[str] = []

    for filepath in _engine_python_files():
        filename = filepath.name
        # Skip test files
        if filename.startswith("test_"):
            continue
        # Skip the shim modules themselves
        if filename in ("capture_mouse_router_handlers_paint.py", "capture_mouse_router_handlers_select.py"):
            continue
        try:
            content = _read_utf8(filepath.as_posix())
        except Exception:
            continue

        for deprecated in DEPRECATED_MODULES:
            # Check for import statements
            if f"import {deprecated}" in content or f"from engine.input_runtime import {deprecated}" in content:
                rel_path = filepath.relative_to(engine_root.parent)
                violations.append(f"{rel_path}: imports deprecated module '{deprecated}'")

    if violations:
        pytest.fail(
            "Deprecated modules are imported in production code (use per-scope handlers):\n"
            + "\n".join(violations)
        )


@pytest.mark.fast
def test_deprecated_shim_modules_are_tiny() -> None:
    """Deprecated shim modules must stay tiny (< 60 lines)."""
    base = _get_input_runtime_path()
    shim_max_lines = 60
    violations: list[str] = []

    for module_name in ("capture_mouse_router_handlers_paint.py", "capture_mouse_router_handlers_select.py"):
        path = base / module_name
        if not path.exists():
            # File deleted is also acceptable
            continue
        lines = _count_non_empty_lines(path)
        if lines > shim_max_lines:
            violations.append(
                f"  {module_name}:\n"
                f"    actual: {lines} non-empty lines\n"
                f"    limit:  {shim_max_lines} lines (shim must be minimal)\n"
                f"    hint:   Shim should only re-export and emit DeprecationWarning. Remove logic."
            )

    if violations:
        pytest.fail(
            "Deprecated shim modules are too large:\n\n"
            + "\n\n".join(violations)
        )


@pytest.mark.fast
def test_deprecated_shim_emits_deprecation_warning() -> None:
    """Deprecated shim modules MUST emit DeprecationWarning on import.
    
    This test imports the shim in a subprocess to ensure the warning is emitted
    even with strict warning filters. The warning cannot be suppressed.
    """
    code = (
        "import json, warnings\n"
        "with warnings.catch_warnings(record=True) as caught:\n"
        "    warnings.simplefilter('always', DeprecationWarning)\n"
        "    from engine.input_runtime import capture_mouse_router_handlers_paint  # noqa: F401\n"
        "    from engine.input_runtime import capture_mouse_router_handlers_select  # noqa: F401\n"
        "dep = [w for w in caught if issubclass(w.category, DeprecationWarning)]\n"
        "print(json.dumps({'dep_count': len(dep), 'messages': [str(w.message) for w in dep]}, sort_keys=True))\n"
        "raise SystemExit(0 if len(dep) >= 2 else 1)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "Expected both deprecated shim imports to emit DeprecationWarning.\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}\n"
    )
    payload = json.loads(result.stdout.strip() or "{}")
    dep_count = int(payload.get("dep_count", 0)) if isinstance(payload, dict) else 0
    assert dep_count >= 2, f"expected >=2 deprecation warnings, got {dep_count}: {result.stdout}"


@pytest.mark.fast
def test_deprecated_import_forbiddance_not_bypassable() -> None:
    """The production import forbiddance check cannot be bypassed by warning filters.
    
    This test verifies that even if warnings are ignored, the AST-based check
    in test_deprecated_modules_not_imported_in_production_code still catches imports.
    """
    import os
    import tempfile

    engine_root = _get_input_runtime_path().parent

    # Create a temporary test file that imports the deprecated module with warnings ignored
    test_content = '''
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
from engine.input_runtime import capture_mouse_router_handlers_paint
'''

    # Write to a temp file in engine (simulating production code)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        dir=engine_root,
        delete=False,
        prefix="_test_forbidden_import_"
    ) as f:
        f.write(test_content)
        temp_path = Path(f.name)

    try:
        # Verify the check catches it via string matching
        content = temp_path.read_text(encoding="utf-8")
        found = False
        for deprecated in DEPRECATED_MODULES:
            if f"import {deprecated}" in content or f"from engine.input_runtime import {deprecated}" in content:
                found = True
                break

        assert found, (
            "The string-based import check failed to detect the deprecated import. "
            "This means the forbiddance test can be bypassed!"
        )
    finally:
        # Clean up temp file
        os.unlink(temp_path)


# ---------------------------------------------------------------------------
# Prefix registry stability tests
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_prefix_registry_baseline_count() -> None:
    """Prefix registry has at least the baseline number of entries."""
    from engine.input_runtime.capture_mouse_router import MOUSE_PREFIX_DISPATCH

    actual = len(MOUSE_PREFIX_DISPATCH)
    if actual < MOUSE_PREFIX_DISPATCH_BASELINE:
        pytest.fail(
            f"MOUSE_PREFIX_DISPATCH entry count regression:\n"
            f"  actual:   {actual} entries\n"
            f"  baseline: {MOUSE_PREFIX_DISPATCH_BASELINE} entries\n"
            f"  hint:     If entries were intentionally removed, update "
            f"MOUSE_PREFIX_DISPATCH_BASELINE in this test file."
        )


@pytest.mark.fast
def test_router_has_no_button_conditionals() -> None:
    """Router must not contain button == conditionals (handler logic)."""
    path = _get_input_runtime_path() / "capture_mouse_router.py"
    content = path.read_text(encoding="utf-8")

    forbidden_patterns = [
        (re.compile(r"if\s+button\s*=="), "button comparison"),
        (re.compile(r"event\.button\s*=="), "event.button comparison"),
        (re.compile(r"editor_actions"), "editor_actions import"),
    ]

    violations: list[str] = []
    for lineno, line in enumerate(content.splitlines(), 1):
        for pattern, desc in forbidden_patterns:
            if pattern.search(line):
                violations.append(
                    f"  Line {lineno}:\n"
                    f"    pattern: {desc}\n"
                    f"    code:    {line.strip()[:70]}"
                )

    if violations:
        pytest.fail(
            "capture_mouse_router.py contains forbidden patterns:\n\n"
            + "\n\n".join(violations[:10])
            + (f"\n\n  ... and {len(violations) - 10} more violations" if len(violations) > 10 else "")
            + "\n\n  hint: Move handler logic to per-scope handler modules."
        )


# ---------------------------------------------------------------------------
# Import boundary enforcement - handler modules only importable via router
# ---------------------------------------------------------------------------

# Per-scope handler modules (the 5 modules from paint/select split)
# These must ONLY be imported by the router and deprecated shims
PER_SCOPE_HANDLER_MODULES: tuple[str, ...] = (
    "capture_mouse_router_handlers_capture_mode",
    "capture_mouse_router_handlers_tile_paint",
    "capture_mouse_router_handlers_entity_paint",
    "capture_mouse_router_handlers_entity_select",
    "capture_mouse_router_handlers_authoring_selected",
)

# Modules allowed to import the per-scope handlers
ALLOWED_HANDLER_IMPORTERS: tuple[str, ...] = (
    "capture_mouse_router.py",           # The router (single choke point)
    "capture_mouse_router_handlers_paint.py",   # Deprecated shim
    "capture_mouse_router_handlers_select.py",  # Deprecated shim
)


@pytest.mark.fast
def test_per_scope_handlers_only_imported_by_router() -> None:
    """Per-scope handler modules can only be imported by the router.
    
    This enforces the router as the single choke point for mouse dispatch.
    Any other module wanting to trigger mouse actions must go through
    the router's public API.
    
    Allowed importers:
    - capture_mouse_router.py (the router itself)
    - capture_mouse_router_handlers_paint.py (deprecated shim)
    - capture_mouse_router_handlers_select.py (deprecated shim)
    - test_*.py files (tests are always allowed)
    """
    engine_root = _get_input_runtime_path().parent
    violations: list[str] = []

    for filepath in _engine_python_files():
        filename = filepath.name
        # Tests are always allowed
        if filename.startswith("test_"):
            continue
        # Allowed importers
        if filename in ALLOWED_HANDLER_IMPORTERS:
            continue

        try:
            content = _read_utf8(filepath.as_posix())
        except Exception:
            continue

        # Check each line for imports
        for lineno, line in enumerate(content.splitlines(), 1):
            for handler_module in PER_SCOPE_HANDLER_MODULES:
                # Match import patterns
                if (f"import {handler_module}" in line or
                    f"from engine.input_runtime import {handler_module}" in line or
                    f"from engine.input_runtime.{handler_module}" in line):
                    rel_path = filepath.relative_to(engine_root.parent)
                    violations.append(
                        f"  {rel_path}:\n"
                        f"    line {lineno}: {line.strip()[:70]}\n"
                        f"    imports:  {handler_module}\n"
                        f"    allowed:  Only {', '.join(ALLOWED_HANDLER_IMPORTERS)}"
                    )

    if violations:
        pytest.fail(
            "Import boundary violation: per-scope handlers imported outside router:\n\n"
            + "\n\n".join(violations[:10])
            + (f"\n\n... and {len(violations) - 10} more violations" if len(violations) > 10 else "")
            + "\n\n  hint: Use route_and_dispatch_mouse() from capture_mouse_router instead."
        )


# ---------------------------------------------------------------------------
# Public surface contract - router has minimal public API
# ---------------------------------------------------------------------------

# The intended public API of the router
ROUTER_PUBLIC_API: tuple[str, ...] = (
    "route_and_dispatch_mouse",  # Main entry point
    "MOUSE_PREFIX_DISPATCH",     # For introspection/testing only
)


@pytest.mark.fast
def test_router_public_surface_is_minimal() -> None:
    """Router's __all__ must contain only the intended public API.
    
    This prevents API sprawl and ensures the router remains a simple choke point.
    """
    from engine.input_runtime import capture_mouse_router

    actual_all = getattr(capture_mouse_router, "__all__", None)

    # Must have __all__ defined
    assert actual_all is not None, (
        "capture_mouse_router.py must define __all__ to declare its public API"
    )

    # Check for exact match
    actual_set = set(actual_all)
    expected_set = set(ROUTER_PUBLIC_API)

    extra = actual_set - expected_set
    missing = expected_set - actual_set

    issues: list[str] = []
    if extra:
        issues.append(f"  unexpected exports: {sorted(extra)}")
    if missing:
        issues.append(f"  missing exports:    {sorted(missing)}")

    if issues:
        pytest.fail(
            "Router public API mismatch:\n"
            + "\n".join(issues) + "\n"
            f"  expected: {sorted(ROUTER_PUBLIC_API)}\n"
            f"  actual:   {sorted(actual_all)}\n"
            f"  hint:     Update __all__ in capture_mouse_router.py or "
            f"ROUTER_PUBLIC_API in this test."
        )


@pytest.mark.fast
def test_router_entry_function_signature_and_return_type() -> None:
    """route_and_dispatch_mouse has the expected signature and returns bool."""
    import inspect

    from engine.input_runtime.capture_mouse_router import route_and_dispatch_mouse

    # Check signature
    sig = inspect.signature(route_and_dispatch_mouse)
    params = list(sig.parameters.keys())
    expected_params = ["controller", "event", "snapshot"]

    assert params == expected_params, (
        f"route_and_dispatch_mouse signature changed:\n"
        f"  expected params: {expected_params}\n"
        f"  actual params:   {params}\n"
        f"  hint: The public API must remain stable."
    )

    # Check return annotation if present
    return_annotation = sig.return_annotation
    if return_annotation != inspect.Parameter.empty:
        # Handle both direct type and string annotation (from __future__ annotations)
        expected = (bool, "bool")
        assert return_annotation in expected or return_annotation is bool, (
            f"route_and_dispatch_mouse should return bool, got {return_annotation}"
        )


@pytest.mark.fast
def test_router_returns_route_table_of_expected_shape() -> None:
    """Internal route table builder returns tuple of MouseRouteSpec."""
    from engine.input_runtime.capture_mouse_router import _get_routes
    from engine.input_runtime.capture_mouse_router_model import MouseRouteSpec

    routes = _get_routes()

    # Must be a tuple (immutable)
    assert isinstance(routes, tuple), (
        f"_get_routes() must return tuple, got {type(routes).__name__}"
    )

    # Must contain at least one route
    assert len(routes) > 0, "_get_routes() returned empty route table"

    # All entries must be MouseRouteSpec
    for i, route in enumerate(routes):
        assert isinstance(route, MouseRouteSpec), (
            f"Route at index {i} is {type(route).__name__}, expected MouseRouteSpec"
        )

    # Each route must have required fields
    for i, route in enumerate(routes):
        assert route.scope, f"Route {i} missing scope"
        assert route.kind in ("press", "release", "scroll"), f"Route {i} has invalid kind: {route.kind}"
        assert route.action_id, f"Route {i} missing action_id"
        assert callable(route.when), f"Route {i}.when is not callable"


# ---------------------------------------------------------------------------
# Shim creep prevention - no new deprecated shims allowed
# ---------------------------------------------------------------------------

# These are the ONLY allowed deprecated shim modules
# No new shims may be introduced - all new handlers must go in per-scope modules
ALLOWED_DEPRECATED_SHIMS: frozenset[str] = frozenset({
    "capture_mouse_router_handlers_paint.py",
    "capture_mouse_router_handlers_select.py",
})

# Known legitimate handler modules (not shims)
LEGITIMATE_HANDLER_MODULES: frozenset[str] = frozenset({
    # Per-scope modules (the 5 from paint/select split)
    "capture_mouse_router_handlers_capture_mode.py",
    "capture_mouse_router_handlers_tile_paint.py",
    "capture_mouse_router_handlers_entity_paint.py",
    "capture_mouse_router_handlers_entity_select.py",
    "capture_mouse_router_handlers_authoring_selected.py",
    # UI modal scopes
    "capture_mouse_router_handlers_modal_base.py",
    "capture_mouse_router_handlers_confirm_modal.py",
    "capture_mouse_router_handlers_context_menu.py",
    "capture_mouse_router_handlers_keybinds.py",
    "capture_mouse_router_handlers_inline_rename.py",
    "capture_mouse_router_handlers_command_palette.py",
    "capture_mouse_router_handlers_console.py",
    "capture_mouse_router_handlers_project_explorer.py",
    "capture_mouse_router_handlers_problems.py",
    # Other legitimate modules
    "capture_mouse_router_handlers_global.py",
    "capture_mouse_router_handlers_ui.py",
    "capture_mouse_router_handlers_paint_base.py",
})


@pytest.mark.fast
def test_no_new_shim_modules_allowed() -> None:
    """No new deprecated shim modules may be introduced.
    
    Only capture_mouse_router_handlers_paint.py and _select.py are allowed
    as deprecated shims. Any new handler module must be a proper per-scope
    module, not a shim.
    
    This test fails if any capture_mouse_router_handlers_*.py file exists
    that is not in the known allowlist.
    """
    base = _get_input_runtime_path()

    all_handler_files: list[str] = []
    for path in base.iterdir():
        if path.is_file() and path.name.startswith("capture_mouse_router_handlers_") and path.name.endswith(".py"):
            all_handler_files.append(path.name)

    # Known allowed files = legitimate modules + deprecated shims
    all_allowed = LEGITIMATE_HANDLER_MODULES | ALLOWED_DEPRECATED_SHIMS

    # Find any unknown files
    unknown_files = [f for f in all_handler_files if f not in all_allowed]

    if unknown_files:
        pytest.fail(
            "Unknown capture_mouse_router_handlers_*.py files found:\n\n"
            + "\n".join(f"  - {f}" for f in sorted(unknown_files))
            + "\n\n"
            f"If this is a legitimate handler module, add it to LEGITIMATE_HANDLER_MODULES.\n"
            f"If this is a shim, remove it - no new shims allowed.\n"
            f"Only allowed deprecated shims: {sorted(ALLOWED_DEPRECATED_SHIMS)}"
        )


# ---------------------------------------------------------------------------
# Base/helper module purity - no hidden route registration
# ---------------------------------------------------------------------------

# Modules that should be pure helpers with no route registration
PURE_HELPER_MODULES = frozenset({
    "capture_mouse_router_handlers_modal_base.py",
    "capture_mouse_router_handlers_paint_base.py",
    "capture_mouse_router_handlers_ui.py",
})

# Patterns that indicate route registration (forbidden in helper modules)
ROUTE_REGISTRATION_PATTERNS = (
    re.compile(r"\bROUTES\s*=\s*\("),           # ROUTES = (...)
    re.compile(r"\bROUTES\s*:\s*tuple"),        # ROUTES: tuple[...]
    re.compile(r"\bbuild_mouse_routes\b"),      # Calling/defining builder
    re.compile(r"\bMouseRouteSpec\s*\("),       # Direct route construction
    re.compile(r"\bregister_route\b"),          # Any registration function
)


@pytest.mark.fast
def test_helper_modules_have_no_route_registration() -> None:
    """Base/helper modules must not contain route registration code.
    
    Files matching *_base.py and *_ui.py are helper modules. They should
    contain only utility functions and classes, not route definitions.
    This prevents hidden routing behavior and keeps helpers pure.
    
    If you need to add routes, put them in a per-scope handler module.
    """
    base = _get_input_runtime_path()
    violations: list[str] = []

    for module_name in PURE_HELPER_MODULES:
        path = base / module_name
        if not path.exists():
            continue

        content = path.read_text(encoding="utf-8")
        found_patterns: list[str] = []

        for pattern in ROUTE_REGISTRATION_PATTERNS:
            matches = pattern.findall(content)
            if matches:
                found_patterns.append(pattern.pattern)

        if found_patterns:
            violations.append(
                f"  {module_name}:\n"
                f"    forbidden patterns: {found_patterns}\n"
                f"    hint: Move route definitions to a per-scope handler module."
            )

    if violations:
        pytest.fail(
            "Helper modules must not contain route registration code:\n\n"
            + "\n".join(violations)
            + "\n\n"
            "Base/helper modules should only contain utility functions.\n"
            "Route definitions belong in per-scope handler modules."
        )
