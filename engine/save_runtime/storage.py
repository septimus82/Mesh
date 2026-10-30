"""Where a game's saves live (#422 H9).

An exported game (``mesh export build``: its folder holds ``bundle_manifest.json``, which only the export writes)
saves per player, outside its installation, which may be read-only (Program Files, /opt, a mounted image):

    Windows  %APPDATA%\\MeshMind Studios\\<game id>\\saves
    macOS    ~/Library/Application Support/MeshMind Studios/<game id>/saves
    Linux    $XDG_DATA_HOME/MeshMind Studios/<game id>/saves   ($XDG_DATA_HOME: ~/.local/share when unset or relative)

``MESH_SAVE_DIR`` names the saves folder itself instead (tests, automation). Anything else (a project in Mesh Studio,
``python main.py`` in a project folder) keeps saving to ``saves`` in the folder it runs in, as before.

An export made before H9 saved into ``<installation>/saves``: those saves stay where they are, are listed and load
(read-only), and are never moved, changed or deleted; a slot saved again is written to the per-user folder, and a slot
in both places loads from the per-user folder.

The game id is ``game_id`` from config.json (new projects get one when created). A project made before H9 has none:
its id is derived from its title, start room and world file, so the same game keeps the same folder; two such games
that share all three share it too (give one a ``game_id`` to separate them).
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import sys
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import DEFAULT_SAVE_DIR

PUBLISHER_DIR = "MeshMind Studios"
SAVE_DIR_ENV = "MESH_SAVE_DIR"
EXPORT_MARKER = "bundle_manifest.json"  # written by engine.tooling.export_bundle.build_bundle, and nothing else
GAME_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def slug(text: str) -> str:
    """``text`` as a lowercase file-name piece (letters, digits, '-'; "Café" → "cafe"), or "" when nothing is left."""
    ascii_text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:40].strip("-")


def new_game_id(title: str) -> str:
    """A fresh id for a new project: its title's slug and 8 random hex digits (two "My Game"s never share one)."""
    return f"{slug(title) or 'game'}-{secrets.token_hex(4)}"


def game_identity(config: Mapping[str, Any]) -> str:
    """The game's id: its ``game_id`` when it has a valid one, else one derived from what an older project has."""
    given = config.get("game_id")
    if isinstance(given, str) and GAME_ID_PATTERN.match(given):
        return given
    basis = "\n".join(str(config.get(key) or "") for key in ("title", "start_scene", "world_file"))
    return f"{slug(str(config.get('title') or '')) or 'game'}-{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:8]}"


def user_data_home() -> Path:
    """The platform's per-user application-data folder."""
    home = Path.home()
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        return Path(appdata) if appdata and Path(appdata).is_absolute() else home / "AppData" / "Roaming"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support"
    xdg = os.environ.get("XDG_DATA_HOME", "")
    return Path(xdg) if xdg and Path(xdg).is_absolute() else home / ".local" / "share"  # (the XDG spec: ignore relative)


def is_exported_game(game_root: Path | None) -> bool:
    return game_root is not None and (game_root / EXPORT_MARKER).is_file()


@dataclass(frozen=True)
class SaveLocation:
    save_dir: Path  # where saves are written (and read first)
    legacy_dir: Path | None  # an older export's saves in its installation: read, never written
    exported: bool
    game_id: str | None


def resolve(game_root: Path | None, config: Mapping[str, Any]) -> SaveLocation:
    """Where the game in ``game_root`` (the folder holding its config.json) keeps its saves."""
    exported = is_exported_game(game_root)
    legacy = game_root / DEFAULT_SAVE_DIR if exported and game_root is not None else None
    override = os.environ.get(SAVE_DIR_ENV, "").strip()
    if override:
        return SaveLocation(Path(override), legacy, exported, game_identity(config) if exported else None)
    if not exported:
        return SaveLocation(Path(DEFAULT_SAVE_DIR), None, False, None)
    game_id = game_identity(config)
    return SaveLocation(user_data_home() / PUBLISHER_DIR / game_id / "saves", legacy, True, game_id)
