import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NotRequired, Sequence, TypedDict, cast

HISTORY_FILE = Path(".mesh/ai_history.jsonl")


class AIHistoryEntry(TypedDict):
    timestamp: str
    plan_path: str
    scenes_touched: list[str]
    result: str
    goal: NotRequired[str]

def append_history_entry(
    plan_path: str,
    scenes_touched: list[str],
    goal: str | None = None,
    result: str = "applied"
) -> None:
    """Append a new entry to the AI history log."""
    entry: AIHistoryEntry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plan_path": str(plan_path),
        "scenes_touched": sorted(list(set(scenes_touched))),
        "result": result,
    }
    if goal:
        entry["goal"] = goal

    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"[Mesh][History] Warning: Failed to append history: {e}")

def load_history() -> list[AIHistoryEntry]:
    """Load all history entries from the log."""
    entries: list[AIHistoryEntry] = []
    if not HISTORY_FILE.exists():
        return entries

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        raw = json.loads(line)
                        if isinstance(raw, dict):
                            entries.append(cast(AIHistoryEntry, raw))
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        print(f"[Mesh][History] Warning: Failed to load history: {e}")

    return entries

def filter_history(
    entries: Sequence[AIHistoryEntry],
    scene: str | None = None,
    plan_path: str | None = None
) -> list[AIHistoryEntry]:
    """Filter history entries by scene or plan path."""
    filtered: list[AIHistoryEntry] = []
    for entry in entries:
        if plan_path and plan_path not in entry.get("plan_path", ""):
            continue
        if scene:
            # Check if scene is in scenes_touched
            # We allow partial match or exact match? User said "contains that scene".
            # Assuming exact match against the ID list.
            if scene not in entry.get("scenes_touched", []):
                continue
        filtered.append(entry)
    return filtered

def extract_scenes_from_plan(plan_data: dict[str, Any]) -> list[str]:
    """Extract a list of scene IDs touched by the plan."""
    scenes = set()
    actions = plan_data.get("actions", [])

    for action in actions:
        # Handle both dicts and Action objects (if passed as dicts)
        args = action.get("args", {}) if isinstance(action, dict) else action.args
        type_ = action.get("type", "") if isinstance(action, dict) else action.type

        # Common patterns
        paths = []
        if "scene_path" in args:
            paths.append(args["scene_path"])
        if "path" in args and "scenes" in str(args["path"]):
            paths.append(args["path"])
        if "from_scene" in args:
            paths.append(args["from_scene"])
        if "to_scene" in args:
            paths.append(args["to_scene"])
        if "into" in args: # place-npc, etc
             # 'into' might be a scene path or ID.
             # If it looks like a path, use it.
             val = args["into"]
             if "/" in val or "\\" in val:
                 paths.append(val)
             else:
                 scenes.add(val)

        for p in paths:
            # Convert path to ID (filename without extension)
            # e.g. scenes/my_scene.json -> my_scene
            # e.g. packs/core/scenes/my_scene.json -> my_scene
            try:
                stem = Path(p).stem
                scenes.add(stem)
            except Exception:
                pass

    return sorted(list(scenes))
