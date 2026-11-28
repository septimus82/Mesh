"""Policy test: a behaviour subscribes to the event bus only while it is built (``__init__``).

The scene records every subscription made while an entity's behaviours are constructed and ends them when the
entity is removed (killed, collected, despawned, deleted) or the room is left (#637). A subscription made anywhere
else is not recorded and outlives its entity: EventLogger's ``on_added``, which nothing calls, logged nothing
(#638 NEW-4). ``destroy()``/``on_removed()`` are not teardown hooks either: nothing in the runtime calls them.

This AST-based test scans engine/behaviours/ for ``event_bus`` subscriptions outside ``__init__``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]

_BEHAVIOURS_ROOT = Path(__file__).resolve().parent.parent / "engine" / "behaviours"


def _mentions_event_bus(node: ast.AST) -> bool:
    return any((isinstance(n, ast.Attribute) and n.attr == "event_bus") or (isinstance(n, ast.Constant) and n.value == "event_bus")
               for n in ast.walk(node))


def _late_subscriptions(source: str) -> list[str]:
    """``Class.method`` for each event-bus subscribe/subscribe_all made outside ``__init__``."""
    found: list[str] = []
    for cls in (n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ClassDef)):
        for fn in (n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
            if fn.name == "__init__":
                continue
            bus_names = {t.id for a in ast.walk(fn) if isinstance(a, ast.Assign) and _mentions_event_bus(a.value)
                         for t in a.targets if isinstance(t, ast.Name)}  # (bus = getattr(window, "event_bus"))
            for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
                if call.func.attr not in ("subscribe", "subscribe_all"):
                    continue
                receiver = call.func.value
                if _mentions_event_bus(receiver) or (isinstance(receiver, ast.Name) and receiver.id in bus_names):
                    found.append(f"{cls.name}.{fn.name}")
    return found


def test_behaviours_subscribe_only_while_built() -> None:
    late = [f"{path.relative_to(_BEHAVIOURS_ROOT)}: {where}" for path in sorted(_BEHAVIOURS_ROOT.rglob("*.py"))
            for where in _late_subscriptions(path.read_text(encoding="utf-8"))]
    assert not late, "subscribe in __init__, where the scene records it and ends it on removal: " + ", ".join(late)


def test_the_policy_sees_a_late_subscription() -> None:
    late = '''
class Logger:
    def __init__(self, window):
        window.event_bus.subscribe("a", print)
    def on_added(self):
        self.window.event_bus.subscribe_all(print)
    def later(self):
        bus = getattr(self.window, "event_bus", None)
        bus.subscribe("b", print)
    def gameplay(self):
        bus = getattr(self.window, "gameplay_event_bus", None)
        bus.subscribe("c", print)
'''
    assert _late_subscriptions(late) == ["Logger.on_added", "Logger.later"]
