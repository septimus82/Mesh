from pathlib import Path

from engine import json_io
from engine.content_lock import build_lock, compute_strict_fingerprint


def main():
    lock = build_lock("worlds/main_world.json")
    fp = compute_strict_fingerprint(lock)
    print(f"Computed strict fingerprint: {fp}")

    golden_dir = Path("traces/golden")
    for trace_path in golden_dir.glob("*.jsonl"):
        meta_path = trace_path.with_suffix(".meta.json")
        if meta_path.exists():
            data = json_io.read_json(meta_path)
        else:
            data = {}

        data["content_fingerprint"] = fp
        json_io.write_json_atomic(meta_path, data)
        print(f"Updated {meta_path}")

if __name__ == "__main__":
    main()
