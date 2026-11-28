"""S1-0 part B: the legacy editor's file operations resolve paths against the CWD, not the project the editor shows.

Every legacy file operation reads ``window.repo_root`` (engine/editor/asset_ops/editor_file_ops_controller.py), an
attribute the real GameWindow never has (contract_gaps_real_window.py lists it). The tests give their fake window a
``repo_root`` (SimpleNamespace(repo_root=...)), so they pass. In the real window:

* the "safe" refactor operations (request_safe_delete_refactor / _rename_ / _move_, the V2 path with the reference
  scan and trash) return False at ``if not repo_root: return False`` and do nothing, silently;
* the plain ones (delete_selected_paths: Edit > Delete with the Project tab focused; rename_selected_asset; move)
  fall back to ``Path(... or ".")``: the CURRENT WORKING DIRECTORY. The Project Explorer lists the project root
  (editor._get_repo_root() -> get_repo_root(), which follows MESH_REPO_ROOT / a main-menu project switch).

So when the CWD is not the project (main-menu "Open project", public_api.run_game(project_root=...), the #623
situations), Delete unlinks the same relative path under the CWD: another project's or the engine checkout's file.

Repro (real hidden GameWindow and EditorModeController; two throwaway folders under one temp dir):
  launch/  stands in for the folder Mesh was started from (the CWD)    assets/sprites/hero.png = b"LAUNCH-FOLDER"
  project/ the project the editor shows (its explorer root)            assets/sprites/hero.png = b"PROJECT"
The process chdirs into launch/ only for the file-op calls and back afterwards; nothing outside the temp dir is touched.

Exits 1 when the delete hits the launch folder's file (or the safe ops silently refuse).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _hidden_game import HERO, REPO, hidden_game, scene  # noqa: E402

REL = "assets/sprites/hero.png"
defects = []

with hidden_game({"Yard": scene("Yard", HERO)}) as (window, _paths, tmp):
    launch, project = tmp / "launch", tmp / "project"
    for root, data in ((launch, b"LAUNCH-FOLDER"), (project, b"PROJECT")):
        (root / "assets" / "sprites").mkdir(parents=True)
        (root / REL).write_bytes(data)

    editor = window.editor_controller
    editor._repo_root_override = project  # what MESH_REPO_ROOT / a main-menu project switch gives the explorer
    file_ops = editor._file_ops_ctl
    print("window has repo_root:", hasattr(window, "repo_root"))
    print("explorer / editor root:", Path(editor._get_repo_root()).relative_to(tmp).as_posix())

    os.chdir(launch)
    try:
        safe_delete = file_ops.request_safe_delete_refactor([REL])
        safe_rename = file_ops.request_safe_rename_refactor("villain.png")
        safe_move = file_ops.request_safe_move_refactor("assets/other")
        print(f"safe delete/rename/move returned: {safe_delete} / {safe_rename} / {safe_move} "
              f"| both files intact: {(launch / REL).exists() and (project / REL).exists()}")
        if not (safe_delete or safe_rename or safe_move):
            defects.append("the safe (V2) refactor operations silently do nothing in the real window")

        deleted = file_ops.delete_selected_paths([REL])
    finally:
        os.chdir(REPO)

    launch_left = (launch / REL).exists()
    project_left = (project / REL).exists()
    print(f"plain delete returned: {deleted} | launch-folder hero.png exists: {launch_left} "
          f"| project hero.png exists: {project_left}")
    if not launch_left and project_left:
        defects.append("Delete unlinked the CWD's file, not the project file the explorer showed")

if defects:
    print("DEFECT REPRODUCED:", "; ".join(defects))
    sys.exit(1)
print("not reproduced")
