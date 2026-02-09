"""Policy test: event subscriptions must have a teardown path.

Any Behaviour that calls ``event_bus.subscribe()`` in ``__init__`` or
``on_added()`` MUST store the returned unsubscribe callable and release
it in ``destroy()`` or ``on_removed()``.

This AST-based test scans engine/behaviours/ for violations.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

_BEHAVIOURS_ROOT = Path(__file__).resolve().parent.parent / "engine" / "behaviours"


def _collect_python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _check_subscription_lifecycle(filepath: Path) -> list[str]:
    """Return violation messages for classes that subscribe without cleanup."""
    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception:
        return []

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        # Check if this class calls event_bus.subscribe anywhere
        subscribes = False
        stores_unsubscribe = False
        has_cleanup = False

        for child in ast.walk(node):
            # Look for event_bus.subscribe(...) calls
            if isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Attribute) and func.attr == "subscribe":
                    if isinstance(func.value, ast.Attribute) and func.value.attr == "event_bus":
                        subscribes = True

            # Look for self._unsubscribe = ... or self._unsubscribers = ...
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                        if target.value.id == "self" and "unsubscrib" in target.attr.lower():
                            stores_unsubscribe = True

        # Check for destroy() or on_removed() method
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if item.name in ("destroy", "on_removed"):
                    has_cleanup = True

        if subscribes and not (stores_unsubscribe and has_cleanup):
            rel = filepath.relative_to(_BEHAVIOURS_ROOT.parent.parent)
            parts = []
            if not stores_unsubscribe:
                parts.append("does not store unsubscribe callable")
            if not has_cleanup:
                parts.append("has no destroy()/on_removed() method")
            detail = "; ".join(parts)
            violations.append(f"  {rel}: {node.name} — {detail}")

    return violations


class TestEventSubscriptionLifecycle:
    """Behaviours that subscribe to the event bus must clean up."""

    def test_all_subscriptions_have_cleanup(self) -> None:
        all_violations: list[str] = []
        for pyfile in _collect_python_files(_BEHAVIOURS_ROOT):
            all_violations.extend(_check_subscription_lifecycle(pyfile))

        if all_violations:
            detail = "\n".join(all_violations)
            pytest.fail(
                f"Event subscription(s) without cleanup path:\n{detail}\n\n"
                "Store the unsubscribe callable and release it in "
                "destroy() or on_removed()."
            )
