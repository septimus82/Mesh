"""S1v: create every template via `mesh new` and the launcher/Studio create_project, then scan statically.

usage: py -3.13 s1v_make.py BASE
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

BASE = Path(sys.argv[1])
import engine  # noqa: E402

print("engine from", engine.__file__)
from engine.project_templates import list_templates  # noqa: E402
from engine.project_scaffold import create_project  # noqa: E402
from mesh_cli.main import main as mesh  # noqa: E402

GATE_KEYS = ("require_flags", "forbid_flags")


def scan(root: Path) -> dict:
    out = {"items.json": (root / "assets/data/items.json").is_file(), "health": [], "vendor": [], "entity_gates": [],
           "cond_act": [], "item_users": [], "combat": []}
    files = [p for p in root.rglob("*.json") if "dist" not in p.parts]
    for path in files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        ents = []
        if isinstance(doc, dict) and isinstance(doc.get("entities"), list):
            ents = doc["entities"]
        elif isinstance(doc, list):  # prefabs.json
            ents = [p.get("entity") for p in doc if isinstance(p, dict) and isinstance(p.get("entity"), dict)]
        rel = path.relative_to(root).as_posix()
        for e in ents:
            if not isinstance(e, dict):
                continue
            names = [b if isinstance(b, str) else (b or {}).get("type") for b in e.get("behaviours") or []]
            cfg = e.get("behaviour_config") or {}
            who = f"{rel}:{e.get('name') or e.get('id')}"
            if "Health" in names:
                out["health"].append((who, e.get("tag"), cfg.get("Health")))
            if "Combat" in names:
                out["combat"].append((who, cfg.get("Combat")))
            if "Vendor" in names:
                out["vendor"].append((who, names))
            if any(k in e for k in GATE_KEYS):
                out["entity_gates"].append((who, {k: e.get(k) for k in GATE_KEYS if k in e}))
            if "ConditionalActivator" in names:
                out["cond_act"].append(who)
            for b in ("PickupCollectible", "DropTable", "RewardChest", "InventoryHolder"):
                if b in names:
                    out["item_users"].append((who, b, cfg.get(b)))
    return out


def tree(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


for t in list_templates():
    quiet = io.StringIO()
    with contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
        code = mesh(["new", f"n_{t.id}", "--template", t.id, "--dest", str(BASE)])
    n_root = BASE / f"n_{t.id}"
    res = {"mesh_new_exit": code, **scan(n_root)}
    if t.launcher:
        s_root = BASE / f"s_{t.id}"
        create_project(s_root, f"s_{t.id}", template_id=t.id)
        same = tree(s_root) == tree(n_root)
        res["studio_create_same_files"] = same
        res["studio_items.json"] = (s_root / "assets/data/items.json").is_file()
    print(f"\n=== {t.id} launcher={t.launcher}")
    for k, v in res.items():
        print(f"  {k}: {v}")
