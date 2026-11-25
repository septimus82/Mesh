"""Repro: legacy editor V2 'safe rename' (inline rename -> request_safe_rename_refactor -> confirm) silently
overwrites an existing file with the renamed one, and rewrites references to point at it.

Entry point: engine.editor.asset_ops.editor_file_ops_controller.EditorFileOpsController, the controller the legacy
editor's Project Explorer inline rename commits through (project_explorer_actions._inline_rename_commit).
Run: py -3.13 repro_legacy_rename_overwrite.py   (PYTHONPATH=D:\\Games\\Mesh-audit)
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import engine
from engine.editor.asset_ops.editor_file_ops_controller import EditorFileOpsController

print("engine from", engine.__file__)
root = Path(tempfile.mkdtemp(prefix="mesh_audit_rename_"))
try:
    (root / "assets").mkdir()
    (root / "assets" / "hero.png").write_bytes(b"HERO-BYTES")
    (root / "assets" / "villain.png").write_bytes(b"VILLAIN-BYTES")  # an unrelated, existing asset
    (root / "scenes").mkdir()
    (root / "scenes" / "a.json").write_text(json.dumps({"entities": [
        {"id": "e1", "sprite": "assets/hero.png"}, {"id": "e2", "sprite": "assets/villain.png"}]}))

    confirms = []
    row = SimpleNamespace(entry=SimpleNamespace(path=str(root / "assets" / "hero.png"), rel_path="assets/hero.png", is_dir=False))
    controller = SimpleNamespace(
        window=SimpleNamespace(repo_root=root, scene_controller=None),
        project_explorer=SimpleNamespace(get_selected_row=lambda: row, refresh_tree=lambda: None,
                                         set_selection_by_path=lambda p: None),
        confirm_modal=SimpleNamespace(request_confirmation=lambda **kw: confirms.append(kw), close=lambda: None),
        _push_command=lambda cmd: None,
    )
    ops = EditorFileOpsController(controller)
    assert ops.request_safe_rename_refactor("villain.png") is True, "rename request was refused (good) -> not reproduced"
    print("confirmation dialog lines:", confirms[0]["message_lines"])
    confirms[0]["on_confirm"]()  # the person presses Confirm

    villain = (root / "assets" / "villain.png").read_bytes()
    scene = json.loads((root / "scenes" / "a.json").read_text())
    print("villain.png now holds:", villain)
    print("scene sprites:", [e["sprite"] for e in scene["entities"]])
    print("hero.png exists:", (root / "assets" / "hero.png").exists())
    lost = villain != b"VILLAIN-BYTES"
    print("DEFECT REPRODUCED: existing villain.png overwritten (irreversible)" if lost else "not reproduced")
    sys.exit(1 if lost else 0)
finally:
    shutil.rmtree(root, ignore_errors=True)  # (the temp folder this script created)
