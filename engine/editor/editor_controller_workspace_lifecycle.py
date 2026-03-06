from __future__ import annotations

from typing import Any

def load_keymap_overrides(self):
    """Load keymap overrides from keymap.json.

    DELEGATED to EditorKeymapController.
    """
    self.keymap.load_overrides()


def load_workspace(self):
    self._workspace_ctl.load_workspace()


def save_workspace(self):
    self._workspace_ctl.save_workspace()


def _autosave_workspace(self, now_ns: int | None = None):
    self._workspace_ctl.schedule_autosave(now_ns=now_ns)


def _flush_workspace_autosave(self):
    self._workspace_ctl.flush_autosave()

def bind_workspace_lifecycle_methods(cls: Any) -> None:
    cls.load_keymap_overrides = load_keymap_overrides
    cls.load_workspace = load_workspace
    cls.save_workspace = save_workspace
    cls._autosave_workspace = _autosave_workspace
    cls._flush_workspace_autosave = _flush_workspace_autosave
