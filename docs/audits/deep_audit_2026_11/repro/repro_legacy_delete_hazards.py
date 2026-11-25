"""#628 review: A (no-clobber primitives on this OS) + B (deletion hazards) + junction-scene check.

Run with PYTHONPATH=<review worktree>; argv[1] = a scratch dir this script may create folders in (it removes them)."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import engine
import engine.optional_arcade as optional_arcade
from engine.editor.editor_actions import run_editor_action
from engine.editor_controller import EditorModeController
from engine.editor_runtime.editor_input_shortcut_handlers import get_active_shortcut_scopes, handle_editor_action_shortcut

print("engine from", engine.__file__)
base = Path(tempfile.mkdtemp(prefix="r628h_", dir=sys.argv[1]))


def files(root):
    out = {}
    for dp, _dn, fn in os.walk(root):
        for n in fn:
            p = Path(dp, n)
            out[p.relative_to(root).as_posix()] = p.read_bytes()
    return out


# ---------------------------------------------------------------- A: primitives
print("\n== A: no-clobber primitives on", sys.platform)
d = base / "prim"
d.mkdir()
(d / "a.txt").write_bytes(b"A")
(d / "b.txt").write_bytes(b"B")
try:
    os.rename(d / "a.txt", d / "b.txt")
    print("os.rename file onto existing file: SUCCEEDED (clobber!)", (d / "b.txt").read_bytes())
except FileExistsError as e:
    print("os.rename file onto existing file: FileExistsError (no clobber); b.txt =", (d / "b.txt").read_bytes(), "| a.txt exists:", (d / "a.txt").exists())
(d / "hero.png").write_bytes(b"HERO")
os.rename(d / "hero.png", d / "Hero.png")
print("os.rename case-only file hero.png -> Hero.png:", sorted(p for p in os.listdir(d) if p.lower() == "hero.png"), (d / "Hero.png").read_bytes())
(d / "sub").mkdir()
(d / "sub" / "x").write_bytes(b"X")
os.rename(d / "sub", d / "Sub")
print("os.rename case-only dir sub -> Sub:", sorted(p for p in os.listdir(d) if p.lower() == "sub"), files(d / "Sub"))
(d / "other").mkdir()
(d / "other" / "y").write_bytes(b"Y")
try:
    os.rename(d / "Sub", d / "other")
    print("os.rename dir onto existing dir: SUCCEEDED (clobber!)")
except OSError as e:
    print("os.rename dir onto existing dir:", type(e).__name__, "| other =", files(d / "other"))
(d / "empty").mkdir()
try:
    os.rename(d / "Sub", d / "empty")
    print("os.rename dir onto existing EMPTY dir: SUCCEEDED")
except OSError as e:
    print("os.rename dir onto existing EMPTY dir:", type(e).__name__)
try:
    os.link(d / "Hero.png", d / "b.txt")
    print("os.link onto existing: SUCCEEDED (clobber!)")
except FileExistsError:
    print("os.link onto existing file: FileExistsError (no clobber)")


# ---------------------------------------------------------------- real legacy editor
class MockWindow:
    def __init__(self, root):
        self.camera = MagicMock()
        self.camera.position = (0, 0)
        self.scene_controller = MagicMock()
        self.scene_controller._loaded_scene_data = {"entities": {}}
        self.player_hud = MagicMock()
        self._mouse_x = self._mouse_y = 100
        self.width, self.height = 800, 600
        self.repo_root = root

    def screen_to_world(self, x, y):
        return x, y

    def console_log(self, msg):
        pass


def make_editor(name):
    root = base / name / "proj"
    (root / "assets").mkdir(parents=True)
    (root / "scenes").mkdir()
    (root / "assets" / "hero.png").write_bytes(b"HERO-1")
    (root / "assets" / "keep.png").write_bytes(b"KEEP")
    (root / "scenes" / "a.json").write_text(json.dumps({"entities": [{"id": "k", "sprite": "assets/keep.png"}]}), encoding="utf-8")
    EditorModeController.load_workspace = MagicMock()  # (as the repo's editor tests do: no workspace file I/O)
    window = MockWindow(root)
    ed = EditorModeController(window)
    window.editor_controller = ed  # (the real GameWindow carries this; the action registry finds the editor through it)
    ed._repo_root_override = root
    ed.project_explorer.set_repo_root(root)
    ed.active = True
    ed.dock.apply_tab_change(ed, "left", "Project")
    ed.project_explorer.ensure_rows()
    return root, window, ed


def select(ed, rel):
    ed.project_explorer.refresh_tree()
    ed.project_explorer.ensure_rows()
    ok = ed.project_explorer.set_selection_by_path(rel)
    return ok, ed.project_explorer.selected_paths(ed._project_explorer_selectable_rows())


print("\n== B1: deletion entry points (real EditorModeController, real action registry)")
root, window, ed = make_editor("b1key")
print("selection:", select(ed, "assets/hero.png"), "| active scopes:", get_active_shortcut_scopes(ed))
handled = handle_editor_action_shortcut(ed, optional_arcade.arcade.key.DELETE, 0)
plan = ed.file_ops._pending_refactor_plan
print("Del key (Project tab focused): handled =", handled, "| pending plan =", getattr(plan, "op_kind", None),
      "| confirm dialog open =", ed.confirm_modal._on_confirm is not None, "| hero.png still there =", (root / "assets" / "hero.png").exists())
ed.confirm_modal.execute_cancel()

for action_id, label in (("editor.delete", "Edit menu 'Delete' (editor.delete)"),
                         ("editor.project_explorer.delete_selected", "palette 'Project Explorer: Delete Selected'")):
    root, window, ed = make_editor(action_id.replace(".", "_"))
    select(ed, "assets/hero.png")
    before = files(root)
    ran = run_editor_action(action_id, ed, window)
    after = files(root)
    print(f"{label}: ran={ran} | confirm dialog opened = {ed.confirm_modal._on_confirm is not None} | hero.png exists = "
          f"{(root / 'assets' / 'hero.png').exists()} | .mesh_trash exists = {(root / '.mesh_trash').exists()} | "
          f"bytes anywhere = {[k for k, v in after.items() if v == b'HERO-1']} | removed = {sorted(set(before) - set(after))}")

print("\n== B2: repeated safe delete of a re-created file (Del key -> confirm, twice)")
root, window, ed = make_editor("b2trash")
for round_no, payload in ((1, b"HERO-1"), (2, b"HERO-2")):
    (root / "assets" / "hero.png").write_bytes(payload)
    select(ed, "assets/hero.png")
    handle_editor_action_shortcut(ed, optional_arcade.arcade.key.DELETE, 0)
    op_id = getattr(ed.file_ops._pending_refactor_plan, "op_id", None)
    ed.confirm_modal.execute_confirm()
    trash = {k: v for k, v in files(root).items() if k.startswith(".mesh_trash/")}
    print(f"round {round_no}: op_id={op_id} | hero.png exists={(root / 'assets' / 'hero.png').exists()} | trash={trash}")
print("HERO-1 bytes survive anywhere:", any(v == b"HERO-1" for v in files(root).values()))

print("\n== junction-reached scene JSON (O8 reachability)")
root, window, ed = make_editor("junction_scene")
ext = base / "junction_scene" / "outside_scenes"
ext.mkdir()
(ext / "ext.json").write_text(json.dumps({"entities": [{"id": "h", "sprite": "assets/hero.png"}]}), encoding="utf-8")
try:
    import _winapi
    _winapi.CreateJunction(str(ext), str(root / "scenes" / "ext"))
    print("list_repo_json_assets sees:", ed.file_ops.list_repo_json_assets())
    select(ed, "assets/hero.png")
    before = files(ext)
    req = ed.file_ops.request_safe_rename_refactor("hero2.png")
    if req:
        ed.confirm_modal.execute_confirm()
    print("rename with a junction-reached scene referencing it: request =", req, "| outside scene changed =", files(ext) != before)
except Exception as e:
    print("junction check skipped:", type(e).__name__, e)

shutil.rmtree(base, ignore_errors=True)
print("\nremoved", base, "exists:", base.exists())
