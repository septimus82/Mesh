"""Check: a non-exported game's SaveManager keeps saves in "saves" relative to the process CWD, not the project the
window loaded (engine.save_runtime.storage.resolve -> Path(DEFAULT_SAVE_DIR)). Paths that change the project without
chdir (legacy main-menu project switch: ui_overlays/main_menu_overlay._apply_project_root; public_api.run_game(
project_root=...)) therefore write project B's quicksave into project A's (or any CWD's) saves folder, where a
same-named slot of A is overwritten (a same-version save gets no backup).
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import engine
from engine.save_manager import SaveManager

print("engine from", engine.__file__)
base = Path(tempfile.mkdtemp(prefix="mesh_audit_cwd_"))
prev = os.getcwd()
try:
    a, b = base / "project_a", base / "project_b"
    a.mkdir(), b.mkdir()
    os.chdir(a)  # e.g. `mesh edit project_a` (game_launch chdirs), then the legacy main menu switches to project_b
    window = SimpleNamespace(engine_config=SimpleNamespace(_config_base_dir=str(b), game_id="b-1234", title="B",
                                                           start_scene="s.json", world_file=None))
    manager = SaveManager(window)
    resolved = (Path.cwd() / manager.save_dir).resolve()
    print("project B's quicksave would be written to:", resolved / "quicksave.json")
    wrong = resolved.parent != b.resolve()
    print("saves follow the CWD, not the project" if wrong else "saves follow the project")
    sys.exit(1 if wrong else 0)
finally:
    os.chdir(prev)
    shutil.rmtree(base, ignore_errors=True)  # (the temp folders this script created)
