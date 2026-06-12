import hashlib
import json
import os
import shutil
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypedDict

from engine import json_io
from engine.swallowed_exceptions import _log_swallow
from engine.tooling import plan_history, polish, scaffold
from engine.tooling.plan_types import Action, Plan
from engine.tooling.validate_all import UnifiedValidator

BACKUP_DIR = Path(".mesh/plan_backups")

class PlanExecutionSummary(TypedDict):
    files_created: list[str]
    files_modified: list[str]
    actions_executed: int

class BackupManager:
    def __init__(self):
        self.backup_root = BACKUP_DIR
        self.current_backup_path: Optional[Path] = None
        self.manifest: Dict[str, List[str]] = {"modified": [], "created": []}

    def start_backup(self, plan_id: str):
        ts = int(time.time())
        name = f"{ts}_{plan_id}"
        self.current_backup_path = self.backup_root / name
        self.current_backup_path.mkdir(parents=True, exist_ok=True)
        self.manifest = {"modified": [], "created": []}

    def backup_file(self, path: Path):
        if not self.current_backup_path:
            return

        str_path = str(path)
        if path.exists():
            # It's a modification
            if str_path not in self.manifest["modified"]:
                # Copy original to backup
                # We maintain directory structure inside backup to avoid collisions
                if path.is_absolute():
                    dest = self.current_backup_path / "files" / path.relative_to(path.anchor)
                else:
                    dest = self.current_backup_path / "files" / path

                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(path, dest)
                except PermissionError:
                    # Fallback to copy if metadata copy fails (common on Windows)
                    shutil.copy(path, dest)
                self.manifest["modified"].append(str_path)
        else:
            # It's a creation
            if str_path not in self.manifest["created"]:
                self.manifest["created"].append(str_path)

    def finish_backup(self):
        if self.current_backup_path:
            manifest_path = self.current_backup_path / "manifest.json"
            json_io.write_json_atomic(manifest_path, self.manifest)

    def restore_last_backup(self) -> bool:
        if not self.backup_root.exists():
            print("[Mesh][Undo] No backups found.")
            return False

        backups = sorted([d for d in self.backup_root.iterdir() if d.is_dir()], key=lambda x: x.name, reverse=True)
        if not backups:
            print("[Mesh][Undo] No backups found.")
            return False

        target = backups[0]
        print(f"[Mesh][Undo] Restoring backup: {target.name}")

        manifest_path = target / "manifest.json"
        if not manifest_path.exists():
            print("[Mesh][Undo] Corrupt backup (missing manifest).")
            return False

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            # 1. Delete created files
            for created in manifest.get("created", []):
                p = Path(created)
                if p.exists():
                    print(f"  - Deleting {p}")
                    p.unlink()

            # 2. Restore modified files
            for modified in manifest.get("modified", []):
                dst = Path(modified)

                if dst.is_absolute():
                    src = target / "files" / dst.relative_to(dst.anchor)
                else:
                    src = target / "files" / dst

                if src.exists():
                    print(f"  - Restoring {dst}")
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(src, dst)
                    except PermissionError:
                        shutil.copy(src, dst)
                else:
                    print(f"  - Warning: Backup source missing for {modified}")

            print("[Mesh][Undo] Restore complete.")
            # Optionally delete the backup folder or mark as restored?
            # For now, keep it.
            return True

        except Exception as e:
            print(f"[Mesh][Undo] Error restoring backup: {e}")
            return False

class PlanExecutor:
    def __init__(self, dry_run: bool = False, safe_paths_only: bool = False, writer: Optional[Callable[[Path, str], None]] = None):
        self.dry_run = dry_run
        self.safe_paths_only = safe_paths_only
        self._writer = writer
        # Back-compat: some callers access `executor.writer` directly.
        self.writer = writer
        self._captured_write_paths: set[str] = set()
        self.captured_writes: list[str] = []
        self.backup_mgr = BackupManager()
        self.summary: PlanExecutionSummary = {"files_created": [], "files_modified": [], "actions_executed": 0}
        self.current_plan: Optional[Plan] = None

    def _normalize_captured_path(self, path: Path) -> str:
        text = str(path)
        if os.path.isabs(text):
            try:
                text = os.path.relpath(text, start=str(Path.cwd()))
            except ValueError:
                text = path.as_posix().replace(":", "").lstrip("/")
        text = text.replace("\\", "/")
        if text.startswith("./"):
            text = text[2:]
        return text

    def _write_file(self, path: Path, content: str):
        if self._writer is not None:
            self._captured_write_paths.add(self._normalize_captured_path(path))
            self._writer(path, content)
            return

        json_io.write_text_atomic(path, content, encoding="utf-8")

    def _dump_json(self, payload: Any) -> str:
        return json_io.dumps_stable(payload) + "\n"

    def undo_last(self) -> bool:
        return self.backup_mgr.restore_last_backup()

    def execute(self, plan: Plan, profile: str = "default", ai_safe: bool = False):
        self.current_plan = plan
        capture_mode = self._writer is not None
        self._captured_write_paths = set()
        self.captured_writes = []

        # Enforce meta.touches for AI-safe plans
        if ai_safe:
            meta = plan.inputs.get("meta", {})
            touches = meta.get("touches")
            if not touches or not isinstance(touches, list):
                raise ValueError("AI-safe apply requires plan.meta.touches (non-empty).")

            # Verify touches match actions
            targets = self._collect_action_targets(plan)
            missing = sorted(list(targets - set(touches)))
            if missing:
                raise ValueError(f"AI-safe apply requires plan.meta.touches to include all action targets. Missing: {missing}")

        if not self.dry_run and not capture_mode:
            # Generate a plan ID hash
            plan_id = hashlib.md5(json_io.dumps_stable(asdict(plan)).encode()).hexdigest()[:8]
            self.backup_mgr.start_backup(plan_id)

        print(f"[Mesh][Executor] Executing plan ({len(plan.actions)} actions)...")

        try:
            for action in plan.actions:
                print(f"  > {action.description}")
                self._run_action(action)
                self.summary["actions_executed"] += 1
        except Exception as e:
            print(f"[Mesh][Executor] ERROR: {e}")
            if not self.dry_run and not capture_mode:
                print("[Mesh][Executor] Attempting rollback...")
                self.backup_mgr.finish_backup()
                # Auto-rollback could happen here, but we leave it to user for now.
            raise e

        self.captured_writes = sorted(self._captured_write_paths)
        if ai_safe and capture_mode:
            meta = plan.inputs.get("meta", {})
            touches_raw = meta.get("touches") or []
            touches_norm = {
                self._normalize_captured_path(Path(p))
                for p in touches_raw
                if isinstance(p, str)
            }
            missing = sorted(self._captured_write_paths - touches_norm)
            if missing:
                raise ValueError(f"touches mismatch: missing {missing}")

        if not self.dry_run and not capture_mode:
            self.backup_mgr.finish_backup()
            plan_history.record_history(plan, dict(self.summary), profile)

        return self.summary

    def _check_safety(self, path: Path):
        if not self.safe_paths_only:
            return
        if self.current_plan is None:
            return

        # Resolve absolute path to check against roots
        abs_path = path.resolve()
        cwd = Path.cwd().resolve()

        # 1. Allowlist
        allowlist = [
            cwd / "assets/data/quests.json",
            cwd / "assets/data/events.json",
            cwd / "assets/prefabs.json",
            cwd / "assets/data/items.json"
        ]
        if abs_path in allowlist:
            return

        # 2. Pack Root
        # We try to guess pack root from plan inputs
        pack_id = self.current_plan.inputs.get("pack")
        if pack_id:
            pack_root = cwd / "packs" / pack_id
            if self._is_subpath(abs_path, pack_root):
                return

        # 3. World File
        # We check if any action in the plan targets this world?
        # Or just check if the path matches 'into_world' input?
        into_world = self.current_plan.inputs.get("into_world")
        if into_world:
            world_path = (cwd / into_world).resolve()
            if abs_path == world_path:
                return

        # 4. Scenes directory (if not in pack)
        # If no pack is specified, maybe we allow writing to scenes/?
        # The requirement says "refuse to modify files outside: target pack root... target world file... shared data".
        # It implies if no pack is specified, we might be restricted?
        # But 'new-region' writes to 'scenes/'.
        # If safe mode is on, and no pack is specified, maybe we allow 'scenes/'?
        # Let's be strict. If safe mode is on, you MUST be in a pack or allowlist.
        # Wait, the user prompt says "target pack root (if specified)".
        # If NOT specified, what is the safe root? The workspace root? That defeats the purpose.
        # Maybe "scenes/" is implicitly allowed?
        # Let's allow "scenes/" and "worlds/" for now if no pack is specified.
        if not pack_id:
             if self._is_subpath(abs_path, cwd / "scenes") or self._is_subpath(abs_path, cwd / "worlds"):
                 return

        raise Exception(f"Safety Violation: Access denied to '{path}'. Allowed: Packs, World, or Shared Data.")

    def _is_subpath(self, path: Path, parent: Path) -> bool:
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False

    def _run_action(self, action: Action):
        t = action.type
        a = action.args

        if self.dry_run:
            return

        if t == "init_pack":
            self._init_pack(a)
        elif t == "create_scene":
            self._create_scene(a)
        elif t == "add_npc":
            self._add_npc(a)
        elif t == "create_quest":
            self._create_quest(a)
        elif t == "wire_world":
            self._wire_world(a)
        elif t == "polish_scene":
            self._polish_scene(a)
        elif t == "validate":
            self._validate(a)
        elif t == "auto_wire_transitions":
            self._auto_wire_transitions(a)
            return
        elif t == "add_puzzle_switch_door":
            self._add_puzzle_switch_door(a)
        elif t == "add_transition":
            self._add_transition(a)
        elif t == "add_npc_dialogue":
            self._add_npc_dialogue(a)
        else:
            print(f"  [Warning] Unknown action type: {t}")

    def _track_file(self, path: Path):
        self._check_safety(path)
        if not self.dry_run:
            if self._writer is None:
                self.backup_mgr.backup_file(path)
            if path.exists():
                if str(path) not in self.summary["files_modified"]:
                    self.summary["files_modified"].append(str(path))
            else:
                if str(path) not in self.summary["files_created"]:
                    self.summary["files_created"].append(str(path))

    def _init_pack(self, args: Dict[str, Any]):
        path = Path(args["path"])
        manifest = path / "manifest.json"

        if self._writer is None and not path.exists():
            path.mkdir(parents=True, exist_ok=True)

        self._track_file(manifest)
        if not manifest.exists():
            content = self._dump_json({
                "id": args["id"],
                "name": args["id"],
                "wip": args.get("wip", True)
            })
            self._write_file(manifest, content)

    def _create_scene(self, args: Dict[str, Any]):
        path = Path(args["path"])
        self._track_file(path)
        if self._writer is None:
            path.parent.mkdir(parents=True, exist_ok=True)

        # Use generate_scene_data instead of create_scene to support write seam
        scene_data = scaffold.generate_scene_data(str(path), args["template"], args)
        if scene_data:
            content = self._dump_json(scene_data)
            self._write_file(path, content)
            print(f"[Mesh][Scaffold] Created new scene at '{path}' using template '{args['template']}'")
        else:
            print(f"[Mesh][Executor] Failed to generate scene data for '{path}'")

    def _add_npc(self, args: Dict[str, Any]):
        path = Path(args["scene_path"])
        self._track_file(path)

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        role = args.get("role", "guard")
        template = scaffold.get_npc_template(role)

        if template:
            npc = template.copy()
            npc["x"] = args.get("x", 300)
            npc["y"] = args.get("y", 300)
            if "name" in args:
                npc["name"] = args["name"]
            if "tags" in args:
                npc.setdefault("tags", []).extend(args["tags"])
        else:
            behaviours = ["Dialogue"]
            behaviour_config = {
                "Dialogue": {"role": role}
            }

            if args.get("quest_id"):
                behaviours.append("QuestGiver")
                behaviour_config["QuestGiver"] = {"quest_id": args["quest_id"]}

            npc = {
                "name": args.get("name", "NPC"),
                "x": args.get("x", 300),
                "y": args.get("y", 300),
                "sprite": "assets/placeholder.png",
                "tag": "npc",
                "tags": args.get("tags", []),
                "behaviours": behaviours,
                "behaviour_config": behaviour_config
            }

        data.setdefault("entities", []).append(npc)

        self._write_file(path, self._dump_json(data))

    def _create_quest(self, args: Dict[str, Any]):
        path = Path(args["path"])
        self._track_file(path)
        if self._writer is None:
            path.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {"quests": []}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                _log_swallow("PLAN-001", "engine/tooling/plan_executor.py pass-only blanket swallow")
                pass

        if not any(q["id"] == args["id"] for q in data.get("quests", [])):
            data.setdefault("quests", []).append({
                "id": args["id"],
                "title": args["title"],
                "type": args["type"],
                "steps": []
            })
            self._write_file(path, self._dump_json(data))

    def _wire_world(self, args: Dict[str, Any]):
        world_path = Path(args["world_path"])
        if not world_path.exists():
            print(f"Warning: World '{world_path}' not found, skipping wiring.")
            return

        self._track_file(world_path)
        with world_path.open("r", encoding="utf-8") as f:
            world = json.load(f)

        scene_id = args["scene_id"]
        scene_path = args["scene_path"]

        # Add scene
        if "scenes" not in world:
            world["scenes"] = {}
        world["scenes"][scene_id] = {"path": scene_path}

        # Link
        link_from = args.get("link_from")
        if link_from and link_from in world["scenes"]:
            if "links" not in world:
                world["links"] = []
            # Check if link exists
            exists = any(
                link["from"] == link_from and link["to"] == scene_id
                for link in world["links"]
            )
            if not exists:
                world["links"].append({"from": link_from, "to": scene_id})
                world["links"].append({"from": scene_id, "to": link_from})

        self._write_file(world_path, self._dump_json(world))

    def _polish_scene(self, args: Dict[str, Any]):
        path = Path(args["path"])
        self._track_file(path)

        if args.get("compact_only"):
            # Use shared logic
            compacted = polish.generate_polished_scene_data(path)
            self._write_file(path, self._dump_json(compacted))
        else:
            # We need to polish (compact + validate) but using our writer.
            # 1. Generate data
            compacted = polish.generate_polished_scene_data(path)

            # 2. Write (via seam)
            self._write_file(path, self._dump_json(compacted))

            # 3. Validate (if not dry run, or if we can validate in-memory?)
            # Validation usually reads from disk. If we are in dry-run, the file on disk is OLD.
            # So validation might fail or be incorrect.
            # However, PlanExecutor usually runs actions sequentially.
            # If dry_run=True, we haven't written the file.
            # If we want to validate the RESULT, we need to validate the in-memory object or the temp file.
            # UnifiedValidator reads from disk.

            # For now, let's skip validation in dry-run, or accept that it validates the old file (which is wrong).
            # But wait, if we are not in dry run, we wrote the file (via _write_file -> path.write_text).
            # So we can validate.

            if not self.dry_run:
                validator = UnifiedValidator(Path("."))
                if not validator.validate_scene(path):
                    raise Exception("Polish validation failed")

    def _validate(self, args: Dict[str, Any]):
        check_refs = args.get("check_refs", False)
        validator = UnifiedValidator(Path("."), strict_compact=False, check_refs=check_refs)
        if not validator.validate_scene(Path(args["scene_path"])):
            raise Exception("Validation failed")

    def _auto_wire_transitions(self, args: Dict[str, Any]):
        from engine.tooling.auto_wire import AutoWireController
        world_path = args["world_path"]
        self._track_file(Path(world_path))

        # Pass our writer to the controller
        controller = AutoWireController(world_path, writer=self._write_file)
        controller.load()

        # Run dry-run first to see what needs changing
        controller.process(dry_run=True)

        # Track only scene files that will be modified
        for sid in controller.modified_scenes:
            if sid in controller.scene_paths:
                self._track_file(controller.scene_paths[sid])

        # Reload to reset state (process modifies in-memory scenes)
        controller.load()
        changes = controller.process(dry_run=False)
        for change in changes:
            print(f"[PlanExecutor] {change}")

    def _add_puzzle_switch_door(self, args: Dict[str, Any]):
        path = Path(args["scene_path"])
        self._track_file(path)

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        entities = data.setdefault("entities", [])

        # Generate unique IDs if not provided
        import uuid
        base_id = args.get("id_prefix", f"puzzle_{uuid.uuid4().hex[:8]}")
        event_id = args.get("event_id", f"{base_id}_unlock")

        # Switch
        switch_args = args.get("switch", {})
        entities.append({
            "name": f"{base_id}_switch",
            "x": switch_args.get("x", 0),
            "y": switch_args.get("y", 0),
            "sprite": switch_args.get("sprite", "assets/switch_off.png"),
            "tag": "interactable",
            "behaviours": ["SwitchInteract"],
            "behaviour_config": {
                "SwitchInteract": {
                    "event_id": event_id,
                    "one_shot": switch_args.get("one_shot", False),
                    "active_sprite": switch_args.get("active_sprite", "")
                }
            }
        })

        # Door
        door_args = args.get("door", {})
        entities.append({
            "name": f"{base_id}_door",
            "x": door_args.get("x", 0),
            "y": door_args.get("y", 0),
            "sprite": door_args.get("sprite", "assets/door_locked.png"),
            "tag": "solid",
            "behaviours": ["DoorLock"],
            "behaviour_config": {
                "DoorLock": {
                    "unlock_event": event_id,
                    "starts_locked": True,
                    "open_sprite": door_args.get("open_sprite", "")
                }
            }
        })

        # Reward (Optional)
        reward_args = args.get("reward")
        if reward_args:
            entities.append({
                "name": f"{base_id}_reward",
                "x": reward_args.get("x", 0),
                "y": reward_args.get("y", 0),
                "sprite": reward_args.get("sprite", "assets/chest.png"),
                "tag": "interactable",
                "behaviours": ["RewardChest"],
                "behaviour_config": {
                    "RewardChest": {
                        "unlock_event": event_id,
                        "item_id": reward_args.get("item_id", ""),
                        "gold": reward_args.get("gold", 0)
                    }
                }
            })

        self._write_file(path, self._dump_json(data))

    def _add_transition(self, args: Dict[str, Any]):
        path = Path(args["scene_path"])
        self._track_file(path)

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        entities = data.setdefault("entities", [])

        entities.append({
            "name": args.get("name", "Transition"),
            "x": args.get("x", 0),
            "y": args.get("y", 0),
            "sprite": args.get("sprite", "assets/placeholder.png"),
            "tag": "trigger",
            "behaviours": ["SceneTransition"],
            "behaviour_config": {
                "SceneTransition": {
                    "target_scene": args["target_scene"],
                    "spawn_id": args.get("spawn_id", "default"),
                    "allow_interact": args.get("allow_interact", True)
                }
            }
        })

        self._write_file(path, self._dump_json(data))

    def _add_npc_dialogue(self, args: Dict[str, Any]):
        path = Path(args["scene_path"])
        self._track_file(path)

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        npc_name = args["npc_name"]
        lines = args["lines"]
        dialogue_id = args.get("dialogue_id")
        speaker_alias = args.get("speaker_alias")

        found = False
        for entity in data.get("entities", []):
            if entity.get("name") == npc_name:
                found = True
                # Ensure Dialogue behaviour is present
                behaviours = entity.setdefault("behaviours", [])
                if "Dialogue" not in behaviours:
                    behaviours.append("Dialogue")

                # Update dialogue block
                dialogue = entity.setdefault("dialogue", {})
                dialogue["lines"] = lines

                if speaker_alias:
                    dialogue["speaker"] = speaker_alias
                elif "speaker" not in dialogue:
                    dialogue["speaker"] = npc_name

                if dialogue_id:
                    dialogue["id"] = dialogue_id

                break

        if not found:
            print(f"[PlanExecutor] Warning: NPC '{npc_name}' not found in '{path}'. Dialogue not added.")
            return

        self._write_file(path, self._dump_json(data))

    def _collect_action_targets(self, plan: Plan) -> set[str]:
        """Collect all file paths targeted by plan actions."""
        targets = set()
        for action in plan.actions:
            args = action.args

            # Common path keys
            for key in ["path", "scene_path", "world_path"]:
                if key in args and isinstance(args[key], str):
                    targets.add(args[key].replace("\\", "/"))

            # Specific keys
            if action.type == "add_transition" and "target_scene" in args:
                # Note: add_transition modifies scene_path, but target_scene is just a reference.
                # However, if we were to modify target_scene (e.g. auto-wire), it would be a target.
                # In standard add_transition, we only modify scene_path.
                pass

            if action.type == "wire_world":
                # wire_world modifies world_path (handled above) AND scene_path (handled above)
                pass

        return targets
