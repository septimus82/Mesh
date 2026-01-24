import json
from typing import Any, Dict, Iterator

from engine.migrations import migrate_payload

TRACE_SCHEMA_VERSION = 1

def write_event_jsonl(path: str, event_dict: Dict[str, Any], metadata: Dict[str, Any] | None = None) -> None:
    """Append a single event dictionary to a JSONL file."""
    # Inject metadata if provided and not already present
    if metadata:
        for k, v in metadata.items():
            if k not in event_dict:
                event_dict[k] = v

    # Always inject schema version
    event_dict["schema_version"] = TRACE_SCHEMA_VERSION

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event_dict) + "\n")

def read_event_jsonl(path: str) -> Iterator[Dict[str, Any]]:
    """Yield event dictionaries from a JSONL file."""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
                yield migrate_payload("trace", raw)
            except json.JSONDecodeError:
                continue
