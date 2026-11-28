"""S1-0 evidence for #618 (fixed by #628): the legacy editor's safe rename never overwrites, also when the destination
appears AFTER the plan was confirmed-for (between the dialog opening and the person pressing Confirm).

Drives EditorFileOpsController.request_safe_rename_refactor -> confirmation -> on_confirm, as the triage repro did,
with a file created at the destination before Confirm. Exit 1 if either file's original bytes are lost.
Run: PYTHONPATH=<checkout> py -3.13 docs/s1/evidence/verify_618_rename_toctou.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from engine.editor.asset_ops.editor_file_ops_controller import EditorFileOpsController

root = Path(tempfile.mkdtemp(prefix="mesh_s1_618_"))
try:
    (root / "assets").mkdir()
    (root / "assets" / "hero.png").write_bytes(b"HERO-BYTES")
    (root / "scenes").mkdir()
    (root / "scenes" / "a.json").write_text(json.dumps({"entities": [{"id": "e1", "sprite": "assets/hero.png"}]}))
    confirms: list[dict] = []
    row = SimpleNamespace(entry=SimpleNamespace(path=str(root / "assets" / "hero.png"), rel_path="assets/hero.png",
                                                is_dir=False))
    controller = SimpleNamespace(
        window=SimpleNamespace(repo_root=root, scene_controller=None),
        project_explorer=SimpleNamespace(get_selected_row=lambda: row, refresh_tree=lambda: None,
                                         set_selection_by_path=lambda p: None),
        confirm_modal=SimpleNamespace(request_confirmation=lambda **kw: confirms.append(kw), close=lambda: None),
        _push_command=lambda cmd: None,
    )
    ops = EditorFileOpsController(controller)
    print("rename request accepted (destination free):", ops.request_safe_rename_refactor("villain.png"))
    (root / "assets" / "villain.png").write_bytes(b"VILLAIN-BYTES")  # appears while the dialog is open
    try:
        confirms[0]["on_confirm"]()
        print("confirm returned normally")
    except Exception as exc:  # noqa: BLE001
        print("confirm raised:", type(exc).__name__, exc)
    hero = (root / "assets" / "hero.png")
    villain = (root / "assets" / "villain.png").read_bytes()
    scene = json.loads((root / "scenes" / "a.json").read_text())
    print("hero.png:", hero.read_bytes() if hero.exists() else "MISSING", "| villain.png:", villain,
          "| scene sprite:", scene["entities"][0]["sprite"])
    lost = villain != b"VILLAIN-BYTES" or not hero.exists() or hero.read_bytes() != b"HERO-BYTES"
    partial = scene["entities"][0]["sprite"] != "assets/hero.png"
    print("DEFECT: a file was lost" if lost else "no file lost",
          "| references rewritten without the move" if partial and not lost else "")
    sys.exit(1 if lost or partial else 0)
finally:
    shutil.rmtree(root, ignore_errors=True)  # (the temp folder this script created)
