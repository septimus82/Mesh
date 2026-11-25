"""Controller for safe file operations (rename, move, etc)."""
from __future__ import annotations

import errno
import hashlib
import json
import os
import posixpath
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from engine.editor.project_explorer.project_explorer_inline_rename_model import INVALID_FILENAME_CHARS
from engine.editor.project_explorer_power_tools_model import (
    compute_common_parent,
    format_paths_for_clipboard,
)
from engine.editor.project_explorer_reveal_model import format_copy_path_text
from engine.hd2d.glb import contained
from engine.swallowed_exceptions import _log_swallow

from .asset_move_model import (
    compute_move_paths,
    format_move_undo_label,
    validate_destination,
)
from .asset_refactor_model import (
    Replacement,
    apply_replacements,
    compute_move_mapping,
    compute_rename_mapping,
    compute_replacements,
    normalize_repo_rel,
    scan_prefab_references,
    scan_scene_references,
)
from .asset_refactor_preview_model import format_refactor_preview
from .asset_rename_model import (
    Replacement as RenameReplacement,
)
from .asset_rename_model import (
    apply_reference_replacements,
    compute_reference_replacements,
    compute_rename_paths,
    format_rename_undo_label,
)

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController


@dataclass
class FsStep:
    src_rel: str
    dst_rel: Optional[str]  # None for delete
    kind: str  # 'move', 'delete'

@dataclass
class PendingRefactorPlan:
    """Holds state for a requested refactor that awaits user confirmation."""
    op_kind: str  # 'rename', 'move', 'delete'
    op_id: str
    fs_steps: List[FsStep]
    json_updates: Dict[str, List[Replacement]]
    preview_lines: List[str]
    trash_moves: List[Tuple[str, str]]
    # State to restore/update after success
    active_scene_update: Optional[Dict[str, Any]] = None
    undo_command: Optional[Dict[str, Any]] = None
    selection_restore: Optional[List[str]] = None


class EditorFileOpsController:
    """Manages file system operations with safety checks and reference updating."""

    def __init__(self, controller: EditorModeController) -> None:
        self.controller = controller
        # V2 Refactor: Staged plan waiting for confirmation
        self._pending_refactor_plan: Optional[PendingRefactorPlan] = None

    def _build_refactor_signature(
        self,
        op_kind: str,
        fs_steps: List[FsStep],
        json_updates: Dict[str, List[Replacement]],
    ) -> Dict[str, Any]:
        fs_sig = [
            {"src": step.src_rel, "dst": step.dst_rel or "", "kind": step.kind}
            for step in fs_steps
        ]
        fs_sig.sort(key=lambda s: (s["kind"], s["src"], s["dst"]))

        json_sig: Dict[str, List[Tuple[str, str, str, str, str]]] = {}
        for path in sorted(json_updates.keys()):
            repls = json_updates[path]
            repl_items = [
                (
                    r.entity_id or "",
                    r.field_path or "",
                    r.old_value or "",
                    r.new_value or "",
                    r.order_key or "",
                )
                for r in repls
            ]
            repl_items.sort()
            json_sig[path] = repl_items

        return {"op_kind": op_kind, "fs_steps": fs_sig, "json_updates": json_sig}

    def _compute_refactor_op_id(
        self,
        op_kind: str,
        fs_steps: List[FsStep],
        json_updates: Dict[str, List[Replacement]],
    ) -> str:
        signature = self._build_refactor_signature(op_kind, fs_steps, json_updates)
        payload = json.dumps(signature, sort_keys=True, separators=(",", ":"))
        return hashlib.md5(payload.encode("utf-8")).hexdigest()[:12]

    def _trash_root(self, repo_root: Path, op_id: str) -> Path:
        return repo_root / ".mesh_trash" / op_id

    def _build_trash_moves(
        self, repo_root: Path, fs_steps: List[FsStep], op_id: str
    ) -> List[Tuple[str, str]]:
        moves: List[Tuple[str, str]] = []
        trash_root = self._trash_root(repo_root, op_id)
        for step in fs_steps:
            if step.kind != "delete":
                continue
            src = repo_root / step.src_rel
            dst = trash_root / step.src_rel
            moves.append((str(src), str(dst)))
        return moves

    def _stage_deletes_to_trash(self, plan: PendingRefactorPlan, repo_root: Path) -> List[Tuple[str, str]]:
        staged: List[Tuple[str, str]] = []
        for src_str, dst_str in plan.trash_moves:
            src = Path(src_str)
            dst = Path(dst_str)
            if not src.exists():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                try:
                    os.replace(src, dst)
                except Exception:
                    _log_swallow("EFOC-001", "blanket exception fallback", once=False)
                    shutil.move(str(src), str(dst))
                staged.append((src_str, dst_str))
            except Exception:
                _log_swallow("EFOC-002", "blanket exception fallback", once=False)
                # Roll back any staged moves before bubbling up
                self._restore_deletes_from_trash(staged)
                raise
        return staged

    def _restore_deletes_from_trash(self, staged: List[Tuple[str, str]]) -> None:
        for src_str, dst_str in reversed(staged):
            src = Path(src_str)
            dst = Path(dst_str)
            if not dst.exists():
                continue
            src.parent.mkdir(parents=True, exist_ok=True)
            try:
                try:
                    os.replace(dst, src)
                except Exception:
                    _log_swallow("EFOC-003", "blanket exception fallback", once=False)
                    shutil.move(str(dst), str(src))
            except Exception as e:
                _log_swallow("EFOC-004", "blanket exception fallback", once=False)
                print(f"CRITICAL: Failed to restore {dst} -> {src}: {e}")

    def _project_root(self) -> Optional[Path]:
        """The folder file operations act in: the project the Project panel shows (#641). None, after an error toast,
        when there isn't one, or when the panel still lists another folder than the open project (a main-menu project
        switch doesn't rescan it), since its paths would then name another project's files. Never the current
        folder: a relative path resolved against it deleted or renamed whatever file had that name there."""
        root = Path(self.controller._get_repo_root())
        shown = Path(self.controller.project_explorer.repo_root)
        if not root.is_dir():
            why = f"the project folder {root} isn't there"
        elif root.resolve() != shown.resolve():
            why = f"the Project panel shows {shown}, not the open project {root}; reopen the project"
        else:
            return shown
        self._refuse("File operation refused", f"{why}. Nothing was changed.")
        return None

    def purge_trash(self, op_id: str) -> None:
        repo_root = self._project_root()
        if repo_root is None:
            return
        trash_root = self._trash_root(repo_root, op_id)
        if trash_root.exists():
            shutil.rmtree(trash_root, ignore_errors=True)

    def _plan_refusal(self, repo_root: Path, fs_steps: List[FsStep], json_paths: List[str]) -> Optional[str]:
        """Why this plan can't run without destroying or escaping anything, or None (#618).

        The whole plan is checked before any of it runs: every move's source exists and its destination is a plain
        project path that doesn't exist yet (a case-only rename of the same file excepted), is no other step's
        destination and isn't inside the folder being moved; every file touched, links and junctions followed, is
        inside the project; nothing deleted is a folder (its references would be rewritten wrongly and a move to the
        trash can stop half-way). ``os.replace`` overwrites silently, so this is what stands between a rename and a
        lost file."""
        root = Path(repo_root)
        claimed: set[str] = set()
        for step in fs_steps:
            if not contained(root, step.src_rel):
                return f"{step.src_rel} is not a path inside the project."
            if step.kind == "delete" and os.path.isdir(root / step.src_rel):
                # The whole selection is refused, never part of it: a half-done delete is worse than none (#668).
                return f"{step.src_rel} is a folder. Deleting folders isn't supported here; delete the files inside, or use Studio."
            if step.kind != "move" or not step.dst_rel:
                continue
            src, dst = root / step.src_rel, root / step.dst_rel
            if not os.path.lexists(src):
                return f"{step.src_rel} no longer exists."
            why = rel_refusal(step.dst_rel)
            if why:
                return f"Can't use {step.dst_rel}: {why}"
            if not contained(root, step.dst_rel):
                return f"{step.dst_rel} is outside the project."
            if f"{step.dst_rel}/".startswith(f"{step.src_rel}/"):
                return f"{step.src_rel} can't be moved inside itself."
            if any(f"{step.src_rel}/".startswith(f"{other.src_rel}/") for other in fs_steps if other is not step):
                return f"{step.src_rel} is inside another item being moved; move one or the other."
            case_only = step.src_rel.casefold() == step.dst_rel.casefold()
            if os.path.lexists(dst) and not (case_only and _same_file(src, dst)):
                return f"{step.dst_rel} already exists. Rename or move it first; nothing was changed."
            key = os.path.normcase(step.dst_rel)
            if key in claimed:
                return f"Two items would both become {step.dst_rel}; nothing was changed."
            claimed.add(key)
        for path_rel in json_paths:
            if not contained(root, path_rel):
                return f"{path_rel} is not a file inside the project."
        return None

    def _refuse(self, title: str, reason: str) -> None:
        print(f"[Refactor] {title}: {reason}")
        self._toast(f"{title}: {reason}", severity="error", seconds=6.0)

    def execute_pending_refactor(self) -> None:
        """
        Execute the staged refactor plan with rollback support.
        Strategy:
        1. Read original content of all affected JSON files.
        2. Apply JSON updates (change references to new paths).
        3. Perform Filesystem operations (Move/Rename/Delete).
        
        If (2) fails: Restore original JSONs.
        If (3) fails: Rollback completed FS steps, then restore original JSONs.
        """
        plan = self._pending_refactor_plan
        if not plan:
            return

        if self._is_web_runtime():
            self._toast(f"Refactor '{plan.op_kind}' simulated (Web Preview).")
            self._pending_refactor_plan = None
            return

        repo_root = self._project_root()
        if repo_root is None:
            self._pending_refactor_plan = None
            return

        # 0. Re-check the whole plan against the disk as it is now (it may have changed while the dialog was open):
        # refused before anything is written, so nothing needs rolling back (#618).
        refusal = self._plan_refusal(repo_root, plan.fs_steps, list(plan.json_updates))
        if refusal:
            self._refuse(f"{plan.op_kind.capitalize()} refused", refusal)
            self._pending_refactor_plan = None
            return

        print(f"[Refactor] Executing {plan.op_kind}...")

        # 1. Read Originals (Snapshot)
        original_json_contents: Dict[str, str] = {}
        try:
            for path_rel in plan.json_updates:
                abs_path = repo_root / path_rel
                if abs_path.exists():
                    original_json_contents[path_rel] = abs_path.read_text(encoding="utf-8")
        except Exception as e:
            _log_swallow("EFOC-005", "blanket exception fallback", once=False)
            self._show_error_modal("Refactor Preparation Failed", f"Could not read original files: {e}")
            self._pending_refactor_plan = None
            return

        from engine.editor.persistence_utils import write_atomic_utf8

        staged_trash_moves: List[Tuple[str, str]] = []
        # 2. Stage deletes to trash (reversible) before JSON writes
        if plan.trash_moves:
            try:
                staged_trash_moves = self._stage_deletes_to_trash(plan, repo_root)
            except Exception as e:
                _log_swallow("EFOC-006", "blanket exception fallback", once=False)
                # Best-effort restore any staged moves
                try:
                    self._restore_deletes_from_trash(staged_trash_moves)
                except Exception:
                    _log_swallow("EFOC-007", "blanket exception fallback", once=False)
                    pass
                self._show_error_modal("Refactor Staging Failed", f"Could not stage deletes: {e}")
                self._pending_refactor_plan = None
                return

        # 3. Apply JSON Updates
        # We execute this BEFORE FS moves, so paths in 'plan.json_updates' are valid.
        written_jsons: List[str] = []
        try:
            for path_rel, replacements in plan.json_updates.items():
                abs_path = repo_root / path_rel
                if not abs_path.exists():
                    continue

                # Load, Apply, Write
                # We rely on 'replacements' being calculated correctly.
                # However, we need to load the json to apply replacements unless we passed the raw new content.
                # Ideally we load 'original_json_contents[path_rel]'
                content_str = original_json_contents[path_rel]
                data = json.loads(content_str)

                # Apply replacements
                # We need 'apply_replacements' from model which takes (data, replacements)
                # But 'modifications' only has replacements.
                new_data = apply_replacements(data, replacements)

                write_atomic_utf8(abs_path, json.dumps(new_data, indent=2))
                written_jsons.append(path_rel)

        except Exception as e:
            _log_swallow("EFOC-008", "blanket exception fallback", once=False)
            print(f"[Refactor] JSON Write Error: {e}. Rolling back...")
            # Restore staged deletes if any
            if staged_trash_moves:
                try:
                    self._restore_deletes_from_trash(staged_trash_moves)
                except Exception:
                    _log_swallow("EFOC-009", "blanket exception fallback", once=False)
                    print("CRITICAL: Failed to restore staged deletes.")
            self._restore_jsons(written_jsons, original_json_contents, repo_root)
            self._show_error_modal("Refactor Aborted", f"Reference update failed: {e}\nFiles restored.")
            self._pending_refactor_plan = None
            return

        # 4. Execute FS Steps (moves only; deletes are staged to trash)
        completed_fs_steps: List[FsStep] = []
        fs_error = None

        for step in plan.fs_steps:
            src = repo_root / step.src_rel
            try:
                if step.kind == "move":
                    if step.dst_rel:
                        dst = repo_root / step.dst_rel
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        _move_no_clobber(src, dst)  # (never over a file that appeared since the check: #618)

                completed_fs_steps.append(step)

            except Exception as e:
                _log_swallow("EFOC-010", "blanket exception fallback", once=False)
                if step.dst_rel and _interrupted_link(repo_root, step):
                    completed_fs_steps.append(step)  # (both names left by a link+unlink cut short: undone below)
                fs_error = e
                break

        if fs_error:
            print(f"[Refactor] FS Error: {fs_error}. Rolling back...")
            # Rollback FS
            self._rollback_fs(completed_fs_steps, repo_root)
            # Restore staged deletes if any
            if staged_trash_moves:
                try:
                    self._restore_deletes_from_trash(staged_trash_moves)
                except Exception:
                    _log_swallow("EFOC-011", "blanket exception fallback", once=False)
                    print("CRITICAL: Failed to restore staged deletes.")
            # Rollback JSONs
            self._restore_jsons(written_jsons, original_json_contents, repo_root)

            self._show_error_modal("File System Error", f"Operation failed: {fs_error}\nChanges reverted.")
            self._pending_refactor_plan = None
            return

        # 5. Success - Update State
        if plan.active_scene_update:
            self._set_current_scene_payload(plan.active_scene_update)

        if plan.undo_command and hasattr(self.controller, "_push_command"):
            self.controller._push_command(plan.undo_command)

        self._refresh_project_tree()

        if plan.selection_restore:
            project = getattr(self.controller, "project_explorer", None)
            if project is not None:
                try:
                    if hasattr(project, "ensure_rows"):
                        project.ensure_rows()

                    restored_paths = [p for p in plan.selection_restore if isinstance(p, str) and p]
                    if not restored_paths:
                        restored_paths = []

                    old_paths: list[str] = []
                    primary_old: str | None = None
                    undo = plan.undo_command if isinstance(plan.undo_command, dict) else {}

                    if plan.op_kind == "rename":
                        old_path = undo.get("old_path")
                        if isinstance(old_path, str) and old_path:
                            old_paths = [old_path]
                            primary_old = old_path
                    elif plan.op_kind == "move":
                        moves = undo.get("moves")
                        if isinstance(moves, list):
                            old_paths = [
                                str(m.get("old_path"))
                                for m in moves
                                if isinstance(m, dict) and isinstance(m.get("old_path"), str)
                            ]
                            if old_paths:
                                primary_old = old_paths[0]

                    if restored_paths:
                        if hasattr(project, "apply_post_move_selection") and old_paths:
                            project.apply_post_move_selection(old_paths, restored_paths, primary_old)
                        else:
                            project.set_selection_by_path(restored_paths[0])
                            if hasattr(project, "_toggle_selection_by_path"):
                                for extra in restored_paths[1:]:
                                    project._toggle_selection_by_path(extra)
                except Exception:
                    _log_swallow("EFOC-012", "blanket exception fallback", once=False)
                    pass
        self._toast(f"Refactor '{plan.op_kind}' complete.")
        self._pending_refactor_plan = None

    def _restore_jsons(self, written: List[str], originals: Dict[str, str], repo_root: Path) -> None:
        from engine.editor.persistence_utils import write_atomic_utf8
        for path_rel in written:
            if path_rel in originals:
                try:
                    write_atomic_utf8(repo_root / path_rel, originals[path_rel])
                except Exception:
                    _log_swallow("EFOC-013", "blanket exception fallback", once=False)
                    print(f"CRITICAL: Failed to restore {path_rel}")

    def _rollback_fs(self, steps: List[FsStep], repo_root: Path) -> None:
        # Reverse order
        for step in reversed(steps):
            try:
                if step.kind == "move" and step.dst_rel:
                    # Move back: dst -> src
                    src = repo_root / step.src_rel
                    dst = repo_root / step.dst_rel
                    if _interrupted_link(repo_root, step):
                        os.unlink(dst)  # (the source never left: drop the extra name the cut-short move made)
                    elif os.path.lexists(dst):
                        _move_no_clobber(dst, src)  # (never over a file made at the old path meanwhile)
            except Exception as e:
                _log_swallow("EFOC-014", "blanket exception fallback", once=False)
                print(f"Rollback failed for {step}: {e}")

    def _show_error_modal(self, title: str, message: str) -> None:
        # Shown as an error toast: a dialog opened here, during Confirm, was closed at once by
        # confirm_pending_refactor / execute_confirm, so nobody ever saw why the refactor failed (#618).
        self._refuse(title, " ".join(message.split("\n")))

    def confirm_pending_refactor(self) -> None:
        self.execute_pending_refactor()
        self.controller.confirm_modal.close()

    def cancel_pending_refactor(self) -> None:
        print("[Refactor] Cancelled by user.")
        self._pending_refactor_plan = None
        self.controller.confirm_modal.close()

    def can_safe_move_selected_assets_folder(self) -> bool:
        """Check if current selection is a moveable folder."""
        row = self._get_selected_project_row()
        if not row:
            return False
        entry = getattr(row, "entry", None)
        if entry is None:
            return False

        # Check if it's a directory and inside assets
        is_dir = getattr(entry, "is_dir", False)
        if not is_dir:
            return False

        # Optional: Limit scope to within 'worlds', 'scenes', 'prefabs' etc?
        # For now, allow any folder in repo
        return True

    def list_repo_json_assets(self, repo_root: Optional[Path] = None) -> List[str]:
        """Deterministic list of candidate files to scan (scenes/prefabs)."""
        repo_root = repo_root or self._project_root()
        if repo_root is None:
            return []

        candidates = []
        # Exclude patterns
        exclude_dirs = {
            "__pycache__", ".git", ".pytest_cache", "build", "dist",
            "node_modules", "venv", ".vscode"
        }

        # DEBUG
        # print(f"DEBUG: Scanning {repo_root} for JSONs...")

        for dirpath, dirnames, filenames in os.walk(repo_root):
            # Prune exclusions in-place
            dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
            dirnames.sort() # Deterministic walk order
            filenames.sort()

            for fname in filenames:
                if fname.lower().endswith(".json"):
                    # Check if it looks like a scene or prefab?
                    # For now, verify later during load.
                    full_path = Path(dirpath) / fname
                    rel_path = full_path.relative_to(repo_root).as_posix()
                    candidates.append(rel_path)

        return sorted(candidates)

    def rename_selected_asset(self, new_name: str) -> bool:
        """Rename the selected Project Explorer asset and update scene references.

        This performs a "safe rename" - updating all references to the asset
        in the currently loaded scene. On native runtime, also renames the file.
        On web runtime, only updates references (preview mode).

        Args:
            new_name: The new filename (without directory).

        Returns:
            True if rename was successful, False otherwise.
        """
        row = self._get_selected_project_row()
        if not row:
            return False

        entry = getattr(row, "entry", None)
        if entry is None:
            self._toast("Cannot rename: not a file entry", severity="warning")
            return False

        if getattr(entry, "is_dir", False):
            self._toast("Cannot rename folders", severity="warning")
            return False

        old_path = getattr(entry, "rel_path", None)
        if not old_path:
            return False

        # Compute paths
        old_rel, new_rel = compute_rename_paths(old_path, new_name.strip())
        if not new_rel:
            return False

        if old_rel == new_rel:
            return True

        # Get scene payload
        scene = self._get_current_scene_payload()

        # Compute replacements
        replacements = compute_reference_replacements(scene, old_rel, new_rel)

        # Detect if web runtime
        is_web = self._is_web_runtime()

        # Attempt filesystem rename on native runtime
        if not is_web:
            repo = self._project_root()
            if repo is None:
                return False
            if not self._perform_fs_rename(repo, old_rel, new_rel):  # (no reference changes for a file not renamed: #618)
                self._refuse("Rename failed", f"{old_rel} couldn't be renamed to {new_rel}; nothing was changed.")
                return False

        # Apply reference replacements to scene
        if replacements:
            new_scene = apply_reference_replacements(scene, replacements)
            self._set_current_scene_payload(new_scene)

            # Push undo entry
            undo_label = format_rename_undo_label(old_rel, new_rel, len(replacements))
            self.controller._push_command({
                "type": "safe_rename",
                "label": undo_label,
                "old_path": old_rel,
                "new_path": new_rel,
                "replacements": [
                    {
                        "entity_id": r.entity_id,
                        "field_path": r.field_path,
                        "old_value": r.old_value,
                        "new_value": r.new_value,
                    }
                    for r in replacements
                ],
            })

        # Refresh project tree
        self._refresh_project_tree()

        # Show toast
        n_refs = len(replacements)
        if is_web:
            self._toast(f"Preview: {n_refs} ref(s) updated (no FS write)")
        else:
            if n_refs > 0:
                self._toast(f"Renamed + {n_refs} ref(s) updated")
            else:
                self._toast("Renamed file")

        return True

    def move_selected_asset(self, dest_folder_rel: str) -> bool:
        """Move the selected Project Explorer asset and update scene references.

        Args:
            dest_folder_rel: Destination folder relative path.

        Returns:
            True if move was successful, False otherwise.
        """
        row = self._get_selected_project_row()
        if not row:
            return False

        entry = getattr(row, "entry", None)
        if entry is None:
            self._toast("Cannot move: not a file entry", severity="warning")
            return False

        if getattr(entry, "is_dir", False):
            self._toast("Cannot move folders", severity="warning")
            return False

        old_path = getattr(entry, "rel_path", None)
        if not old_path:
            return False

        # Validate
        is_valid, reason = validate_destination(old_path, dest_folder_rel)
        if not is_valid:
            self._toast(f"Cannot move: {reason}", severity="warning")
            return False

        # Compute paths
        old_rel, new_rel = compute_move_paths(old_path, dest_folder_rel)
        if not new_rel or old_rel == new_rel:
            return False

        scene = self._get_current_scene_payload()
        replacements = compute_reference_replacements(scene, old_rel, new_rel)
        is_web = self._is_web_runtime()

        if not is_web:
            repo = self._project_root()
            if repo is None or not self._perform_fs_rename(repo, old_rel, new_rel):
                return False  # Abort on move failure usually

        if replacements:
            new_scene = apply_reference_replacements(scene, replacements)
            self._set_current_scene_payload(new_scene)

            undo_label = format_move_undo_label(old_rel, new_rel, len(replacements))
            self.controller._push_command({
                "type": "safe_move",
                "label": undo_label,
                "old_path": old_rel,
                "new_path": new_rel,
                "replacements": [
                    {
                        "entity_id": r.entity_id,
                        "field_path": r.field_path,
                        "old_value": r.old_value,
                        "new_value": r.new_value,
                    }
                    for r in replacements
                ],
            })

        self._refresh_project_tree()

        n_refs = len(replacements)
        if is_web:
            self._toast(f"Preview: Moved + {n_refs} ref(s) updated")
        else:
            if n_refs > 0:
                self._toast(f"{n_refs} ref(s) updated")
            else:
                self._toast(
                    "No changes made" if not replacements and is_web else "Moved file",
                    severity="warning" if not replacements and is_web else "info",
                )
                # Original logic for move toast was slightly different, I'll match intent.

        return True

    def move_selected_paths_to_folder(self, paths: list[str], dest_folder_rel: str) -> bool:
        """Move multiple assets into a folder and update references.

        Native runtime moves files; web runtime previews only.
        """
        if not paths:
            return False

        ordered = sorted({p for p in paths if p})
        if not ordered:
            return False

        is_web = self._is_web_runtime()
        scene = self._get_current_scene_payload()

        moves: list[tuple[str, str]] = []
        for old_rel in ordered:
            old_rel_norm, new_rel = compute_move_paths(old_rel, dest_folder_rel)
            if not new_rel or old_rel_norm == new_rel:
                continue
            moves.append((old_rel_norm, new_rel))

        if not moves:
            return False

        replacements: list[RenameReplacement] = []
        for old_rel, new_rel in moves:
            replacements.extend(compute_reference_replacements(scene, old_rel, new_rel))

        if not is_web:  # (a move that fails: the ones done are undone and no reference changes: #618)
            repo = self._project_root()
            if repo is None:
                return False
            done: list[FsStep] = []
            for old_rel, new_rel in moves:
                if not self._perform_fs_rename(repo, old_rel, new_rel):
                    self._rollback_fs(done, repo)
                    self._refuse("Move failed", f"{old_rel} couldn't be moved to {new_rel}; nothing was changed.")
                    return False
                done.append(FsStep(old_rel, new_rel, "move"))

        if replacements:
            new_scene = apply_reference_replacements(scene, replacements)
            self._set_current_scene_payload(new_scene)
        undo_label = f"Move Assets · {len(moves)} → {dest_folder_rel}"
        self.controller._push_command({
            "type": "safe_move_batch",
            "label": undo_label,
            "moves": [
                {"old_path": old_rel, "new_path": new_rel}
                for old_rel, new_rel in moves
            ],
            "replacements": [
                {
                    "entity_id": r.entity_id,
                    "field_path": r.field_path,
                    "old_value": r.old_value,
                    "new_value": r.new_value,
                }
                for r in replacements
            ],
        })

        self._refresh_project_tree()

        if is_web:
            self._toast(f"Preview: Moved {len(moves)} asset(s)")
        else:
            self._toast(f"Moved {len(moves)} asset(s)")
        return True

    def copy_selected_path(self) -> bool:
        """Copy selected path to clipboard."""
        row = self._get_selected_project_row()
        if not row:
            return False

        path: str | None = None
        entry = getattr(row, "entry", None)
        if entry is not None:
            path = getattr(entry, "rel_path", None)
        if not path:
            recent = getattr(row, "recent", None)
            if recent is not None:
                path = getattr(recent, "rel_path", None)

        if not path:
            return False

        formatted = format_copy_path_text(path)
        if not formatted:
            return False

        self._try_copy_to_os_clipboard(formatted)
        self._toast(f"Copied: {formatted}")
        return True

    def copy_selected_paths(self, paths: list[str]) -> bool:
        """Copy multiple selected paths to clipboard."""
        formatted = format_paths_for_clipboard(paths)
        if not formatted:
            return False
        self._try_copy_to_os_clipboard(formatted)
        self._toast(f"Copied {len(formatted.splitlines())} path(s)")
        return True

    def copy_common_parent(self, paths: list[str]) -> bool:
        """Copy common parent folder to clipboard."""
        parent = compute_common_parent(paths)
        if not parent:
            return False
        self._try_copy_to_os_clipboard(parent)
        self._toast(f"Copied: {parent}")
        return True

    # -- Capability Checks (EditorFileOpsProtocol) --

    def safe_rename_selected_asset(self, new_name: str) -> bool:
        """Alias for rename_selected_asset to satisfy EditorFileOpsProtocol."""
        return self.rename_selected_asset(new_name)

    def can_copy_selected_path(self) -> bool:
        """Check if we can copy a path from the selection."""
        row = self._get_selected_project_row()
        return row is not None

    def can_safe_rename_selected_asset(self) -> bool:
        """Check if we can safely rename the selected asset."""
        row = self._get_selected_project_row()
        if not row:
            return False

        entry = getattr(row, "entry", None)
        # Must be a file entry (not None and not a directory)
        if entry is None or getattr(entry, "is_dir", False):
            return False

        return True

    def can_safe_move_selected_asset(self) -> bool:
        """Check if we can safe move the selected asset."""
        # Same conditions as rename for now - must be a file
        return self.can_safe_rename_selected_asset()

    def can_delete_selected_assets(self, paths: list[str]) -> bool:
        return bool(paths)

    def can_move_selected_assets(self, paths: list[str]) -> bool:
        return bool(paths)

    # -- Helpers --

    def _get_selected_project_row(self) -> Any:
        if hasattr(self.controller, "project_explorer"):
            return self.controller.project_explorer.get_selected_row()
        return None

    def _get_current_scene_payload(self) -> Dict[str, Any]:
        scene = getattr(
            getattr(self.controller.window, "scene_controller", None),
            "_loaded_scene_data",
            None,
        )
        if not isinstance(scene, dict):
            return {}
        return scene

    def _set_current_scene_payload(self, scene: Dict[str, Any]) -> None:
        if hasattr(self.controller.window, "scene_controller"):
             # type check ignore as we are dynamically accessing
             self.controller.window.scene_controller._loaded_scene_data = scene

    def _refresh_project_tree(self) -> None:
        if hasattr(self.controller, "project_explorer"):
            self.controller.project_explorer.refresh_tree()
        elif hasattr(self.controller, "_refresh_project_explorer_rows"):
            self.controller._refresh_project_explorer_rows()

    def _toast(self, message: str, *, severity: str = "info", seconds: float | None = None) -> None:
        feedback = getattr(self.controller, "feedback", None)
        method = getattr(feedback, severity, None) if feedback is not None else None
        if callable(method):
            if seconds is not None:
                method(message, ttl=seconds)
            else:
                method(message)

        hud = getattr(self.controller.window, "player_hud", None)
        toaster = getattr(hud, "enqueue_" "toast", None) if hud is not None else None
        if callable(toaster):
            toaster(message, seconds=2.5 if seconds is None else seconds)

    def _is_web_runtime(self) -> bool:
        return sys.platform == "emscripten" or os.environ.get("PYGBAG") == "1"

    def _perform_fs_rename(self, repo: Path, old_rel: str, new_rel: str) -> bool:
        try:
            old_abs = repo / old_rel
            new_abs = repo / new_rel
            case_only = is_case_only_rename(old_rel, new_rel)

            # Basic checks
            if self._plan_refusal(repo, [FsStep(old_rel, new_rel, "move")], []):  # (#618: same guard as V2)
                return False
            if not old_abs.exists():
                return False
            if new_abs.exists() and not case_only:
                return False  # Don't overwrite

            # Ensure parent dir exists (for move)
            if not new_abs.parent.exists():
                new_abs.parent.mkdir(parents=True, exist_ok=True)

            if case_only:
                temp_rel = compute_temp_rename_rel(old_rel, repo)
                temp_abs = repo / temp_rel
                try:
                    _move_no_clobber(old_abs, temp_abs)
                    _move_no_clobber(temp_abs, new_abs)
                    return True
                except Exception:
                    _log_swallow("EFOC-018", "blanket exception fallback", once=False)
                    # Best-effort rollback
                    try:
                        if temp_abs.exists() and not old_abs.exists():
                            _move_no_clobber(temp_abs, old_abs)
                    except Exception:
                        _log_swallow("EFOC-019", "blanket exception fallback", once=False)
                        pass
                    return False

            _move_no_clobber(old_abs, new_abs)
            return True
        except Exception:
            _log_swallow("EFOC-020", "blanket exception fallback", once=False)
            return False

    def _try_copy_to_os_clipboard(self, text: str) -> None:
        """Attempt to copy text to OS clipboard. Safe no-op if unavailable."""
        try:
            pyperclip_module = __import__("pyperclip")
            copy_fn = getattr(pyperclip_module, "copy", None)
            if callable(copy_fn):
                copy_fn(text)
        except Exception:
            _log_swallow("EFOC-021", "blanket exception fallback", once=False)
            pass

    def request_safe_rename_refactor(self, new_name: str) -> bool:
        """Request V2 safe rename."""
        # 1. Selection
        row = self._get_selected_project_row()
        if not row:
            return False
        entry = getattr(row, "entry", None)
        old_rel = getattr(entry, "rel_path", None)  # (the Project panel's rows carry no absolute path: #641)
        if not isinstance(old_rel, str) or not old_rel:
            return False

        repo_root = self._project_root()
        if repo_root is None:
            return False

        # 2. Paths: a rename gives a new name in the same folder, never a path (#618)
        why = name_refusal(new_name)
        if why:
            self._refuse("Rename refused", why)
            return False
        parent_rel = posixpath.dirname(old_rel)
        new_rel = f"{parent_rel}/{new_name}" if parent_rel else new_name
        if old_rel == new_rel:
            return False

        # 3. Plan Data
        mapping = compute_rename_mapping(old_rel, new_rel)
        modifications, all_replacements = self._scan_and_compute_replacements(repo_root, mapping)

        # 4. Build Plan
        # Rename is effectively a move
        fs_step = FsStep(src_rel=old_rel, dst_rel=new_rel, kind="move")
        refusal = self._plan_refusal(repo_root, [fs_step], list(modifications))
        if refusal:
            self._refuse("Rename refused", refusal)
            return False

        fs_summary = f"Rename: {old_rel} -> {new_name}"
        preview_lines = format_refactor_preview(
            "Confirm Rename", "rename", fs_summary, modifications
        )

        undo_cmd = {
            "type": "safe_rename_refactor",
            "label": f"Rename {old_rel} -> {new_name}",
            "old_path": old_rel,
            "new_path": new_rel,
        }
        op_id = self._compute_refactor_op_id("rename", [fs_step], modifications)

        self._pending_refactor_plan = PendingRefactorPlan(
            op_kind="rename",
            op_id=op_id,
            fs_steps=[fs_step],
            json_updates=modifications,
            preview_lines=preview_lines,
            trash_moves=[],
            active_scene_update=self._compute_active_scene_update(mapping),
            undo_command=undo_cmd,
            selection_restore=[new_rel]
        )

        self.controller.confirm_modal.request_confirmation(
            title="Confirm Safe Rename",
            message_lines=preview_lines,
            on_confirm=self.confirm_pending_refactor,
            on_cancel=self.cancel_pending_refactor
        )
        return True

    def request_safe_move_refactor(self, dest_folder: str = "") -> bool:
        """Request V2 safe move (folder or file)."""
        project = getattr(self.controller, "project_explorer", None)
        if not project:
            return False

        repo_root = self._project_root()
        if repo_root is None:
            return False

        if hasattr(project, "ensure_rows"):
            project.ensure_rows()

        paths = project.selected_paths(getattr(project, "selectable_rows", []))
        if not isinstance(paths, (list, tuple)):
            paths = []
        if not paths:
            row = self._get_selected_project_row()
            entry = getattr(row, "entry", None) if row is not None else None
            candidate: str | None = None
            if entry is not None:
                rel_candidate = getattr(entry, "rel_path", None)
                if isinstance(rel_candidate, str) and rel_candidate:
                    candidate = rel_candidate
                else:
                    path_candidate = getattr(entry, "path", None)
                    if isinstance(path_candidate, str) and path_candidate:
                        candidate = path_candidate
            if candidate:
                try:
                    candidate_path = Path(str(candidate))
                    if candidate_path.is_absolute():
                        candidate = candidate_path.relative_to(repo_root).as_posix()
                except Exception:
                    _log_swallow("EFOC-022", "blanket exception fallback", once=False)
                    pass
                paths = [str(candidate).replace("\\", "/")]
        if not paths:
            return False

        if str(dest_folder or "").strip()[:1] in ("/", "\\"):  # (an absolute path, never the project's root: #618)
            self._refuse("Move refused", f"{dest_folder} is not a folder path inside the project (like assets/sprites).")
            return False
        dest_norm = normalize_repo_rel(dest_folder)
        full_mapping: dict[str, str] = {}
        fs_steps: list[FsStep] = []
        new_rels: list[str] = []

        for p_str in paths:
             # Normalize
             old_rel_norm = normalize_repo_rel(p_str)
             basename = posixpath.basename(old_rel_norm)

             if dest_norm:
                 new_rel = f"{dest_norm}/{basename}"
             else:
                 new_rel = basename

             if old_rel_norm == new_rel:
                 continue

             sub_map = compute_move_mapping(old_rel_norm, new_rel)
             full_mapping.update(sub_map)

             fs_steps.append(FsStep(src_rel=old_rel_norm, dst_rel=new_rel, kind="move"))
             new_rels.append(new_rel)

        if not fs_steps:
             return False

        modifications, all_replacements = self._scan_and_compute_replacements(repo_root, full_mapping)
        refusal = self._plan_refusal(repo_root, fs_steps, list(modifications))
        if refusal:
            self._refuse("Move refused", refusal)
            return False

        if len(fs_steps) == 1:
            fs_summary = f"Move: {fs_steps[0].src_rel} -> {fs_steps[0].dst_rel}"
        else:
            fs_summary = f"Move {len(fs_steps)} items to {dest_norm or 'root'}"

        preview_lines = format_refactor_preview(
             "Confirm Move", "move", fs_summary, modifications
        )

        # We store the list of moves for undo
        undo_cmd = {
            "type": "safe_move_refactor",
            "moves": [{"old_path": s.src_rel, "new_path": s.dst_rel} for s in fs_steps],
            # Legacy field for single move compat if needed
            "old_path": fs_steps[0].src_rel if len(fs_steps) == 1 else "",
            "new_path": fs_steps[0].dst_rel if len(fs_steps) == 1 else "",
        }
        op_id = self._compute_refactor_op_id("move", fs_steps, modifications)

        self._pending_refactor_plan = PendingRefactorPlan(
            op_kind="move",
            op_id=op_id,
            fs_steps=fs_steps,
            json_updates=modifications,
            preview_lines=preview_lines,
            trash_moves=[],
            active_scene_update=self._compute_active_scene_update(full_mapping),
            undo_command=undo_cmd,
            selection_restore=new_rels
        )

        self.controller.confirm_modal.request_confirmation(
            title=f"Confirm Move ({len(fs_steps)} items)",
            message_lines=preview_lines,
            on_confirm=self.confirm_pending_refactor,
            on_cancel=self.cancel_pending_refactor
        )
        return True


    def request_safe_delete_refactor(self, paths: List[str]) -> bool:
        """Request V2 safe batch delete."""
        if not paths:
            return False
        repo_root = self._project_root()
        if repo_root is None:
            return False

        # Build mapping for all paths -> delete (None)
        # Note: compute_move_mapping handles singular paths.
        # We need to compute delete replacements specifically.
        # But our helper '_scan_and_compute_replacements' takes a mapping.
        # Let's construct a mapping where value is "" (empty string) to clear references.

        mapping = {}
        fs_steps = []

        sorted_paths = sorted(paths)
        for p in sorted_paths:
            # For each path, if it's a folder, we mapping implicitly covers children via 'compute_move_mapping' prefix logic?
            # No, 'compute_move_mapping' handles prefix.
            # Does 'compute_replacements' handle prefix logic for deletion?
            # It checks if ref.asset_path starts with?
            # asset_refactor_model.compute_replacements relies on exact match or prefix if folder.
            # So mapping[p] = "" should work if the model supports it.
            # Assuming model treats empty string as "replace with empty".
            mapping[p] = ""
            fs_steps.append(FsStep(src_rel=p, dst_rel=None, kind="delete"))

        refusal = self._plan_refusal(repo_root, fs_steps, [])  # (folders and paths outside the project: nothing asked)
        if refusal:
            self._refuse("Delete refused", f"{refusal} Nothing was changed.")
            return False

        modifications, all_replacements = self._scan_and_compute_replacements(repo_root, mapping)

        fs_summary = f"Delete {len(sorted_paths)} items:\n" + "\n".join([f"  - {p}" for p in sorted_paths[:5]])
        if len(sorted_paths) > 5:
            fs_summary += f"\n  ...and {len(sorted_paths)-5} more."
        fs_summary += "\n(Staged to .mesh_trash)"

        preview_lines = format_refactor_preview(
             "Confirm Delete", "delete", fs_summary, modifications
        )

        undo_cmd = {
             "type": "safe_delete_batch",
             "label": f"Delete {len(sorted_paths)} items",
             "paths": sorted_paths
        }

        op_id = self._compute_refactor_op_id("delete", fs_steps, modifications)
        trash_moves = self._build_trash_moves(repo_root, fs_steps, op_id)
        self._pending_refactor_plan = PendingRefactorPlan(
            op_kind="delete",
            op_id=op_id,
            fs_steps=fs_steps,
            json_updates=modifications,
            preview_lines=preview_lines,
            trash_moves=trash_moves,
            active_scene_update=self._compute_active_scene_update(mapping),
            undo_command=undo_cmd,
            selection_restore=None
        )

        self.controller.confirm_modal.request_confirmation(
            title="Confirm Delete",
            message_lines=preview_lines,
            on_confirm=self.confirm_pending_refactor,
            on_cancel=self.cancel_pending_refactor
        )
        return True

    def _scan_and_compute_replacements(
        self, repo_root: Path, mapping: Dict[str, str]
    ) -> Tuple[Dict[str, List[Replacement]], List[Replacement]]:
        """Helper to scan repo and find references."""
        candidates = self.list_repo_json_assets(repo_root)

        modifications: Dict[str, List[Replacement]] = {}
        all_refs: List[Replacement] = []

        for c_rel in candidates:
            c_full = repo_root / c_rel
            if not c_full.exists():
                continue
            try:
                with open(c_full, "r", encoding="utf-8") as f:
                    payload = json.load(f)

                refs = scan_scene_references(payload) if "entities" in payload else scan_prefab_references(payload)
                file_replacements = compute_replacements(refs, mapping)
                if file_replacements:
                    modifications[c_rel] = file_replacements
                    all_refs.extend(file_replacements)
            except Exception:
                _log_swallow("EFOC-023", "blanket exception fallback", once=False)
                continue
        return modifications, all_refs

    def _compute_active_scene_update(self, mapping: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Compute updated payload for the currently active scene."""
        current_scene = self._get_current_scene_payload()
        if not current_scene:
            return None
        refs = scan_scene_references(current_scene)
        reps = compute_replacements(refs, mapping)
        if reps:
            return apply_replacements(current_scene, reps)
        return None


_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
)


def name_refusal(name: str) -> Optional[str]:
    """Why ``name`` can't be one file or folder name in a project on any OS (#618), or None.

    Refuses separators and drive colons (a name is never a path), ``.``/``..``, Windows-invalid characters, a
    trailing space or dot (Windows drops it, so it names another file) and Windows' reserved device names."""
    if name in ("", ".", ".."):
        return f"'{name}' is not a file name."
    if any(ch in INVALID_FILENAME_CHARS or ord(ch) < 32 for ch in name):
        return f'\'{name}\' contains a character a file name can\'t have (/ \\ : < > " | ? * or a control character).'
    if name.rstrip(" .") != name:
        return f"'{name}' ends in a space or a dot, which Windows drops."
    if name.split(".")[0].rstrip(" ").upper() in _WINDOWS_RESERVED:
        return f"'{name}' is a device name Windows reserves."
    return None


def rel_refusal(rel: str) -> Optional[str]:
    """Why ``rel`` isn't a plain project-relative path (``a/b/c.png``: no absolute path, drive, ``..`` or
    backslash; every part a valid name), or None."""
    for part in rel.split("/"):
        why = name_refusal(part)
        if why:
            return why
    return None


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _move_no_clobber(src: Path, dst: Path) -> None:
    """Move ``src`` to ``dst`` without ever replacing what is at ``dst``: raises (FileExistsError, or another OSError)
    instead (#618). ``os.replace`` overwrites silently, so a file made at ``dst`` after the plan was checked would be
    lost; here the final move itself refuses."""
    if sys.platform == "win32":
        os.rename(src, dst)  # MoveFileEx without REPLACE_EXISTING: FileExistsError for a file or folder; case-only works
        return
    if os.path.isdir(src) and not os.path.islink(src):
        os.rename(src, dst)  # POSIX replaces only an EMPTY folder (ENOTEMPTY/ENOTDIR otherwise): no data can be lost
        return
    if _same_file(src, dst):
        os.rename(src, dst)  # a case-only rename on a case-insensitive disk: one file, nothing to clobber
        return
    try:
        os.link(src, dst, follow_symlinks=False)  # FileExistsError if anything is at dst; a symlink stays a symlink
    except FileExistsError:
        raise
    except (OSError, NotImplementedError):
        # ponytail: no hard links on this file system (FAT/exFAT, some network/FUSE mounts): re-check, then rename,
        # which leaves a microsecond window in which a file made at dst would be replaced. Upgrade path:
        # renameat2(RENAME_NOREPLACE) where the platform has it.
        if os.path.lexists(dst):
            raise FileExistsError(errno.EEXIST, "already exists", str(dst)) from None
        os.rename(src, dst)
        return
    os.unlink(src)


def _interrupted_link(repo_root: Path, step: FsStep) -> bool:
    """Whether a move by link+unlink was cut short: source and destination are two names of one file (never a
    case-only rename, where they are one name)."""
    if not step.dst_rel or step.src_rel.casefold() == step.dst_rel.casefold():
        return False
    return _same_file(Path(repo_root) / step.src_rel, Path(repo_root) / step.dst_rel)


def is_case_only_rename(old_rel: str, new_rel: str) -> bool:
    """Return True if rename differs only by case."""
    if old_rel == new_rel:
        return False
    return old_rel.casefold() == new_rel.casefold()


def compute_temp_rename_rel(old_rel: str, repo_root: Path) -> str:
    """Compute deterministic temp rename path in same directory.

    Uses a hash of old_rel and resolves collisions with deterministic suffixes.
    """
    posix = PurePosixPath(old_rel)
    directory = posix.parent.as_posix() if posix.parent != PurePosixPath(".") else ""
    base = posix.stem
    ext = posix.suffix
    digest = hashlib.md5(old_rel.encode("utf-8")).hexdigest()[:8]
    base_temp = f"{base}.__meshtmp__{digest}"

    def make_rel(name: str) -> str:
        return f"{directory}/{name}" if directory else name

    candidate = make_rel(f"{base_temp}{ext}")
    if not (repo_root / candidate).exists():
        return candidate

    counter = 1
    while counter < 100:
        suffix = f"__{counter:02d}"
        candidate = make_rel(f"{base_temp}{suffix}{ext}")
        if not (repo_root / candidate).exists():
            return candidate
        counter += 1

    # Fallback deterministic candidate if many collisions
    return make_rel(f"{base_temp}__{counter:02d}{ext}")
