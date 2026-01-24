import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.tooling.plan_types import Plan

HISTORY_DIR = Path(".mesh/plan_history")

def record_history(plan: Plan, result: Dict[str, Any], profile: str = "default"):
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time())
    plan_hash = hashlib.md5(json.dumps(asdict(plan), sort_keys=True).encode()).hexdigest()[:8]
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

    with (HISTORY_DIR / filename).open("w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)

def list_history() -> List[Dict[str, Any]]:
    if not HISTORY_DIR.exists():
        return []

    records = []
    for f in sorted(HISTORY_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            records.append({
                "id": f.stem,
                "timestamp": data.get("timestamp"),
                "wizard": data.get("wizard"),
                "actions": len(data.get("plan_snapshot", {}).get("actions", [])),
                "status": "success" # Assumed if written
            })
        except:
            pass
    return records

def get_history(history_id: str) -> Optional[Dict[str, Any]]:
    # Try exact match
    path = HISTORY_DIR / f"{history_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    # Try prefix match
    matches = list(HISTORY_DIR.glob(f"*{history_id}*.json"))
    if len(matches) == 1:
        return json.loads(matches[0].read_text(encoding="utf-8"))

    return None
