"""``mesh doctor``: the Health and Combat settings Mesh's own tools wrote before #651, found; corrected only on request.

Owner decision D12: a ``mesh doctor`` warning and an opt-in correction (``mesh doctor --fix-health-defaults``), never a
silent rewrite. Before #651, adding Health or Combat in Mesh Studio, ``mesh author`` or MCP wrote every default into
the file (``project_ops.add_behaviour``). Those values are explicit, so they still apply after the fix: a "Health 50"
enemy starts at 1 of 50, and the player at 1 of 1 dealing 1 damage, whatever its stats say.

What counts as tool-written, per behaviour config (the keys are what add_behaviour wrote, so a creator's own partial
config never matches):

* Health holding all three of ``max_hp``, ``hp`` and ``invulnerable``, with ``hp == 1``, and either
  - ``max_hp > 1`` ("Health N" set afterwards, "Starts with" left at the tool's 1): the fix drops ``hp`` (starts full);
  - or the entity is the player and ``max_hp == 1`` (left as added): the fix drops ``hp`` and ``max_hp`` (the stats').
* The player's Combat holding all seven keys the tool wrote, with ``damage == 1``: the fix drops ``damage`` (the
  stats' attack).

Not flagged: a config missing any of those keys (``{"hp": 1}`` or ``{"hp": 1, "max_hp": 50}`` is the creator's own
choice), and Health left as added (1 of 1) on anything but the player, which plays the same either way.
Scanned: the world's rooms and ``assets/prefabs.json`` (the shared player). The fix owns the project (as ``mesh author``
does), copies each file it changes under ``.mesh/backups/`` first, and changes nothing else in it.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

HEALTH_KEYS = frozenset({"max_hp", "hp", "invulnerable"})
COMBAT_KEYS = frozenset({"damage", "cooldown", "range", "hitbox_size", "target_tag", "attack_anim", "attack_sound"})
PREFABS = "assets/prefabs.json"
FIX_FLAG = "--fix-health-defaults"


@dataclass(frozen=True)
class Finding:
    file: str  # project-relative
    entity: str
    behaviour: str
    drop: tuple[str, ...]
    message: str


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _is_player(entity: dict[str, Any]) -> bool:
    return entity.get("tag") == "player" or entity.get("prefab_id") == "player"  # (project_ops.PLAYER_PREFAB)


def _drops(entity: dict[str, Any]) -> Iterator[tuple[str, tuple[str, ...], str]]:
    configs = entity.get("behaviour_config")
    if not isinstance(configs, dict):
        return
    health, combat = configs.get("Health"), configs.get("Combat")
    if isinstance(health, dict) and HEALTH_KEYS <= health.keys() and _num(health["hp"]) == 1.0:
        max_hp = _num(health["max_hp"])
        if max_hp is not None and max_hp > 1.0:
            yield "Health", ("hp",), f"starts at 1 of {max_hp:g} HP; with the fix it starts full"
        elif max_hp == 1.0 and _is_player(entity):
            yield "Health", ("hp", "max_hp"), "has 1 of 1 HP; with the fix it takes max_hp from the player's stats"
    if (isinstance(combat, dict) and COMBAT_KEYS <= combat.keys() and _num(combat["damage"]) == 1.0
            and _is_player(entity)):
        yield "Combat", ("damage",), "deals 1 damage; with the fix it deals the player's stats' attack"


def _entities(doc: Any) -> list[dict[str, Any]]:
    if isinstance(doc, dict) and isinstance(doc.get("entities"), list):
        return [e for e in doc["entities"] if isinstance(e, dict)]
    if isinstance(doc, list):  # prefabs.json
        return [p["entity"] for p in doc if isinstance(p, dict) and isinstance(p.get("entity"), dict)]
    return []


def project_files(world: str | Path) -> tuple[Path, list[Path]]:
    """The project root (the folder above ``world`` holding config.json, else the current folder) and the files to
    scan: the world's rooms and the prefabs file, those that exist."""
    world_path = Path(world).resolve()
    root = next((d for d in world_path.parents if (d / "config.json").is_file()), Path.cwd().resolve())
    try:
        scenes = json.loads(world_path.read_text(encoding="utf-8")).get("scenes")
    except (OSError, ValueError, AttributeError):
        scenes = None
    entries = scenes.values() if isinstance(scenes, dict) else scenes if isinstance(scenes, list) else []
    rels = [e.get("path") if isinstance(e, dict) else e for e in entries]
    files = dict.fromkeys(root / r for r in [*rels, PREFABS] if isinstance(r, str) and r)
    return root, [f for f in files if f.is_file()]


def _scan(root: Path, files: list[Path]) -> Iterator[tuple[Path, Any, list[Finding]]]:
    for path in files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
        found = []
        for entity in _entities(doc):
            label = str(entity.get("name") or entity.get("id") or "?")
            for behaviour, drop, what in _drops(entity):
                found.append(Finding(rel, label, behaviour, drop, f"{rel}: {label}'s {behaviour} {what} (the "
                                     f"settings Mesh's tools wrote before #651; if you chose them, keep them)."))
        if found:
            yield path, doc, found


def find(world: str | Path) -> list[Finding]:
    """What ``mesh doctor`` warns about. Reads only."""
    root, files = project_files(world)
    return [f for _path, _doc, found in _scan(root, files) for f in found]


def fix(world: str | Path) -> list[Finding]:
    """Drop the settings ``find`` reports, owning the project as ``mesh author`` does (raises
    project_ownership.OwnedElsewhere / OwnershipUnavailable if it can't: nothing changed). Each changed file is copied
    to ``.mesh/backups/health-defaults-<time>/`` first."""
    from engine import json_io
    from engine.editor import project_ownership  # noqa: PLC0415  # (heavy: only when writing)

    root, _ = project_files(world)
    fixed: list[Finding] = []
    with project_ownership.acquire(root, project_ownership.AUTHORING, wait=0.5) as held:
        backup = root / ".mesh" / "backups" / f"health-defaults-{time.strftime('%Y%m%d-%H%M%S')}"
        for path, doc, found in _scan(root, project_files(world)[1]):
            if not held.owns(path):
                continue
            for entity in _entities(doc):
                for behaviour, drop, _what in list(_drops(entity)):
                    for key in drop:
                        entity["behaviour_config"][behaviour].pop(key, None)
            copy = backup / path.relative_to(root)
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, copy)
            json_io.write_json_atomic(path, doc)
            fixed += found
    return fixed
