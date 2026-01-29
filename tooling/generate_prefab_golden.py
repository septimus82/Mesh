"""Generate golden file for resolved prefabs."""

import json
from pathlib import Path

from engine import json_io
from engine.prefabs import get_prefab_manager


def main():
    manager = get_prefab_manager()
    manager.load()

    output = {}
    for pid in sorted(manager.prefabs.keys()):
        resolved = manager.get_prefab(pid)
        output[pid] = resolved

    json_io.write_json_atomic("prefabs.golden.json", output)
    print("Generated prefabs.golden.json")

if __name__ == "__main__":
    main()
