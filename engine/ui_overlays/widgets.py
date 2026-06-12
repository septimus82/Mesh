"""Compatibility re-export for shared UI widget primitives."""

from __future__ import annotations

import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType


def _load_shared_widgets_module() -> ModuleType:
    module_name = "engine._ui_widgets_shared"
    cached = sys.modules.get(module_name)
    if isinstance(cached, ModuleType):
        return cached
    source_path = Path(__file__).resolve().parents[1] / "ui" / "widgets.py"
    spec = spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"Unable to load shared widgets module from {source_path}")
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_shared = _load_shared_widgets_module()

Rect = _shared.Rect
Padding = _shared.Padding
DrawInstruction = _shared.DrawInstruction
LayoutResult = _shared.LayoutResult
Widget = _shared.Widget
Label = _shared.Label
Button = _shared.Button
VStack = _shared.VStack
Panel = _shared.Panel
TextInput = _shared.TextInput
Slider = _shared.Slider
Toggle = _shared.Toggle
ScrollList = _shared.ScrollList

__all__ = [
    "Rect",
    "Padding",
    "DrawInstruction",
    "LayoutResult",
    "Widget",
    "Label",
    "Button",
    "VStack",
    "Panel",
    "TextInput",
    "Slider",
    "Toggle",
    "ScrollList",
]
