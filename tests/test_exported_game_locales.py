"""H9.2 (#422): an exported game shows its interface text in words.

A project's export carried the installed engine package but neither the engine's ``locales/en.json`` (which an
installed Mesh keeps in ``share/mesh-engine``, outside the package) nor the project's own ``locales/``. A player's
Python has no Mesh, so ``tr`` found no text and every message showed its key: the pause menu said
``UI_SETTINGS_SAVED``. Each game here is exported and run by its own engine in a separate Python, from its own
folder, whose Python holds no Mesh data; the messages are compared with the words, never with ``tr``.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from engine.tooling.export_bundle import build_bundle
from tooling.installed_product_check import bundle_problems

pytestmark = pytest.mark.fast

REPO = Path(__file__).resolve().parent.parent
ENGINE_TEXT = "share/mesh-engine/locales/en.json"

# Run by the exported game's own engine, in its folder (as its main.py does), with a Python holding no Mesh data.
PROBE = r'''
import json, sys, sysconfig
nowhere, locale, keys = sys.argv[1], sys.argv[2], sys.argv[3:]
sysconfig.get_path = lambda *args, **kwargs: nowhere  # (a player's Python: no share/mesh-engine of its own)
sys.path.insert(0, ".")
from engine import i18n
from engine.ui_overlays._settings_data import toast_settings_not_saved, toast_settings_saved
from engine.ui_toasts import ToastManager
class Hud:
    def __init__(self):
        self.toasts = ToastManager()
    def enqueue_toast(self, message, *, seconds=4.0):
        self.toasts.push_toast(message, ttl_s=seconds)
    def active_toasts(self):
        return self.toasts.get_active_toasts()
class Window:
    player_hud = Hud()
i18n.set_locale(locale)
toast_settings_saved(Window)
toast_settings_not_saved(Window)
print("MESH-TEXT " + json.dumps({"toasts": Window.player_hud.active_toasts(), "text": {k: i18n.tr(k) for k in keys}}))
'''


def _export(tmp_path: Path, locales: dict[str, str] | None = None) -> Path:
    """A new blank project, with ``locales`` (name: text) in its ``locales/``, exported (deterministically)."""
    from engine.project_scaffold import create_project

    project = tmp_path / "game"
    create_project(project, "Game", "blank")
    for name, text in (locales or {}).items():
        (project / "locales").mkdir(exist_ok=True)
        (project / "locales" / name).write_text(text, encoding="utf-8")
    bundle = tmp_path / "bundle"
    assert build_bundle(project, bundle, deterministic=True)[0] == 0
    return bundle


def _play(bundle: Path, tmp_path: Path, *keys: str, locale: str = "en") -> dict[str, Any]:
    nowhere = tmp_path / "player python"
    nowhere.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("MESH_") and k != "PYTHONPATH"}
    out = subprocess.run([sys.executable, "-I", "-c", PROBE, str(nowhere), locale, *keys], cwd=bundle,
                         capture_output=True, text=True, timeout=120, env=env)
    line = next((text for text in out.stdout.splitlines() if text.startswith("MESH-TEXT ")), None)
    assert out.returncode == 0 and line is not None, out.stdout + out.stderr
    return json.loads(line[len("MESH-TEXT "):])


def test_an_exported_game_says_its_messages_in_words(tmp_path: Path) -> None:
    played = _play(_export(tmp_path), tmp_path, "UI_SETTINGS_SAVED", "UI_SETTINGS_NOT_SAVED", "UI_LOADING")
    assert played["toasts"] == ["Settings saved", "Settings not saved"]  # (was ["UI_SETTINGS_SAVED", ...])
    assert played["text"] == {"UI_SETTINGS_SAVED": "Settings saved", "UI_SETTINGS_NOT_SAVED": "Settings not saved",
                              "UI_LOADING": "LOADING…"}


def test_an_exported_game_ships_the_engines_text_and_lists_it(tmp_path: Path) -> None:
    """The engine's text, from the running Mesh's allow-listed copy, and nothing else beside the game's own files;
    listed in the bundle's manifest with its hash, and the same in every deterministic export."""
    bundle = _export(tmp_path)
    manifest = json.loads((bundle / "bundle_manifest.json").read_text(encoding="utf-8"))
    listed = {f["path"]: f for f in manifest["files"]}
    assert [p for p in listed if p.startswith(("share/", "locales/"))] == [ENGINE_TEXT]  # (a blank game has no text)
    shipped = (bundle / ENGINE_TEXT).read_bytes()
    assert shipped == (REPO / "locales" / "en.json").read_bytes()
    assert listed[ENGINE_TEXT]["sha256"] == hashlib.sha256(shipped).hexdigest() and listed[ENGINE_TEXT]["category"] == "runtime"
    assert bundle_problems(bundle) == []  # (every file on disk listed, every listed file as hashed)
    again = tmp_path / "again"
    assert build_bundle(tmp_path / "game", again, deterministic=True)[0] == 0
    assert (again / "bundle_manifest.json").read_bytes() == (bundle / "bundle_manifest.json").read_bytes()


def test_a_games_own_text_ships_and_wins_over_the_engines(tmp_path: Path) -> None:
    bundle = _export(tmp_path, {"en.json": json.dumps({"UI_SETTINGS_SAVED": "Saved!", "QUEST_DONE": "Quest done!"}),
                                "notes.txt": "the translator's notes"})
    listed = {f["path"]: f for f in json.loads((bundle / "bundle_manifest.json").read_text(encoding="utf-8"))["files"]}
    assert [p for p in listed if p.startswith(("share/", "locales/"))] == ["locales/en.json", ENGINE_TEXT]
    assert listed["locales/en.json"]["category"] == "content" and bundle_problems(bundle) == []
    played = _play(bundle, tmp_path, "QUEST_DONE", "UI_CANCEL", "NO_SUCH_KEY")
    assert played["toasts"] == ["Saved!", "Settings not saved"]  # (the game's own, then the engine's it didn't list)
    assert played["text"] == {"QUEST_DONE": "Quest done!", "UI_CANCEL": "Cancel", "NO_SUCH_KEY": "NO_SUCH_KEY"}


def test_another_language_falls_back_to_english(tmp_path: Path) -> None:
    bundle = _export(tmp_path, {"de.json": json.dumps({"UI_SETTINGS_SAVED": "Einstellungen gespeichert"})})
    played = _play(bundle, tmp_path, "UI_CANCEL", locale="de")
    assert played["toasts"] == ["Einstellungen gespeichert", "Settings not saved"]
    assert played["text"] == {"UI_CANCEL": "Cancel"}


@pytest.mark.parametrize("broken", ["{not json", "[1, 2]", "\udcff"], ids=["malformed", "not a table", "not utf-8"])
def test_a_broken_translation_of_the_games_falls_back_without_a_crash(tmp_path: Path, broken: str) -> None:
    from engine.project_scaffold import create_project

    project = tmp_path / "game"
    create_project(project, "Game", "blank")
    (project / "locales").mkdir()
    for name in ("en.json", "fr.json"):
        (project / "locales" / name).write_bytes(broken.encode("utf-8", "surrogateescape"))
    bundle = tmp_path / "bundle"
    assert build_bundle(project, bundle, deterministic=True)[0] == 0
    for locale in ("en", "fr"):
        assert _play(bundle, tmp_path, locale=locale)["toasts"] == ["Settings saved", "Settings not saved"]
