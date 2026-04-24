import hashlib
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine import json_io
from engine.swallowed_exceptions import _log_swallow
from engine.tooling.plan_types import Plan

HISTORY_DIR = Path(".mesh/plan_history")

def record_history(plan: Plan, result: Dict[str, Any], profile: str = "default"):
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time())
    plan_hash = hashlib.md5(json_io.dumps_stable(asdict(plan)).encode()).hexdigest()[:8]
    filename = f"{timestamp}_{plan_hash}.json"

    record = {
        "timestamp": timestamp,
        "plan_hash": plan_hash,
        "wizard": plan.wizard,
        "profile": profile,
        "inputs": plan.inputs,
        "result": result,
        "plan_snapshot": asdict(plan)
    }

    json_io.write_json_atomic(HISTORY_DIR / filename, record)

def list_history() -> List[Dict[str, Any]]:
    if not HISTORY_DIR.exists():
        return []

    records = []
    for f in sorted(HISTORY_DIR.glob("*.json"), reverse=True):
        try:
            data = json_io.read_json(f)
            records.append({
                "id": f.stem,
                "timestamp": data.get("timestamp"),
                "wizard": data.get("wizard"),
                "actions": len(data.get("plan_snapshot", {}).get("actions", [])),
                "status": "success" # Assumed if written
            })
        except Exception:
            _log_swallow("PLAN-001", "engine/tooling/plan_history.py pass-only blanket swallow")
            pass
    return records

def get_history(history_id: str) -> Optional[Dict[str, Any]]:
    # Try exact match
    path = HISTORY_DIR / f"{history_id}.json"
    if path.exists():
        raw = json_io.read_json(path)
        return raw if isinstance(raw, dict) else None

    # Try prefix match
    matches = list(HISTORY_DIR.glob(f"*{history_id}*.json"))
    if len(matches) == 1:
        raw = json_io.read_json(matches[0])
        return raw if isinstance(raw, dict) else None

    return None
