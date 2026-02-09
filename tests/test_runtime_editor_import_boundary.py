"""
Policy test: Runtime modules must not import editor/overlay modules.

This enforces a clean architectural boundary between:
- Runtime code (ships in game builds)
- Editor code (development-only tooling)

Violations would cause editor code to be bundled in production builds,
increasing binary size and potentially exposing development-only features.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = REPO_ROOT / "engine"

# Modules that are considered "runtime" - should not import editor code
RUNTIME_MODULE_PREFIXES: Sequence[str] = (
    "engine.action_runtime",
    "engine.behaviours",
    "engine.console_runtime",
    "engine.event_runtime",
    "engine.game_runtime",
    "engine.input_runtime",
    "engine.lighting",
    "engine.pathfinding",
    "engine.quest_runtime",
    "engine.save_runtime",
    "engine.scene_runtime",
    "engine.state_runtime",
)

# Directories that are considered runtime code
RUNTIME_DIRS: FrozenSet[str] = frozenset({
    "action_runtime",
    "behaviours",
    "console_runtime",
    "event_runtime",
    "game_runtime",
    "input_runtime",
    "lighting",
    "pathfinding",
    "quest_runtime",
    "save_runtime",
    "scene_runtime",
    "state_runtime",
})

# Modules that are considered "editor" - should not be imported by runtime
EDITOR_MODULE_PATTERNS: Sequence[str] = (
    "engine.editor",
    "engine.editor_controller",
    "engine.editor_runtime",
    "engine.ui_overlays",
    "editor",
    "editor_controller",
    "editor_runtime",
    "ui_overlays",
)

# Explicit allowlist for approved cross-boundary imports
# Format: (runtime_module_path, editor_import) -> reason
# Keep this minimal and document each exception
# These are EXISTING violations at initial test creation - new violations will fail CI
ALLOWED_VIOLATIONS: dict[tuple[str, str], str] = {
    # tick.py editor sprite ghosting - conditional import for editor overlay
    ("engine/game_runtime/tick.py", "engine.editor.editor_sprite_ghosting"): "Conditional import for editor sprite ghosting overlay",
    # capture_focus_query - needs editor panel query for focus check
    ("engine/input_runtime/capture_focus_query.py", "engine.editor.editor_panels_query"): "Needs editor panel query for focus management",
    # capture_runtime - editor runtime integration
    ("engine/input_runtime/capture_runtime.py", "engine.editor_runtime.input"): "Editor runtime input integration",
    ("engine/input_runtime/capture_runtime.py", "engine.editor_runtime.hover_detection"): "Editor runtime hover detection",
    ("engine/input_runtime/capture_runtime.py", "engine.editor.editor_cursor_apply"): "Editor cursor application",
}

# Ratchet file for tracking violation count over time
RATCHET_FILE = REPO_ROOT / "artifacts" / "runtime_editor_import_ratchet.txt"


@dataclass(frozen=True)
class ImportViolation:
    file: str
    line: int
    col: int
    imported_module: str
    
    def as_key(self) -> tuple[str, str]:
        return (self.file, self.imported_module)


def _is_runtime_dir(path: Path) -> bool:
    """Check if path is in a runtime directory."""
    for part in path.parts:
        if part in RUNTIME_DIRS:
            return True
    return False


def _is_editor_import(module: str) -> bool:
    """Check if module name is an editor/overlay import."""
    if not module:
        return False
    for pattern in EDITOR_MODULE_PATTERNS:
        if module == pattern or module.startswith(pattern + "."):
            return True
    return False


def _scan_file_for_violations(path: Path, repo_root: Path) -> list[ImportViolation]:
    """Scan a single Python file for editor imports."""
    violations: list[ImportViolation] = []
    rel_path = path.relative_to(repo_root).as_posix()
    
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=rel_path)
    except (SyntaxError, UnicodeDecodeError):
        return []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_editor_import(alias.name):
                    violations.append(ImportViolation(
                        file=rel_path,
                        line=node.lineno,
                        col=node.col_offset,
                        imported_module=alias.name,
                    ))
        elif isinstance(node, ast.ImportFrom):
            if node.module and _is_editor_import(node.module):
                violations.append(ImportViolation(
                    file=rel_path,
                    line=node.lineno,
                    col=node.col_offset,
                    imported_module=node.module,
                ))
    
    return violations


def _filter_allowed(violations: list[ImportViolation]) -> list[ImportViolation]:
    """Remove explicitly allowed violations."""
    return [v for v in violations if v.as_key() not in ALLOWED_VIOLATIONS]


def _read_ratchet_count() -> int | None:
    """Read the current ratchet count from file."""
    if not RATCHET_FILE.exists():
        return None
    try:
        text = RATCHET_FILE.read_text(encoding="utf-8").strip()
        return int(text)
    except (ValueError, OSError):
        return None


def test_runtime_modules_do_not_import_editor() -> None:
    """
    Verify runtime modules don't import editor/overlay code.
    
    This test scans all Python files in runtime directories and fails if
    any import editor modules (excluding explicitly allowed exceptions).
    
    To fix violations:
    1. Move shared code to engine.shared/ or engine.models/
    2. Use dependency injection for optional editor features
    3. If truly necessary, add to ALLOWED_VIOLATIONS with documented reason
    """
    all_violations: list[ImportViolation] = []
    
    # Scan all runtime directories
    for runtime_dir in RUNTIME_DIRS:
        dir_path = ENGINE_ROOT / runtime_dir
        if not dir_path.exists():
            continue
        
        for py_file in sorted(dir_path.rglob("*.py")):
            if "__pycache__" in str(py_file):
                continue
            violations = _scan_file_for_violations(py_file, REPO_ROOT)
            all_violations.extend(violations)
    
    # Filter out allowed violations
    actual_violations = _filter_allowed(all_violations)
    
    if not actual_violations:
        return
    
    # Format error message with actionable information
    lines = [
        "Runtime modules must not import editor/overlay code.",
        "",
        "Violations found:",
    ]
    
    for v in sorted(actual_violations, key=lambda x: (x.file, x.line)):
        lines.append(f"  {v.file}:{v.line}:{v.col} imports {v.imported_module}")
    
    lines.extend([
        "",
        "To fix:",
        "  1. Move shared code to engine/shared/ or use dependency injection",
        "  2. If truly necessary, add exception to ALLOWED_VIOLATIONS in this test",
        "",
        f"Total violations: {len(actual_violations)}",
    ])
    
    raise AssertionError("\n".join(lines))


def test_runtime_editor_import_ratchet() -> None:
    """
    Ratchet test: violation count must not increase.
    
    This allows existing violations to remain while preventing new ones.
    The ratchet count is stored in artifacts/runtime_editor_import_ratchet.txt.
    
    To update the ratchet after fixing violations:
        echo NEW_COUNT > artifacts/runtime_editor_import_ratchet.txt
    """
    # Count current violations
    all_violations: list[ImportViolation] = []
    
    for runtime_dir in RUNTIME_DIRS:
        dir_path = ENGINE_ROOT / runtime_dir
        if not dir_path.exists():
            continue
        
        for py_file in sorted(dir_path.rglob("*.py")):
            if "__pycache__" in str(py_file):
                continue
            violations = _scan_file_for_violations(py_file, REPO_ROOT)
            all_violations.extend(violations)
    
    actual_violations = _filter_allowed(all_violations)
    current_count = len(actual_violations)
    
    # Read ratchet
    ratchet_count = _read_ratchet_count()
    
    if ratchet_count is None:
        # No ratchet file - this is initial run, create it
        RATCHET_FILE.parent.mkdir(parents=True, exist_ok=True)
        RATCHET_FILE.write_text(str(current_count) + "\n", encoding="utf-8")
        return
    
    if current_count > ratchet_count:
        raise AssertionError(
            f"Runtime→Editor import violations increased!\n"
            f"  Previous count: {ratchet_count}\n"
            f"  Current count:  {current_count}\n"
            f"  New violations: {current_count - ratchet_count}\n"
            f"\n"
            f"Fix the new violations or, if intentional, update the ratchet:\n"
            f"  echo {current_count} > {RATCHET_FILE.relative_to(REPO_ROOT)}"
        )
    
    if current_count < ratchet_count:
        # Count decreased - update ratchet automatically
        RATCHET_FILE.write_text(str(current_count) + "\n", encoding="utf-8")
