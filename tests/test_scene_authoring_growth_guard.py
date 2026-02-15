from __future__ import annotations

import ast
from pathlib import Path


def _is_scene_controller_import(node: ast.stmt) -> bool:
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name == "engine.scene_controller" or alias.name.endswith(".scene_controller"):
                return True
        return False
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if module == "engine.scene_controller" or module.endswith(".scene_controller"):
            return True
        return False
    return False


def _collect_illegal_scene_controller_imports(module: ast.AST) -> list[str]:
    illegal: list[str] = []

    def visit(statements: list[ast.stmt], *, in_type_checking: bool) -> None:
        for stmt in statements:
            if _is_scene_controller_import(stmt) and not in_type_checking:
                lineno = getattr(stmt, "lineno", 0)
                illegal.append(f"line {lineno}: scene_controller import outside TYPE_CHECKING")

            if isinstance(stmt, ast.If):
                is_type_checking_guard = False
                test = stmt.test
                if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
                    is_type_checking_guard = True
                visit(stmt.body, in_type_checking=in_type_checking or is_type_checking_guard)
                visit(stmt.orelse, in_type_checking=in_type_checking)

    if isinstance(module, ast.Module):
        visit(module.body, in_type_checking=False)

    return sorted(illegal)


def test_scene_authoring_does_not_regrow() -> None:
    """
    Guard against `engine/scene_runtime/authoring/__init__.py` regrowing.

    This is intentionally text-based (no imports) to avoid side-effects and to keep it fast.
    """

    package_root = (Path(__file__).resolve().parents[1] / "engine" / "scene_runtime" / "authoring").resolve()
    authoring_path = (package_root / "__init__.py").resolve()
    assert package_root.exists(), f"missing authoring package: {package_root}"
    assert authoring_path.exists(), f"missing authoring facade: {authoring_path}"

    text = authoring_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    nonempty = [line for line in lines if line.strip()]

    # Baseline captured when the facade split landed.
    BASELINE_NONEMPTY_LINES = 103

    # Allow small incidental growth, but fail on large additions in a single PR.
    MAX_NONEMPTY_GROWTH = 20

    # Hard budget slightly above the current baseline.
    NONEMPTY_BUDGET = 140

    assert len(nonempty) <= NONEMPTY_BUDGET, (
        f"{authoring_path} grew too large: nonempty_lines={len(nonempty)} > budget={NONEMPTY_BUDGET}. "
        "Keep authoring/__init__.py as a thin facade and move logic into authoring/*_ops modules."
    )

    assert len(nonempty) <= BASELINE_NONEMPTY_LINES + MAX_NONEMPTY_GROWTH, (
        f"{authoring_path} regrew unexpectedly: nonempty_lines={len(nonempty)} > "
        f"baseline={BASELINE_NONEMPTY_LINES} + max_growth={MAX_NONEMPTY_GROWTH}. "
        "Refactor shared helpers into authoring/*_ops modules instead of expanding the facade."
    )

    parsed = ast.parse(text, filename=str(authoring_path))
    illegal_imports = _collect_illegal_scene_controller_imports(parsed)
    assert not illegal_imports, f"{authoring_path} must not import scene_controller at runtime:\n" + "\n".join(illegal_imports)
