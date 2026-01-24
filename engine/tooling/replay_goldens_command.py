import argparse
import json
from pathlib import Path

from engine.config import load_config
from engine.content_lock import build_lock, compute_strict_fingerprint
from engine.events import MeshEvent
from engine.tooling import trace_command


def handle_replay_goldens(args: argparse.Namespace) -> int:
    golden_dir = Path("traces/golden")
    if not golden_dir.exists():
        print(f"[Mesh][Goldens] No golden traces found in {golden_dir}")
        return 0

    traces = list(golden_dir.glob("*.jsonl"))
    traces = sorted(traces, key=lambda p: p.name)
    if not traces:
        print(f"[Mesh][Goldens] No golden traces found in {golden_dir}")
        return 0

    print(f"[Mesh][Goldens] Found {len(traces)} golden traces.")

    failures = []

    for trace_path in traces:
        print(f"[Mesh][Goldens] Replaying {trace_path.name}...")

        # 1. Replay
        config = load_config()
        game = trace_command.HeadlessGame(config)

        # Load events
        try:
            raw_events = trace_command.read_event_jsonl(str(trace_path))
            events = []
            for d in raw_events:
                etype = d.get("type") or d.get("name")
                payload = d.get("payload", {})
                if etype:
                    events.append(MeshEvent(type=etype, payload=payload))
        except Exception as e:
            print(f"  [FAIL] Failed to load trace: {e}")
            failures.append(trace_path.name)
            continue

        # Replay
        try:
            for event in events:
                game.event_bus.emit(event)
                game.update()
        except Exception as e:
            print(f"  [FAIL] Exception during replay: {e}")
            failures.append(trace_path.name)
            continue

        # 2. Assertions
        assertions_path = trace_path.with_suffix(".assertions.json")
        if assertions_path.exists():
            if not trace_command.verify_assertions(game, str(assertions_path)):
                print("  [FAIL] Assertions failed.")
                failures.append(trace_path.name)
                continue
        else:
            print("  [WARN] No assertions file found.")

        # 3. Strict Mode (Fingerprint Check)
        if args.strict:
            # We expect a .meta.json or similar with the expected fingerprint
            meta_path = trace_path.with_suffix(".meta.json")
            if meta_path.exists():
                try:
                    text = meta_path.read_text(encoding="utf-8")
                    # print(f"DEBUG: meta content: {repr(text)}")
                    meta = json.loads(text)
                    expected_fp = meta.get("content_fingerprint")
                    if expected_fp:
                        current_lock = build_lock(args.world or "worlds/main_world.json")
                        current_fp = compute_strict_fingerprint(current_lock)
                        if current_fp != expected_fp:
                            print(f"  [FAIL] Fingerprint mismatch. Expected {expected_fp}, got {current_fp}")
                            failures.append(trace_path.name)
                            continue
                except Exception as e:
                    print(f"  [WARN] Failed to check fingerprint: {e}")
            else:
                print("  [WARN] Strict mode enabled but no meta file found.")

        print(f"  [PASS] {trace_path.name}")

    if failures:
        print(f"\n[Mesh][Goldens] {len(failures)}/{len(traces)} traces failed.")
        return 1

    print(f"\n[Mesh][Goldens] All {len(traces)} traces passed.")
    return 0

def add_replay_goldens_command(subparsers) -> None:
    parser = subparsers.add_parser("replay-goldens", help="Replay golden traces")
    parser.add_argument("--world", help="World file to use for fingerprint check")
    parser.add_argument("--strict", action="store_true", help="Check content fingerprint")
    parser.set_defaults(func=handle_replay_goldens)
