"""Generate golden file for resolved prefabs."""

import json
from pathlib import Path

from engine.prefabs import get_prefab_manager


def main():
    manager = get_prefab_manager()
    manager.load()

    output = {}
    for pid in sorted(manager.prefabs.keys()):
        resolved = manager.get_prefab(pid)
        output[pid] = resolved

    Path("prefabs.golden.json").write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    print("Generated prefabs.golden.json")

if __name__ == "__main__":
    main()
