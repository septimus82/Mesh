"""Content diff engine for comparing lockfiles."""

from __future__ import annotations

from typing import Any, Dict


def diff_locks(old_lock: Dict[str, Any], new_lock: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the difference between two content locks."""

    diff: dict[str, Any] = {
        "packs": {
            "added": [],
            "removed": [],
            "version_changed": [],
            "order_changed": None
        },
        "overrides": {
            "total_delta": 0,
            "added": [],
            "removed": [],
            "changed": []
        },
        "content_files": {
            "changed": [],
            "added": [],
            "removed": []
        }
    }

    # 1. Pack Changes
    old_packs = {p["id"]: p for p in old_lock.get("packs", [])}
    new_packs = {p["id"]: p for p in new_lock.get("packs", [])}

    old_ids = set(old_packs.keys())
    new_ids = set(new_packs.keys())

    # Added/Removed
    for pid in sorted(new_ids - old_ids):
        diff["packs"]["added"].append({
            "id": pid,
            "version": new_packs[pid]["version"]
        })

    for pid in sorted(old_ids - new_ids):
        diff["packs"]["removed"].append({
            "id": pid,
            "version": old_packs[pid]["version"]
        })

    # Version Changed
    for pid in sorted(old_ids & new_ids):
        v_old = old_packs[pid]["version"]
        v_new = new_packs[pid]["version"]
        if v_old != v_new:
            diff["packs"]["version_changed"].append({
                "id": pid,
                "old": v_old,
                "new": v_new
            })

    # Order Changed
    old_order = [p["id"] for p in old_lock.get("packs", [])]
    new_order = [p["id"] for p in new_lock.get("packs", [])]

    if old_order != new_order:
        diff["packs"]["order_changed"] = {
            "old": old_order,
            "new": new_order
        }

    # 2. Override Changes
    old_overrides = old_lock.get("overrides", {})
    new_overrides = new_lock.get("overrides", {})

    diff["overrides"]["total_delta"] = len(new_overrides) - len(old_overrides)

    old_keys = set(old_overrides.keys())
    new_keys = set(new_overrides.keys())

    diff["overrides"]["added"] = sorted(list(new_keys - old_keys))
    diff["overrides"]["removed"] = sorted(list(old_keys - new_keys))

    for k in sorted(old_keys & new_keys):
        if old_overrides[k] != new_overrides[k]:
            diff["overrides"]["changed"].append({
                "key": k,
                "old": old_overrides[k],
                "new": new_overrides[k]
            })

    # 3. Content File Changes
    old_files = old_lock.get("content_files", {})
    new_files = new_lock.get("content_files", {})

    old_f_keys = set(old_files.keys())
    new_f_keys = set(new_files.keys())

    diff["content_files"]["added"] = sorted(list(new_f_keys - old_f_keys))
    diff["content_files"]["removed"] = sorted(list(old_f_keys - new_f_keys))

    for k in sorted(old_f_keys & new_f_keys):
        if old_files[k] != new_files[k]:
            diff["content_files"]["changed"].append(k)

    return diff
