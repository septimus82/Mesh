from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.lighting as lighting

pytestmark = [pytest.mark.fast]


def test_resolve_light_symbols_prefers_candidate_order() -> None:
    calls: list[str] = []

    modules = {
        "arcade.experimental.lights": SimpleNamespace(Light=object(), LightLayer=object()),
        "arcade.lights": SimpleNamespace(Light=object(), LightLayer=object()),
        "arcade.future.light": SimpleNamespace(Light=object(), LightLayer=object()),
    }

    def _find_spec(name: str):  # noqa: ANN202
        calls.append(f"find:{name}")
        return object() if name in modules else None

    def _import_module(name: str):  # noqa: ANN202
        calls.append(f"import:{name}")
        return modules[name]

    light, layer = lighting._resolve_light_symbols(find_spec_func=_find_spec, import_module_func=_import_module)
    assert light is modules["arcade.experimental.lights"].Light
    assert layer is modules["arcade.experimental.lights"].LightLayer
    assert calls[:2] == ["find:arcade.experimental.lights", "import:arcade.experimental.lights"]


def test_resolve_light_symbols_falls_back_to_arcade_lights() -> None:
    calls: list[str] = []

    modules = {
        "arcade.lights": SimpleNamespace(Light=object(), LightLayer=object()),
    }

    def _find_spec(name: str):  # noqa: ANN202
        calls.append(f"find:{name}")
        return object() if name in modules else None

    def _import_module(name: str):  # noqa: ANN202
        calls.append(f"import:{name}")
        return modules[name]

    light, layer = lighting._resolve_light_symbols(find_spec_func=_find_spec, import_module_func=_import_module)
    assert light is modules["arcade.lights"].Light
    assert layer is modules["arcade.lights"].LightLayer
    assert calls[:3] == [
        "find:arcade.experimental.lights",
        "find:arcade.lights",
        "import:arcade.lights",
    ]
