"""Lightweight plugin / mod system for Mesh Engine.

Plugins live in a ``mods/`` directory (configurable) under the repository
root.  Each plugin is a sub-directory with a ``mod.json`` manifest and a
Python entry-point module.

Manifest format (``mod.json``)::

    {
        "id": "my_cool_mod",
        "name": "My Cool Mod",
        "version": "1.0.0",
        "author": "Someone",
        "description": "Adds cool things",
        "entry_point": "main",          // Python module name (relative)
        "dependencies": [],             // list of other plugin ids
        "engine_version": ">=0.4.0"     // semver constraint (advisory)
    }

Entry-point module must expose a ``create_plugin()`` factory::

    from engine.plugin_system import MeshPlugin

    class MyCoolPlugin(MeshPlugin):
        def on_enable(self, ctx):
            ctx.event_bus.subscribe("scene_loaded", self._on_scene)

        def _on_scene(self, event):
            ...

    def create_plugin():
        return MyCoolPlugin()
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.logging_tools import get_logger
_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

@dataclass
class PluginManifest:
    """Parsed ``mod.json``."""

    id: str
    name: str
    version: str = "0.0.0"
    author: str = ""
    description: str = ""
    entry_point: str = "main"
    dependencies: List[str] = field(default_factory=list)
    engine_version: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PluginManifest":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", data.get("id", ""))),
            version=str(data.get("version", "0.0.0")),
            author=str(data.get("author", "")),
            description=str(data.get("description", "")),
            entry_point=str(data.get("entry_point", "main")),
            dependencies=list(data.get("dependencies", [])),
            engine_version=str(data.get("engine_version", "")),
        )

    @classmethod
    def load(cls, path: Path) -> "PluginManifest":
        """Load manifest from a ``mod.json`` file."""
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


# ---------------------------------------------------------------------------
# Plugin base class
# ---------------------------------------------------------------------------

class PluginContext:
    """Sandboxed view of the engine passed to plugin lifecycle hooks.

    Plugins access core systems through this context rather than
    importing engine internals directly, which keeps coupling loose and
    makes it straightforward to restrict API surface later.
    """

    def __init__(self, window: Any) -> None:
        self._window = window

    @property
    def event_bus(self) -> Any:
        return getattr(self._window, "event_bus", None)

    @property
    def scene_controller(self) -> Any:
        return getattr(self._window, "scene_controller", None)

    @property
    def console(self) -> Any:
        return getattr(self._window, "console", None)

    @property
    def audio(self) -> Any:
        return getattr(self._window, "audio", None)

    @property
    def engine_config(self) -> Any:
        return getattr(self._window, "engine_config", None)

    @property
    def asset_manager(self) -> Any:
        return getattr(self._window, "asset_manager", None)


class MeshPlugin:
    """Base class for all Mesh Engine plugins.

    Subclass and override lifecycle hooks as needed.
    """

    def on_load(self, ctx: PluginContext) -> None:
        """Called after the plugin is instantiated.

        Use this for one-time setup (registering event handlers, etc.).
        """

    def on_enable(self, ctx: PluginContext) -> None:
        """Called when the plugin is activated during gameplay."""

    def on_disable(self, ctx: PluginContext) -> None:
        """Called when the plugin is deactivated (e.g. user disables it)."""

    def on_unload(self, ctx: PluginContext) -> None:
        """Called before the plugin is removed.  Clean up resources here."""


# ---------------------------------------------------------------------------
# Plugin Manager
# ---------------------------------------------------------------------------

@dataclass
class _LoadedPlugin:
    manifest: PluginManifest
    instance: MeshPlugin
    enabled: bool = False
    module: Any = None


class PluginManager:
    """Discovers, loads, and manages the lifecycle of plugins."""

    def __init__(self, mods_dir: Path | None = None) -> None:
        self._mods_dir: Path | None = mods_dir
        self._plugins: Dict[str, _LoadedPlugin] = {}
        self._ctx: Optional[PluginContext] = None

    @property
    def loaded_ids(self) -> list[str]:
        return list(self._plugins.keys())

    @property
    def enabled_ids(self) -> list[str]:
        return [pid for pid, lp in self._plugins.items() if lp.enabled]

    def get_manifest(self, plugin_id: str) -> Optional[PluginManifest]:
        lp = self._plugins.get(plugin_id)
        return lp.manifest if lp else None

    # -- Discovery & Loading ----------------------------------------------

    def discover(self, mods_dir: Path | None = None) -> list[PluginManifest]:
        """Scan *mods_dir* for plugin directories with ``mod.json``.

        Returns a list of manifests found (does **not** load them yet).
        """
        search_dir = mods_dir or self._mods_dir
        if search_dir is None or not search_dir.is_dir():
            return []

        manifests: list[PluginManifest] = []
        for child in sorted(search_dir.iterdir()):
            manifest_path = child / "mod.json"
            if child.is_dir() and manifest_path.is_file():
                try:
                    manifests.append(PluginManifest.load(manifest_path))
                except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
                    _log_swallow("PLSY-001", "engine/plugin_system.py blanket swallow", once=True)
                    logger.warning("[PluginManager] Failed to read %s: %s", manifest_path, exc)
        return manifests

    def load_all(self, window: Any, mods_dir: Path | None = None) -> list[str]:
        """Discover and load all plugins from *mods_dir*.

        Returns plugin ids that were successfully loaded.
        """
        self._ctx = PluginContext(window)
        search_dir = mods_dir or self._mods_dir
        manifests = self.discover(search_dir)

        if not manifests:
            return []

        # Topological sort by dependencies (simple: load deps first)
        ordered = self._topo_sort(manifests)

        loaded: list[str] = []
        for manifest in ordered:
            if self._load_one(manifest, search_dir or Path("mods")):
                loaded.append(manifest.id)

        return loaded

    def _load_one(self, manifest: PluginManifest, mods_dir: Path) -> bool:
        """Attempt to load a single plugin.  Returns ``True`` on success."""
        if manifest.id in self._plugins:
            return True  # already loaded

        # Check dependencies
        for dep in manifest.dependencies:
            if dep not in self._plugins:
                logger.warning(
                    "[PluginManager] Plugin '%s' requires '%s' which is not loaded — skipping",
                    manifest.id, dep,
                )
                return False

        plugin_dir = mods_dir / manifest.id
        entry_file = plugin_dir / f"{manifest.entry_point}.py"
        if not entry_file.is_file():
            logger.warning("[PluginManager] Entry point '%s' not found for plugin '%s'", entry_file, manifest.id)
            return False

        try:
            mod_name = f"mods.{manifest.id}.{manifest.entry_point}"
            spec = importlib.util.spec_from_file_location(mod_name, str(entry_file))
            if spec is None or spec.loader is None:
                logger.warning("[PluginManager] Cannot create module spec for '%s'", entry_file)
                return False
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)

            factory = getattr(module, "create_plugin", None)
            if not callable(factory):
                logger.warning("[PluginManager] Plugin '%s' has no create_plugin() factory", manifest.id)
                return False

            instance = factory()
            if not isinstance(instance, MeshPlugin):
                logger.warning("[PluginManager] create_plugin() in '%s' did not return a MeshPlugin", manifest.id)
                return False

        except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
            _log_swallow("PLSY-002", "engine/plugin_system.py blanket swallow", once=True)
            logger.warning("[PluginManager] Failed to load plugin '%s': %s", manifest.id, exc)
            return False

        lp = _LoadedPlugin(manifest=manifest, instance=instance, module=module)
        self._plugins[manifest.id] = lp

        if self._ctx is not None:
            try:
                instance.on_load(self._ctx)
            except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
                _log_swallow("PLSY-003", "engine/plugin_system.py blanket swallow", once=True)
                logger.warning("[PluginManager] on_load failed for '%s': %s", manifest.id, exc)

        logger.info("[PluginManager] Loaded plugin '%s' v%s", manifest.id, manifest.version)
        return True

    # -- Enable / Disable -------------------------------------------------

    def enable_all(self) -> None:
        """Enable all loaded plugins."""
        for pid in self._plugins:
            self.enable(pid)

    def enable(self, plugin_id: str) -> bool:
        lp = self._plugins.get(plugin_id)
        if lp is None or lp.enabled:
            return False
        lp.enabled = True
        if self._ctx is not None:
            try:
                lp.instance.on_enable(self._ctx)
            except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
                _log_swallow("PLSY-004", "engine/plugin_system.py blanket swallow", once=True)
                logger.warning("[PluginManager] on_enable failed for '%s': %s", plugin_id, exc)
        return True

    def disable(self, plugin_id: str) -> bool:
        lp = self._plugins.get(plugin_id)
        if lp is None or not lp.enabled:
            return False
        lp.enabled = False
        if self._ctx is not None:
            try:
                lp.instance.on_disable(self._ctx)
            except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
                _log_swallow("PLSY-005", "engine/plugin_system.py blanket swallow", once=True)
                logger.warning("[PluginManager] on_disable failed for '%s': %s", plugin_id, exc)
        return True

    def unload_all(self) -> None:
        """Disable and unload all plugins (reverse order)."""
        for pid in reversed(list(self._plugins.keys())):
            self.disable(pid)
            lp = self._plugins.get(pid)
            if lp is not None and self._ctx is not None:
                try:
                    lp.instance.on_unload(self._ctx)
                except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
                    _log_swallow("PLSY-006", "engine/plugin_system.py blanket swallow", once=True)
                    logger.warning("[PluginManager] on_unload failed for '%s': %s", pid, exc)
        self._plugins.clear()

    # -- Helpers ----------------------------------------------------------

    @staticmethod
    def _topo_sort(manifests: list[PluginManifest]) -> list[PluginManifest]:
        """Simple topological sort so dependencies are loaded first."""
        by_id = {m.id: m for m in manifests}
        visited: set[str] = set()
        result: list[PluginManifest] = []

        def visit(mid: str) -> None:
            if mid in visited:
                return
            visited.add(mid)
            m = by_id.get(mid)
            if m is None:
                return
            for dep in m.dependencies:
                visit(dep)
            result.append(m)

        for m in manifests:
            visit(m.id)

        return result
