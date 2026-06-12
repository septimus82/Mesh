"""Policy test: no bare ``except:`` in engine source.

Bare ``except:`` catches ``SystemExit``, ``KeyboardInterrupt``, and
``GeneratorExit`` — all of which should propagate.  Use
``except Exception:`` instead.

Ruff rule E722 is now **enforced** (removed from the ignore list).
This AST-based test acts as a safety net in case ruff is not run.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ENGINE_ROOT = Path(__file__).resolve().parent.parent / "engine"


def _collect_python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _find_bare_excepts(filepath: Path) -> list[int]:
    """Return 1-based line numbers of bare ``except:`` handlers."""
    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception:
        return []

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            lines.append(node.lineno)
    return lines


class TestNoBareExcept:
    """Every ``except`` in engine/ must name at least ``Exception``."""

    def test_no_bare_except_in_engine(self) -> None:
        violations: list[str] = []
        for pyfile in _collect_python_files(_ENGINE_ROOT):
            bare_lines = _find_bare_excepts(pyfile)
            for lineno in bare_lines:
                rel = pyfile.relative_to(_ENGINE_ROOT.parent)
                violations.append(f"  {rel}:{lineno}")

        if violations:
            detail = "\n".join(violations)
            pytest.fail(
                f"Bare ``except:`` found (use ``except Exception:`` instead):\n"
                f"{detail}"
            )
