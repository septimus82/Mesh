"""How much memory Mesh Studio's undo history holds, and what an edit, an undo and a redo cost (Astra, 12 November).

A disposable project (``build``): the starter room, a small room with ten people, and one or more large rooms of
a thousand objects or more (``--entities``). Then editing sessions as Studio has them, without a window (``Project.edit_scene`` moving one
person of the small room, ``Project.undo``, ``Project.redo``), each in a process of its own:

* edits in the small room only, never having opened a large room;
* the same after opening one large room, and after opening several;
* 25, 50 and 100 edits (one run, measured at each count), then every one undone and redone;
* half undone and a new edit made (the redo history is dropped);
* 150 edits (the history holds 100: the oldest go).

Measured, garbage collected first:

* ``documents_bytes``: the project's documents as loaded (world, rooms, shared player, each room as first read);
* ``traced_bytes``: everything Python allocated since the project was opened and still holds (tracemalloc);
* ``history_bytes``: that, less the same once the history is dropped at the end of the session: what the undo and
  redo history held, as the allocator sees it. This is the number the history is judged by;
* ``process_bytes``: the process's private memory (Windows) or resident set (elsewhere). Complementary only: it
  includes the interpreter and what the allocator keeps after freeing, so nothing is concluded from it alone;
* per edit, undo and redo: the peak of allocations above what was held before it; and wall time, measured in a
  second session without tracemalloc (``untraced``), which slows every allocation.

A digest of every document after the edits, after undoing them all and after redoing them all is recorded too, so two
engines can be shown to leave identical documents for the identical session.

    py -3.13 tooling/undo_history_memory.py OUT [--entities 500] [--repeat 3] [--only SCENARIO,...]

Run it from any checkout (it measures the engine it is run from); ``OUT/undo_history_memory.json`` gets the numbers.
"""

from __future__ import annotations

import gc
import hashlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

WORLD = "packs/core_regions/worlds/main.json"
SMALL_PEOPLE = 10
# name: (large rooms opened before editing, edits, undo and redo them all, then undo half and make a new edit)
SCENARIOS: dict[str, tuple[int, int, bool, bool]] = {
    "small_room_only": (0, 100, True, True),
    "after_one_large_room": (1, 100, True, True),
    "after_three_large_rooms": (3, 100, True, True),
    "past_the_limit": (1, 150, False, False),
}
# Sized so that the engine as it was (a copy of every open room in every undo step) stays under MEMORY_LIMIT: 100 steps
# of three 1,000-object rooms are about 1.8 GB there. The memory scales with objects x open rooms x steps.
CHECKPOINTS = (25, 50, 100, 150)
HISTORY_COPIES = "_frozen"  # where an engine that shares history copies keeps them (absent on older ones)
MEMORY_LIMIT = 3 * 1024 ** 3  # a session's process is ended if it grows past this (``watchdog``)
SESSION_TIMEOUT = 1800  # seconds: a session that takes longer is killed, never left running


def build(dest: Path, large_rooms: int, entities: int) -> Path:
    """The project on disk: ``start``, ``Small`` and ``Large 1..n`` (each of ``entities`` objects)."""
    from engine import authoring
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    create_project(dest, "Undo", template_id="starter")
    project = Project.open(dest, WORLD)
    assert project is not None
    authoring.apply(project, [{"op": "add_room", "label": "Small"},
                              *({"op": "add_room", "label": f"Large {i + 1}"} for i in range(large_rooms))])
    keys = {label: key for key, label, _path in project.rooms()}
    authoring.apply(project, [{"op": "place_prefab", "room": keys["Small"], "prefab": "person", "x": 96 + 64 * p, "y": 160}
                              for p in range(SMALL_PEOPLE)])
    for i in range(large_rooms):
        authoring.apply(project, [{"op": "place_prefab", "room": keys[f"Large {i + 1}"], "prefab": "person", "x": 96, "y": 96}])
    project.save()
    for i in range(large_rooms):  # thousands of objects, written straight to the room's file (placing them one edit
        key = keys[f"Large {i + 1}"]  # at a time would copy the growing room thousands of times)
        path = dest / project.path(key)
        room = json.loads(path.read_text(encoding="utf-8"))
        template = room["entities"][-1]
        room["entities"] = [{**json.loads(json.dumps(template)), "id": f"{key}_thing_{n}", "name": f"Thing {n}",
                             "x": float(64 + 48 * (n % 100)), "y": float(64 + 48 * (n // 100))} for n in range(entities)]
        path.write_text(json.dumps(room, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return dest


def process_bytes() -> int:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        *((name, ctypes.c_size_t) for name in (
                            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                            "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
                            "PrivateUsage"))]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return 0
        return int(counters.PrivateUsage)
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def reachable(roots: list[Any], skip: set[int], objects: dict[int, Any]) -> set[int]:
    """The ids of the documents' objects reachable from ``roots`` and not in ``skip``."""
    seen: set[int] = set()
    stack = list(roots)
    while stack:
        obj = stack.pop()
        if obj is None or id(obj) in seen or id(obj) in skip or isinstance(obj, type):
            continue
        seen.add(id(obj))
        objects[id(obj)] = obj
        if isinstance(obj, dict):
            stack.extend(obj.keys())
            stack.extend(obj.values())
        elif isinstance(obj, (list, tuple, set, frozenset)):
            stack.extend(obj)
        elif type(obj).__module__ == "engine.studio_project" and hasattr(obj, "__dict__"):
            stack.append(vars(obj))
    return seen


def documents_bytes(project: Any) -> int:
    """The project's documents: their objects' own sizes, each counted once. (Only the documents are walked: a
    walk over every object of a large history takes gigabytes itself.)"""
    objects: dict[int, Any] = {}
    documents = reachable([project.world, project.scenes, project.player, project._as_read], set(), objects)
    return sum(sys.getsizeof(objects[i]) for i in documents)


def digest(project: Any) -> str:
    """Every document, rooms as stored, as one number: the same session must give the same on any engine."""
    docs = {"world": project.world, "rooms": {k: project.scenes[k] for k in sorted(project.scenes)},
            "player": project.player, "current": project.current, "dirty": sorted(project.dirty)}
    return hashlib.sha256(json.dumps(docs, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def held(project: Any, base: int) -> dict[str, Any]:
    gc.collect()
    out = {"undo_steps": len(project._undo), "redo_steps": len(project._redo), "process_bytes": process_bytes()}
    if tracemalloc.is_tracing():
        out.update(documents_bytes=documents_bytes(project), traced_bytes=tracemalloc.get_traced_memory()[0] - base)
    return out


def watchdog() -> None:
    """End this process the moment it holds more than MEMORY_LIMIT, whatever it is doing (checked five times a
    second from a thread of its own): a measurement never takes the machine's memory."""
    import threading

    def watch() -> None:
        while True:
            if process_bytes() > MEMORY_LIMIT:
                sys.stderr.write(f"stopped: the session's process passed {MEMORY_LIMIT / 1e9:.0f} GB (use fewer --entities)\n")
                sys.stderr.flush()
                os._exit(3)
            time.sleep(0.2)

    threading.Thread(target=watch, daemon=True).start()


def timed(action: Any) -> tuple[float, int]:
    """(milliseconds, peak of allocations above what was held when it started; 0 when not tracing)."""
    tracing = tracemalloc.is_tracing()
    if tracing:
        tracemalloc.reset_peak()
    before = tracemalloc.get_traced_memory()[0] if tracing else 0
    start = time.perf_counter()
    action()
    ms = (time.perf_counter() - start) * 1000
    return ms, (tracemalloc.get_traced_memory()[1] - before) if tracing else 0


def summary(samples: list[tuple[float, int]]) -> dict[str, Any]:
    if not samples:
        return {"n": 0}
    ms = sorted(s[0] for s in samples)
    return {"n": len(ms), "median_ms": round(statistics.median(ms), 2), "p95_ms": round(ms[int(len(ms) * 0.95) - 1], 2),
            "max_ms": round(ms[-1], 2), "median_peak_bytes": int(statistics.median(s[1] for s in samples)),
            "max_peak_bytes": max(s[1] for s in samples)}


def session(root: Path, name: str, trace: bool = True) -> dict[str, Any]:
    """One scenario. ``trace=False``: no tracemalloc (it slows every allocation): wall times only."""
    from engine import project_ops as ops
    from engine.studio_project import UNDO_LIMIT, Project

    large, edits, round_trip, branch = SCENARIOS[name]
    watchdog()
    gc.collect()
    if trace:
        tracemalloc.start()
    base = tracemalloc.get_traced_memory()[0] if trace else 0
    project = Project.open(root, WORLD)
    assert project is not None
    keys = {label: key for key, label, _path in project.rooms()}
    small = keys["Small"]
    for i in range(large):  # the person opens each large room, looks, and goes back to the small one
        project.current = keys[f"Large {i + 1}"]
        project.scene()
    project.current = small
    person = project.scene()["entities"][0]["id"]
    out: dict[str, Any] = {"scenario": name, "large_rooms_opened": large, "edits": edits, "undo_limit": UNDO_LIMIT,
                           "loaded_rooms": sorted(project.scenes),
                           "objects_per_room": {k: len(project.scenes[k].get("entities") or []) for k in sorted(project.scenes)},
                           "opened": held(project, base), "digest_opened": digest(project), "after_edits": {}}

    def edit(n: int) -> None:
        project.edit_scene(lambda room: ops.move_entity(room, person, 100.0 + n, 160.0), small)

    samples = []
    for n in range(1, edits + 1):
        samples.append(timed(lambda n=n: edit(n)))
        if n in CHECKPOINTS:
            out["after_edits"][str(n)] = held(project, base)
    out["edit"] = summary(samples)
    out["digest_edited"] = digest(project)
    if round_trip:
        undone = []
        for _ in range(len(project._undo)):  # (a count, never a condition that could stay true)
            undone.append(timed(project.undo))
        out["undo"], out["all_undone"], out["digest_all_undone"] = summary(undone), held(project, base), digest(project)
        redone = []
        for _ in range(len(project._redo)):
            redone.append(timed(project.redo))
        out["redo"], out["all_redone"], out["digest_all_redone"] = summary(redone), held(project, base), digest(project)
    if branch:
        for _ in range(len(project._undo) // 2):
            project.undo()
        out["half_undone"] = held(project, base)
        edit(edits + 1)  # a new edit: what could be redone is gone
        out["new_edit_after_half_undone"], out["digest_branched"] = held(project, base), digest(project)
    project._undo.clear()
    project._redo.clear()
    if isinstance(getattr(project, HISTORY_COPIES, None), dict):
        getattr(project, HISTORY_COPIES).clear()
    out["history_dropped"] = dropped = held(project, base)
    if not trace:
        return {"scenario": name, "traced": False, **{k: out[k] for k in ("edit", "undo", "redo") if k in out},
                "process_bytes_at_most": max(v["process_bytes"] for v in out["after_edits"].values())}
    tracemalloc.stop()
    # What the history held at each point: what was allocated and still held then, less what is still held now that
    # the history is gone (the documents are the same size throughout: one person moved).
    for point in (out["opened"], *out["after_edits"].values(), *(out[k] for k in (
            "all_undone", "all_redone", "half_undone", "new_edit_after_half_undone", "history_dropped") if k in out)):
        point["history_bytes"] = point["traced_bytes"] - dropped["traced_bytes"]
    return out


def main(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[1] == "--session":  # a scenario, in this process, on a copy of the project
        print(json.dumps(session(Path(argv[2]), argv[3], trace="--untraced" not in argv)))
        return 0
    out = Path(argv[1])
    entities = int(argv[argv.index("--entities") + 1]) if "--entities" in argv else 500
    only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else list(SCENARIOS)
    repeat = int(argv[argv.index("--repeat") + 1]) if "--repeat" in argv else 3
    out.mkdir(parents=True, exist_ok=True)
    source = out / "project"
    if source.exists():
        shutil.rmtree(source)  # (this script's own folder, made by an earlier run)
    build(source, 3, entities)
    result: dict[str, Any] = {"python": sys.version.split()[0], "platform": platform.platform(),
                              "processor": platform.processor(), "cpus": os.cpu_count(), "entities_per_large_room": entities,
                              "process_bytes_is": "private bytes" if sys.platform == "win32" else "resident set",
                              "repeat": repeat, "runs": {}}
    result["untraced"] = {}
    for name in only:
        runs: list[dict[str, Any]] = []
        untraced: list[dict[str, Any]] = []
        for extra, into in (((), runs), (("--untraced",), untraced)):
            for _ in range(repeat):
                work = out / "work"
                if work.exists():
                    shutil.rmtree(work)
                shutil.copytree(source, work)
                done = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--session", str(work), name, *extra],
                                      capture_output=True, text=True, cwd=REPO, check=False, timeout=SESSION_TIMEOUT)
                if done.returncode != 0:
                    print(done.stderr[-3000:], file=sys.stderr)
                    return 1
                into.append(json.loads(done.stdout.strip().splitlines()[-1]))
        result["runs"][name], result["untraced"][name] = runs, untraced
        last = runs[-1]["after_edits"][str(max(int(k) for k in runs[-1]["after_edits"]))]
        print(f"{name}: documents {last['documents_bytes'] / 1e6:.1f} MB, history {last['history_bytes'] / 1e6:.1f} MB "
              f"at {last['undo_steps']} steps; edit {untraced[-1]['edit']['median_ms']} ms untraced", flush=True)
    shutil.rmtree(out / "work", ignore_errors=True)
    shutil.rmtree(source, ignore_errors=True)
    (out / "undo_history_memory.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
