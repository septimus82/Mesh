"""F10 (#422): how much memory a long AI-assisted editing session leaves behind in Mesh Studio's proposals.

A disposable, realistically populated project (``build``): the starter room plus eight more, each with a 64 x 48
map painted on two layers and twenty people. Then a long session (``session``) as Studio has it, without a window:
- Studio's AI host with its live session running, as when Studio is open;
- an AI proposing changes through the MCP path (``authoring_session.propose``, ``proposal_status``, ``withdraw``);
- the person deciding in Studio: accepting most proposals, rejecting some; some fail on acceptance; some end in a
  conflict with the person's own edits; a few are still waiting at the end.

Measured afterwards (garbage collected):
- ``proposal_copies``: how many proposals still hold whole-project documents (``base`` / ``after``);
- ``exclusive_bytes``: the bytes reachable only through the proposals (Studio's list and the bridge's map),
  excluding what the project itself (its documents, undo history) and the F6 revision snapshots hold anyway;
- ``traced_bytes``: everything Python allocated during the session and still holds (tracemalloc), for scale.

    py -3.13 tooling/f10_proposal_memory.py OUT [--proposals N]

Run it from any checkout (it measures the engine it is run from); ``OUT/f10_memory.json`` gets the numbers.
"""

from __future__ import annotations

import gc
import json
import shutil
import sys
import threading
import time
import tracemalloc
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

ROOMS = 8
MAP = (64, 48)
PEOPLE = 20


def build(dest: Path) -> Path:
    from engine import authoring
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    create_project(dest, "Big", template_id="starter")
    project = Project.open(dest, "packs/core_regions/worlds/main.json")
    assert project is not None
    for i in range(ROOMS):
        authoring.apply(project, [{"op": "add_room", "label": f"Room {i + 1}"}])
    for key, _label, _path in project.rooms():
        width, height = MAP
        cells = [[x, y] for x in range(width) for y in range(height)]
        border = [[x, y] for x, y in cells if x in (0, width - 1) or y in (0, height - 1)]
        changes = [{"op": "resize_map", "room": key, "width": width, "height": height},
                   {"op": "paint_tiles", "room": key, "layer": "ground", "cells": cells, "tile": 1 + (len(key) % 3)},
                   {"op": "paint_tiles", "room": key, "layer": "walls", "cells": border, "tile": 5}]
        changes += [{"op": "place_prefab", "room": key, "prefab": "person", "x": 96 + 64 * (p % 10),
                     "y": 96 + 96 * (p // 10)} for p in range(PEOPLE)]
        try:
            authoring.apply(project, changes)
        except authoring.ChangeError:  # (a room without a "walls" layer: paint its ground only)
            authoring.apply(project, [c for c in changes if c.get("layer") != "walls"])
    project.save()
    return dest


class _Studio:
    """What Studio's AI host needs of Studio, without a window (as tests/test_authoring_session_discovery.py)."""

    def __init__(self, project: Any) -> None:
        self.project = project
        self.window = SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path=project.path(project.current)))

    def on_ai_proposal(self, proposal: Any) -> None: ...
    def on_ai_decided(self, proposal: Any) -> None: ...


def _sizes(roots: list[Any], exclude: list[Any]) -> int:
    """Bytes of the objects reachable from ``roots`` and not from ``exclude`` (each object counted once)."""
    def walk(start: list[Any], skip: set[int]) -> set[int]:
        seen: set[int] = set()
        stack = list(start)
        while stack:
            obj = stack.pop()
            if id(obj) in seen or id(obj) in skip or isinstance(obj, (type, threading.Thread)):
                continue
            seen.add(id(obj))
            objects[id(obj)] = obj
            if isinstance(obj, dict):
                stack.extend(obj.keys())
                stack.extend(obj.values())
            elif isinstance(obj, (list, tuple, set, frozenset)):
                stack.extend(obj)
            elif hasattr(obj, "__dict__") and type(obj).__module__.startswith("engine.studio_ai"):
                stack.append(vars(obj))
        return seen

    objects: dict[int, Any] = {}
    excluded = walk(exclude, set())
    return sum(sys.getsizeof(objects[i]) for i in walk(roots, excluded))


def session(root: Path, proposals: int) -> dict[str, Any]:
    from engine import authoring, authoring_session
    from engine.studio_ai import StudioAIHost
    from engine.studio_project import Project

    project = Project.open(root, "packs/core_regions/worlds/main.json")
    assert project is not None
    studio = _Studio(project)
    host = StudioAIHost(studio)
    host.start()
    stop = threading.Event()

    def pump() -> None:  # (Studio's on_update)
        while not stop.is_set():
            host.drain()
            time.sleep(0.002)

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    outcomes: dict[str, int] = {}
    rooms = [key for key, _label, _path in project.rooms()]
    gc.collect()
    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    try:
        for i in range(proposals):
            room = rooms[i % len(rooms)]
            kind = ("accept", "accept", "reject", "withdraw", "fail", "conflict")[i % 6]
            revision = authoring_session.read_project(root)["revision"]
            if kind == "fail":  # (removes a person the person removes first: nothing to remove when accepted)
                victim = next(e["id"] for e in project.scene(room)["entities"] if "_person_" in str(e.get("id")))
                changes: list[dict[str, Any]] = [{"op": "remove_entity", "room": room, "entity_id": victim}]
            elif kind == "conflict":  # (renames a person the person renames too, differently)
                victim = next(e["id"] for e in project.scene(room)["entities"] if "_person_" in str(e.get("id")))
                changes = [{"op": "rename_entity", "room": room, "entity_id": victim, "name": f"AI name {i}"}]
            else:
                changes = [{"op": "place_prefab", "room": room, "prefab": "person", "x": 200 + i, "y": 300}]
            staged = authoring_session.propose(root, changes, title=f"Change {i}", base_revision=revision)
            assert staged.get("ok"), staged
            pid = staged["proposal_id"]
            proposal = next(p for p in host.proposals if p.proposal_id == pid)
            if kind == "accept":
                outcome = host.accept(proposal)
            elif kind == "reject":
                outcome = host.reject_proposal(proposal)
            elif kind == "withdraw":
                outcome = authoring_session.withdraw(root, pid)
            elif kind == "fail":
                authoring.apply(project, [{"op": "remove_entity", "room": room, "entity_id": victim}])
                outcome = host.accept(proposal)
            else:
                authoring.apply(project, [{"op": "rename_entity", "room": room, "entity_id": victim,
                                           "name": f"Person's name {i}"}])
                outcome = host.accept(proposal)
                if i < proposals - 12:  # (the last few conflicts stay waiting; the others are rejected)
                    host.reject_proposal(proposal)
            status = authoring_session.proposal_status(root, pid)
            assert status.get("ok"), status
            outcomes[status["proposal"]["status"]] = outcomes.get(status["proposal"]["status"], 0) + 1
            del outcome
        gc.collect()
        traced = tracemalloc.get_traced_memory()[0] - before
        bridge_map = getattr(host.bridge, "_proposals", {})
        exclusive = _sizes([host.proposals, bridge_map], [project.__dict__, host._snapshots])
        distinct = {id(p): p for p in [*host.proposals, *bridge_map.values()]}.values()
        copies = sum(1 for p in distinct if getattr(p, "base", None) or getattr(p, "after", None))
        statuses: dict[str, int] = {}
        for p in host.proposals:
            statuses[p.status] = statuses.get(p.status, 0) + 1
        return {"proposals_made": proposals, "statuses_kept": statuses, "outcomes": outcomes,
                "kept_in_studio": len(host.proposals), "kept_by_bridge": len(bridge_map),
                "proposal_copies": copies, "exclusive_bytes": exclusive, "traced_bytes": traced,
                "project_bytes": len(json.dumps(project.all_documents())), "revision": project.revision}
    finally:
        tracemalloc.stop()
        stop.set()
        thread.join(timeout=2)
        host.stop()


def run(out: Path, proposals: int = 120) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    root = out / "project"
    if root.exists():
        shutil.rmtree(root)
    build(root)
    try:
        result = session(root, proposals)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    (out / "f10_memory.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    count = int(sys.argv[sys.argv.index("--proposals") + 1]) if "--proposals" in sys.argv else 120
    print(json.dumps(run(Path(args[0]), count), indent=1))
