"""Tests for the plugin / mod system."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.fast]

from engine.plugin_system import (
    MeshPlugin,
    PluginContext,
    PluginManifest,
    PluginManager,
)


# ---------------------------------------------------------------------------
# PluginManifest
# ---------------------------------------------------------------------------


class TestPluginManifest:
    def test_from_dict_full(self):
        data = {
            "id": "test_mod",
            "name": "Test Mod",
            "version": "1.2.3",
            "author": "Alice",
            "description": "A test",
            "entry_point": "plugin",
            "dependencies": ["core_lib"],
            "engine_version": ">=0.4.0",
        }
        m = PluginManifest.from_dict(data)
        assert m.id == "test_mod"
        assert m.name == "Test Mod"
        assert m.version == "1.2.3"
        assert m.author == "Alice"
        assert m.entry_point == "plugin"
        assert m.dependencies == ["core_lib"]

    def test_from_dict_minimal(self):
        m = PluginManifest.from_dict({"id": "bare"})
        assert m.id == "bare"
        assert m.name == "bare"
        assert m.version == "0.0.0"
        assert m.entry_point == "main"
        assert m.dependencies == []

    def test_load_from_file(self, tmp_path):
        manifest_path = tmp_path / "mod.json"
        manifest_path.write_text(json.dumps({"id": "file_test", "name": "File Test"}), encoding="utf-8")
        m = PluginManifest.load(manifest_path)
        assert m.id == "file_test"
        assert m.name == "File Test"


# ---------------------------------------------------------------------------
# PluginContext
# ---------------------------------------------------------------------------


class TestPluginContext:
    def test_context_properties(self):
        window = MagicMock()
        window.event_bus = MagicMock()
        window.scene_controller = MagicMock()
        window.console = MagicMock()
        window.audio = MagicMock()
        window.engine_config = MagicMock()
        window.asset_manager = MagicMock()

        ctx = PluginContext(window)
        assert ctx.event_bus is window.event_bus
        assert ctx.scene_controller is window.scene_controller
        assert ctx.console is window.console
        assert ctx.audio is window.audio
        assert ctx.engine_config is window.engine_config
        assert ctx.asset_manager is window.asset_manager

    def test_context_missing_attrs(self):
        """Context returns None for missing attributes on window."""
        window = object()  # bare object, no attrs
        ctx = PluginContext(window)
        assert ctx.event_bus is None
        assert ctx.scene_controller is None


# ---------------------------------------------------------------------------
# MeshPlugin base class
# ---------------------------------------------------------------------------


class TestMeshPlugin:
    def test_lifecycle_hooks_are_noop(self):
        """Base class hooks should not raise."""
        ctx = PluginContext(MagicMock())
        p = MeshPlugin()
        p.on_load(ctx)
        p.on_enable(ctx)
        p.on_disable(ctx)
        p.on_unload(ctx)


# ---------------------------------------------------------------------------
# Helper to create a temp mod directory
# ---------------------------------------------------------------------------


def _create_mod(
    mods_dir: Path,
    mod_id: str,
    *,
    entry_point: str = "main",
    plugin_code: str | None = None,
    dependencies: list[str] | None = None,
    manifest_overrides: dict | None = None,
) -> Path:
    """Create a minimal mod directory with mod.json and entry point."""
    mod_dir = mods_dir / mod_id
    mod_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "id": mod_id,
        "name": mod_id.replace("_", " ").title(),
        "version": "1.0.0",
        "entry_point": entry_point,
        "dependencies": dependencies or [],
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)

    (mod_dir / "mod.json").write_text(json.dumps(manifest), encoding="utf-8")

    if plugin_code is None:
        plugin_code = (
            "from engine.plugin_system import MeshPlugin\n"
            "\n"
            "class TestPlugin(MeshPlugin):\n"
            "    loaded = False\n"
            "    enabled = False\n"
            "    def on_load(self, ctx):\n"
            "        TestPlugin.loaded = True\n"
            "    def on_enable(self, ctx):\n"
            "        TestPlugin.enabled = True\n"
            "    def on_disable(self, ctx):\n"
            "        TestPlugin.enabled = False\n"
            "\n"
            "def create_plugin():\n"
            "    return TestPlugin()\n"
        )
    (mod_dir / f"{entry_point}.py").write_text(plugin_code, encoding="utf-8")
    return mod_dir


# ---------------------------------------------------------------------------
# PluginManager — Discovery
# ---------------------------------------------------------------------------


class TestPluginManagerDiscover:
    def test_discover_empty_dir(self, tmp_path):
        pm = PluginManager()
        manifests = pm.discover(tmp_path)
        assert manifests == []

    def test_discover_nonexistent(self, tmp_path):
        pm = PluginManager()
        manifests = pm.discover(tmp_path / "no_such_dir")
        assert manifests == []

    def test_discover_finds_mods(self, tmp_path):
        _create_mod(tmp_path, "mod_a")
        _create_mod(tmp_path, "mod_b")
        pm = PluginManager()
        manifests = pm.discover(tmp_path)
        ids = [m.id for m in manifests]
        assert "mod_a" in ids
        assert "mod_b" in ids

    def test_discover_skips_bad_manifest(self, tmp_path):
        _create_mod(tmp_path, "good_mod")
        bad = tmp_path / "bad_mod"
        bad.mkdir()
        (bad / "mod.json").write_text("not valid json{{{", encoding="utf-8")
        pm = PluginManager()
        manifests = pm.discover(tmp_path)
        assert len(manifests) == 1
        assert manifests[0].id == "good_mod"


# ---------------------------------------------------------------------------
# PluginManager — Load & Enable
# ---------------------------------------------------------------------------


class TestPluginManagerLoadEnable:
    def test_load_all(self, tmp_path):
        _create_mod(tmp_path, "test_plug")
        pm = PluginManager(tmp_path)
        window = MagicMock()
        loaded = pm.load_all(window, tmp_path)
        assert "test_plug" in loaded
        assert "test_plug" in pm.loaded_ids

    def test_enable_disable(self, tmp_path):
        _create_mod(tmp_path, "toggle_mod")
        pm = PluginManager(tmp_path)
        window = MagicMock()
        pm.load_all(window, tmp_path)
        assert pm.enabled_ids == []

        pm.enable("toggle_mod")
        assert "toggle_mod" in pm.enabled_ids

        pm.disable("toggle_mod")
        assert pm.enabled_ids == []

    def test_enable_all(self, tmp_path):
        _create_mod(tmp_path, "a")
        _create_mod(tmp_path, "b")
        pm = PluginManager(tmp_path)
        window = MagicMock()
        pm.load_all(window, tmp_path)
        pm.enable_all()
        assert set(pm.enabled_ids) == {"a", "b"}

    def test_unload_all(self, tmp_path):
        _create_mod(tmp_path, "unload_me")
        pm = PluginManager(tmp_path)
        window = MagicMock()
        pm.load_all(window, tmp_path)
        pm.enable_all()
        pm.unload_all()
        assert pm.loaded_ids == []
        assert pm.enabled_ids == []

    def test_get_manifest(self, tmp_path):
        _create_mod(tmp_path, "info_mod", manifest_overrides={"version": "2.5.0"})
        pm = PluginManager(tmp_path)
        window = MagicMock()
        pm.load_all(window, tmp_path)
        m = pm.get_manifest("info_mod")
        assert m is not None
        assert m.version == "2.5.0"
        assert pm.get_manifest("no_such") is None


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


class TestPluginDependencies:
    def test_dependency_order(self, tmp_path):
        _create_mod(tmp_path, "base_lib")
        _create_mod(tmp_path, "ext_mod", dependencies=["base_lib"])
        pm = PluginManager(tmp_path)
        window = MagicMock()
        loaded = pm.load_all(window, tmp_path)
        # base_lib should load first
        assert loaded.index("base_lib") < loaded.index("ext_mod")

    def test_missing_dependency_skips(self, tmp_path):
        _create_mod(tmp_path, "needs_missing", dependencies=["not_here"])
        pm = PluginManager(tmp_path)
        window = MagicMock()
        loaded = pm.load_all(window, tmp_path)
        assert "needs_missing" not in loaded


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestPluginErrors:
    def test_no_create_plugin_factory(self, tmp_path):
        code = "# no create_plugin\nclass NotAPlugin: pass\n"
        _create_mod(tmp_path, "no_factory", plugin_code=code)
        pm = PluginManager(tmp_path)
        window = MagicMock()
        loaded = pm.load_all(window, tmp_path)
        assert "no_factory" not in loaded

    def test_create_plugin_returns_wrong_type(self, tmp_path):
        code = "def create_plugin(): return 42\n"
        _create_mod(tmp_path, "bad_type", plugin_code=code)
        pm = PluginManager(tmp_path)
        window = MagicMock()
        loaded = pm.load_all(window, tmp_path)
        assert "bad_type" not in loaded

    def test_entry_point_missing_file(self, tmp_path):
        mod_dir = tmp_path / "no_file"
        mod_dir.mkdir()
        (mod_dir / "mod.json").write_text(
            json.dumps({"id": "no_file", "entry_point": "nonexistent"}),
            encoding="utf-8",
        )
        pm = PluginManager(tmp_path)
        window = MagicMock()
        loaded = pm.load_all(window, tmp_path)
        assert "no_file" not in loaded

    def test_on_load_exception_handled(self, tmp_path):
        code = (
            "from engine.plugin_system import MeshPlugin\n"
            "\n"
            "class BrokenPlugin(MeshPlugin):\n"
            "    def on_load(self, ctx):\n"
            "        raise RuntimeError('boom')\n"
            "\n"
            "def create_plugin():\n"
            "    return BrokenPlugin()\n"
        )
        _create_mod(tmp_path, "broken", plugin_code=code)
        pm = PluginManager(tmp_path)
        window = MagicMock()
        # Should not raise
        loaded = pm.load_all(window, tmp_path)
        assert "broken" in loaded  # loaded despite on_load error


# ---------------------------------------------------------------------------
# Lifecycle hooks
# ---------------------------------------------------------------------------


class TestPluginLifecycle:
    def test_full_lifecycle(self, tmp_path):
        """Verify on_load → on_enable → on_disable → on_unload sequence."""
        calls: list[str] = []
        code = (
            "from engine.plugin_system import MeshPlugin\n"
            "\n"
            "calls = []\n"
            "\n"
            "class TrackPlugin(MeshPlugin):\n"
            "    def on_load(self, ctx): calls.append('load')\n"
            "    def on_enable(self, ctx): calls.append('enable')\n"
            "    def on_disable(self, ctx): calls.append('disable')\n"
            "    def on_unload(self, ctx): calls.append('unload')\n"
            "\n"
            "def create_plugin():\n"
            "    return TrackPlugin()\n"
        )
        _create_mod(tmp_path, "lifecycle", plugin_code=code)
        pm = PluginManager(tmp_path)
        window = MagicMock()
        pm.load_all(window, tmp_path)
        pm.enable_all()
        pm.unload_all()

        # Access the 'calls' list from the loaded module
        import sys
        mod = sys.modules.get("mods.lifecycle.main")
        assert mod is not None
        assert mod.calls == ["load", "enable", "disable", "unload"]


# ---------------------------------------------------------------------------
# Topo sort
# ---------------------------------------------------------------------------


class TestTopoSort:
    def test_no_deps(self):
        manifests = [
            PluginManifest(id="a", name="A"),
            PluginManifest(id="b", name="B"),
        ]
        result = PluginManager._topo_sort(manifests)
        ids = [m.id for m in result]
        assert set(ids) == {"a", "b"}

    def test_linear_deps(self):
        manifests = [
            PluginManifest(id="c", name="C", dependencies=["b"]),
            PluginManifest(id="b", name="B", dependencies=["a"]),
            PluginManifest(id="a", name="A"),
        ]
        result = PluginManager._topo_sort(manifests)
        ids = [m.id for m in result]
        assert ids.index("a") < ids.index("b") < ids.index("c")

    def test_missing_dep_not_in_set(self):
        manifests = [
            PluginManifest(id="x", name="X", dependencies=["missing"]),
        ]
        result = PluginManager._topo_sort(manifests)
        assert len(result) == 1  # still returned, loading will fail on dep check
