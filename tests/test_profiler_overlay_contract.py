from __future__ import annotations

from types import SimpleNamespace
import sys

import pytest

import engine.optional_arcade as optional_arcade
from engine.input_runtime.capture_key_router_model import SCOPE_GLOBAL, build_route_table
from engine.ui_overlays import providers
from engine.ui_overlays.profiler_overlay import render_rows

pytestmark = [pytest.mark.fast]


def _make_snapshot() -> object:
    return SimpleNamespace(
        metrics={
            "frame_total_ms": SimpleNamespace(p95=10.5, max=17.25),
            "update_ms": SimpleNamespace(p95=5.0, max=8.5),
            "draw_ms": SimpleNamespace(p95=3.25, max=5.75),
        },
        meta={"counters": {"render_draw_calls": 3}},
    )


def test_profiler_toggle_route_exists() -> None:
    key = optional_arcade.arcade.key
    matches = [
        route
        for route in build_route_table()
        if route.scope == SCOPE_GLOBAL
        and route.action_id == "capture.profiler.toggle"
        and int(route.combo.key) == int(key.F6)
        and int(route.combo.mods) == int(key.MOD_SHIFT)
    ]
    assert matches


def test_render_rows_are_deterministic_and_include_core_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(optional_arcade.arcade, "get_fps", lambda: 60.0)
    snapshot = _make_snapshot()
    overlay_perf = {
        "providers_total": {"count": 3, "total_ms": 6.0, "max_ms": 3.0},
        "command_palette_provider": {"count": 2, "total_ms": 4.0, "max_ms": 2.5},
    }
    rows = render_rows(
        snapshot,
        overlay_perf_snapshot=overlay_perf,
        runtime_summary={
            "entity_count": 42,
            "hot_reload_enabled": True,
            "hot_reload_running": True,
            "rumble_enabled": True,
            "rumble_strength": 0.6,
            "rumble_backend_connected": True,
            "shader_reloaded": 4,
            "shader_failed": 1,
            "textures_reloaded": 7,
            "textures_failed": 2,
            "audio_reloaded": 8,
            "audio_failed": 3,
        },
    )
    rows_again = render_rows(
        snapshot,
        overlay_perf_snapshot=overlay_perf,
        runtime_summary={
            "entity_count": 42,
            "hot_reload_enabled": True,
            "hot_reload_running": True,
            "rumble_enabled": True,
            "rumble_strength": 0.6,
            "rumble_backend_connected": True,
            "shader_reloaded": 4,
            "shader_failed": 1,
            "textures_reloaded": 7,
            "textures_failed": 2,
            "audio_reloaded": 8,
            "audio_failed": 3,
        },
    )
    assert rows == rows_again
    assert rows[0] == "PROFILER (Shift+F6)"
    assert rows[1] == "summary: fps=60.0 entities=42 draw_calls=3"
    assert rows[2] == "dev: hot_reload_enabled=1 running=1"
    assert rows[3] == "dev: rumble_enabled=1 strength=0.60 backend=1"
    assert rows[4] == "hot_reload: shaders reloaded=4 failed=1"
    assert rows[5] == "hot_reload: WARN shader reload failures detected"
    assert rows[6] == "hot_reload: textures reloaded=7 failed=2"
    assert rows[7] == "hot_reload: WARN texture reload failures detected"
    assert rows[8] == "hot_reload: audio reloaded=8 failed=3"
    assert rows[9] == "hot_reload: WARN audio reload failures detected"
    assert "frame: p95=10.50ms max=17.25ms" in rows
    assert "update: p95=5.00ms max=8.50ms" in rows
    assert "draw: p95=3.25ms max=5.75ms" in rows
    assert "overlay_provider_ms:" in rows
    assert "providers_total: n=3 total=6.00ms max=3.00ms" in rows
    assert "command_palette_provider: n=2 total=4.00ms max=2.50ms" in rows


def test_profiler_provider_emits_rows_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(optional_arcade.arcade, "get_fps", lambda: 120.0)
    monkeypatch.setattr(providers, "is_hot_reload_enabled", lambda: True)
    monkeypatch.setattr(
        providers,
        "read_overlay_perf_telemetry",
        lambda reset=False: {
            "providers_total": {"count": 1, "total_ms": 1.5, "max_ms": 1.5},
            "command_palette_provider": {"count": 1, "total_ms": 0.5, "max_ms": 0.5},
        },
    )

    snapshot = _make_snapshot()
    window = SimpleNamespace(
        profiler_overlay=SimpleNamespace(visible=True),
        perf_stats=SimpleNamespace(snapshot=lambda: snapshot),
        scene_controller=SimpleNamespace(get_all_entities=lambda: [1, 2, 3]),
        input_controller=SimpleNamespace(
            manager=SimpleNamespace(
                is_rumble_enabled=lambda: True,
                get_rumble_strength=lambda: 0.5,
                has_rumble_backend=lambda: True,
            )
        ),
        asset_hot_reload_watcher=SimpleNamespace(running=True),
        _last_hot_reload_stats={
            "shader_reloaded": 2,
            "shader_failed": 0,
            "textures_reloaded": 5,
            "textures_failed": 0,
            "audio_reloaded": 6,
            "audio_failed": 0,
        },
    )
    payload = providers.profiler_provider(window)
    assert payload["profiler_enabled"] is True
    assert isinstance(payload["profiler_rows"], list)
    assert payload["profiler_rows"][0] == "PROFILER (Shift+F6)"
    assert payload["profiler_rows"][1].startswith("summary: fps=120.0 entities=3 draw_calls=3")
    assert payload["profiler_rows"][2] == "dev: hot_reload_enabled=1 running=1"
    assert payload["profiler_rows"][3] == "dev: rumble_enabled=1 strength=0.50 backend=1"
    assert payload["profiler_rows"][4] == "hot_reload: shaders reloaded=2 failed=0"
    assert payload["profiler_rows"][5] == "hot_reload: textures reloaded=5 failed=0"
    assert payload["profiler_rows"][6] == "hot_reload: audio reloaded=6 failed=0"


def test_profiler_provider_prefers_perf_counters_without_entity_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(optional_arcade.arcade, "get_fps", lambda: 90.0)
    monkeypatch.setattr(providers, "is_hot_reload_enabled", lambda: False)
    monkeypatch.setattr(
        providers,
        "read_overlay_perf_telemetry",
        lambda reset=False: {
            "providers_total": {"count": 0, "total_ms": 0.0, "max_ms": 0.0},
            "command_palette_provider": {"count": 0, "total_ms": 0.0, "max_ms": 0.0},
        },
    )
    snapshot = SimpleNamespace(
        metrics={},
        meta={"counters": {"world.entities.count": 7, "render.draw_calls": 9}},
    )
    scan_called = {"value": False}

    def _scan_entities() -> list[int]:
        scan_called["value"] = True
        raise AssertionError("entity scan should not be called when perf counter exists")

    window = SimpleNamespace(
        profiler_overlay=SimpleNamespace(visible=True),
        perf_stats=SimpleNamespace(snapshot=lambda: snapshot),
        scene_controller=SimpleNamespace(get_all_entities=_scan_entities),
        asset_hot_reload_watcher=SimpleNamespace(running=False),
    )
    payload = providers.profiler_provider(window)
    assert payload["profiler_enabled"] is True
    assert payload["profiler_rows"][1].startswith("summary: fps=90.0 entities=7 draw_calls=9")
    assert scan_called["value"] is False


def test_profiler_provider_hot_reload_warn_line_is_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(optional_arcade.arcade, "get_fps", lambda: 75.0)
    monkeypatch.setattr(providers, "is_hot_reload_enabled", lambda: True)
    monkeypatch.setattr(
        providers,
        "read_overlay_perf_telemetry",
        lambda reset=False: {
            "providers_total": {"count": 0, "total_ms": 0.0, "max_ms": 0.0},
            "command_palette_provider": {"count": 0, "total_ms": 0.0, "max_ms": 0.0},
        },
    )
    snapshot = _make_snapshot()
    window = SimpleNamespace(
        profiler_overlay=SimpleNamespace(visible=True),
        perf_stats=SimpleNamespace(snapshot=lambda: snapshot),
        scene_controller=SimpleNamespace(get_all_entities=lambda: [1]),
        asset_hot_reload_watcher=SimpleNamespace(running=True),
        _last_hot_reload_stats={
            "shader_reloaded": 1,
            "shader_failed": 3,
            "textures_reloaded": 2,
            "textures_failed": 4,
            "audio_reloaded": 5,
            "audio_failed": 6,
        },
    )
    payload = providers.profiler_provider(window)
    rows = payload["profiler_rows"]
    assert "hot_reload: shaders reloaded=1 failed=3" in rows
    assert "hot_reload: WARN shader reload failures detected" in rows
    assert "hot_reload: textures reloaded=2 failed=4" in rows
    assert "hot_reload: WARN texture reload failures detected" in rows
    assert "hot_reload: audio reloaded=5 failed=6" in rows
    assert "hot_reload: WARN audio reload failures detected" in rows


def test_profiler_provider_disabled_path_is_empty_and_side_effect_free() -> None:
    before = set(sys.modules)
    window = SimpleNamespace(
        profiler_overlay=SimpleNamespace(visible=False),
        perf_stats=SimpleNamespace(snapshot=lambda: (_ for _ in ()).throw(RuntimeError("nope"))),
    )
    payload = providers.profiler_provider(window)
    assert payload == {"profiler_enabled": False, "profiler_rows": []}

    loaded = sorted(set(sys.modules) - before)
    assert not any(name.startswith("engine.editor") for name in loaded)
    assert not any(name.startswith("engine.scene_runtime") for name in loaded)
    assert "engine.scene_controller" not in loaded
