from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROD_ROOTS = (ROOT / "engine", ROOT / "mesh_cli")

SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9_.-]+)?$")

# Existing non-engine-version literals that are intentionally allowed.
SEMVER_LITERAL_ALLOWLIST: set[tuple[str, str]] = {
    ("engine/content_packs.py", "0.0.0"),
    ("engine/tooling/pack_commands.py", "0.1.0"),
    ("engine/tooling_runtime/pack_manifest.py", "0.0.0-dev"),
    ("engine/plugin_system.py", "0.0.0"),  # default plugin manifest version
    ("engine/public_api/version.py", "1.0.0"),  # public API semver contract constant
}

# Only these modules may define version constants directly.
VERSION_DEFINITION_ALLOWLIST = {
    "engine/version.py:ENGINE_VERSION",
    "engine/__init__.py:__version__",
}


def _iter_prod_files() -> list[Path]:
    files: list[Path] = []
    for base in PROD_ROOTS:
        files.extend(sorted(base.rglob("*.py")))
    return files


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def test_semver_string_literals_are_allowlisted() -> None:
    violations: list[str] = []
    for path in _iter_prod_files():
        rel = _rel(path)
        tree = ast.parse(_read_source(path), filename=rel)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            value = node.value.strip()
            if not SEMVER_RE.fullmatch(value):
                continue
            if rel == "engine/version.py":
                continue
            if (rel, value) in SEMVER_LITERAL_ALLOWLIST:
                continue
            violations.append(f"{rel}:{node.lineno} literal='{value}'")

    assert not violations, (
        "Version literal policy violation. Use mesh_cli.version_info.get_tool_version() for tool/engine version "
        "reporting, or add an allowlist entry with rationale for non-engine semantic literals. "
        f"Offenders: {sorted(violations)}"
    )


def _module_level_targets(node: ast.stmt) -> list[str]:
    targets: list[str] = []
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                targets.append(target.id)
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        targets.append(node.target.id)
    return targets


def test_no_new_engine_or_dunder_version_definitions() -> None:
    tracked = {"ENGINE_VERSION", "__version__"}
    violations: list[str] = []
    for path in _iter_prod_files():
        rel = _rel(path)
        tree = ast.parse(_read_source(path), filename=rel)
        for node in tree.body:
            for name in _module_level_targets(node):
                if name not in tracked:
                    continue
                token = f"{rel}:{name}"
                if token not in VERSION_DEFINITION_ALLOWLIST:
                    violations.append(f"{token} (line {getattr(node, 'lineno', '?')})")

    assert not violations, (
        "Version definition drift detected. Keep ENGINE_VERSION in engine/version.py and __version__ in "
        "engine/__init__.py only; route all version reads through mesh_cli.version_info.get_tool_version(). "
        f"Offenders: {sorted(violations)}"
    )
