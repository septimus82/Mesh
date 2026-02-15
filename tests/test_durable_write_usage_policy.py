from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROD_ROOTS = (ROOT / "engine", ROOT / "mesh_cli", ROOT / "tooling")

ALLOWLIST = {
    "engine/save_runtime/io.py",
    "mesh_cli/content.py",
    "mesh_cli/release.py",
    "mesh_cli/verify.py",
    "mesh_cli/verify_steps/pipeline.py",
}


def _iter_production_files() -> list[Path]:
    files: list[Path] = []
    for base in PROD_ROOTS:
        files.extend(sorted(base.rglob("*.py")))
    return files


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _is_durable_true(value: ast.AST) -> bool:
    return isinstance(value, ast.Constant) and value.value is True


def test_durable_true_usage_is_allowlisted() -> None:
    violations: list[str] = []
    for path in _iter_production_files():
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        tree = ast.parse(_read_source(path), filename=rel)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg != "durable":
                    continue
                if _is_durable_true(kw.value) and rel not in ALLOWLIST:
                    violations.append(f"{rel}:{node.lineno}")
    assert not violations, (
        "durable=True is restricted to critical write paths. "
        "If needed, add file to allowlist with rationale. "
        f"Unexpected durable=True call sites: {sorted(violations)}"
    )
