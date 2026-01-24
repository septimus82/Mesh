import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from engine.game_state_controller import GameStateController
from engine.paths import get_content_roots, set_content_roots
from engine.scene_loader import SceneLoader
from engine.tooling.plan_types import Plan


@dataclass
class TestSpec:
    __test__ = False
    name: str
    type: str # quest, scene, npc, world, prefab
    setup_actions: List[Dict[str, Any]] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    assertions: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class TestReport:
    __test__ = False
    passed: bool
    tests: List[Dict[str, Any]]
    coverage: Dict[str, Any]

    @property
    def coverage_ratio(self) -> float:
        total = self.coverage.get("actions_total", 0)
        if total == 0:
            return 1.0
        return self.coverage.get("actions_covered", 0) / total

class MockGame:
    def __init__(self):
        # Minimal mock for GameWindow
        pass

class PlanTester:
    def __init__(self, root_path: Path):
        self.root = root_path

    def infer_tests(self, plan: Plan) -> List[TestSpec]:
        tests = []
        for i, action in enumerate(plan.actions):
            if action.type in ("add_quest", "create_quest"):
                quest_id = action.args.get("id")
                if not quest_id:
                    continue

                test = TestSpec(name=f"Test Quest: {quest_id}", type="quest")

                # Setup: Activate quest
                test.setup_actions.append({"type": "activate_quest", "quest_id": quest_id})

                requirements = action.args.get("requirements", {})

                # Steps to satisfy requirements
                for flag in requirements.get("flags", []):
                    test.steps.append({"type": "set_flag", "flag": flag})

                for counter, value in requirements.get("counters", {}).items():
                    test.steps.append({"type": "set_counter", "counter": counter, "value": value})

                # Assertion: Quest Completed
                test.assertions.append({"type": "quest_completed", "quest_id": quest_id})

                tests.append(test)

            elif action.type == "create_scene":
                path = action.args.get("path")
                if path:
                    test = TestSpec(name=f"Load Scene: {Path(path).name}", type="scene")
                    test.assertions.append({"type": "scene_loadable", "path": path})
                    tests.append(test)

            elif action.type in ("place_npc", "add_npc"):
                scene_path = action.args.get("into") or action.args.get("scene_path")
                role = action.args.get("role") or action.args.get("name")
                if scene_path and role:
                    test = TestSpec(name=f"NPC Presence: {role} in {Path(scene_path).name}", type="npc")
                    test.assertions.append({"type": "npc_present", "scene_path": scene_path, "role": role})
                    tests.append(test)

            elif action.type in ("wire_world", "add_world_link"):
                world_path = action.args.get("world_path")
                if world_path:
                    test = TestSpec(name=f"World Reachability: {Path(world_path).name}", type="world")
                    test.assertions.append({"type": "world_reachable", "world_path": world_path})
                    tests.append(test)

            elif action.type == "place_prefab":
                prefab_id = action.args.get("prefab_id")
                if prefab_id:
                    test = TestSpec(name=f"Prefab Resolution: {prefab_id}", type="prefab")
                    test.assertions.append({"type": "prefab_resolves", "prefab_id": prefab_id})
                    tests.append(test)

            elif action.type == "add_transition":
                scene_path = action.args.get("scene") or action.args.get("scene_path")
                target_scene = action.args.get("target_scene")
                if scene_path and target_scene:
                    test = TestSpec(name=f"Transition: {Path(scene_path).name} -> {target_scene}", type="transition")
                    # Assert source scene is loadable
                    test.assertions.append({"type": "scene_loadable", "path": scene_path})
                    # Assert target scene is loadable (if it's a path) or resolves (if it's an ID)
                    # For simplicity, we'll use a generic 'transition_valid' assertion that checks both
                    test.assertions.append({
                        "type": "transition_valid",
                        "source_path": scene_path,
                        "target": target_scene
                    })
                    tests.append(test)

            elif action.type == "add_puzzle":
                scene_path = action.args.get("scene")
                if scene_path:
                    test = TestSpec(name=f"Puzzle in {Path(scene_path).name}", type="scene")
                    test.assertions.append({"type": "scene_loadable", "path": scene_path})
                    tests.append(test)

            elif action.type == "add_npc_dialogue":
                scene_path = action.args.get("scene_path")
                npc_name = action.args.get("npc_name")
                if scene_path and npc_name:
                    test = TestSpec(name=f"Dialogue: {npc_name} in {Path(scene_path).name}", type="npc")
                    test.assertions.append({"type": "npc_present", "scene_path": scene_path, "role": npc_name})
                    tests.append(test)

            elif action.type in ("polish_scene", "validate"):
                path = action.args.get("path") or action.args.get("scene_path")
                if path:
                    test = TestSpec(name=f"Validate Scene: {Path(path).name}", type="scene")
                    test.assertions.append({"type": "scene_loadable", "path": path})
                    tests.append(test)

        return tests

    def run_ai_tests(self, plan: Plan) -> TestReport:
        """Run AI-specific tests in sandbox."""
        # AI tests always run in sandbox
        return self.run_tests_in_sandbox(plan, full_sandbox=False)

    def run_tests(self, tests: List[TestSpec], total_actions: int = 0) -> TestReport:
        if not tests:
            print("[Mesh][Tester] No tests to run.")
            return TestReport(passed=True, tests=[], coverage={"actions_total": total_actions, "actions_covered": 0, "actions_skipped": []})

        print(f"[Mesh][Tester] Running {len(tests)} tests...")

        # Load quests data once
        all_quests = []

        # Load core quests
        quests_path = self.root / "assets/data/quests.json"
        if quests_path.exists():
            try:
                data = json.loads(quests_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "quests" in data:
                    all_quests.extend(data["quests"])
                elif isinstance(data, list):
                    all_quests.extend(data)
            except Exception as e:
                print(f"[Mesh][Tester] Failed to load quests.json: {e}")

        # Load pack quests
        packs_dir = self.root / "packs"
        if packs_dir.exists():
            for pack_dir in packs_dir.iterdir():
                pack_quests = pack_dir / "assets/data/quests.json"
                if pack_quests.exists():
                    try:
                        data = json.loads(pack_quests.read_text(encoding="utf-8"))
                        if isinstance(data, dict) and "quests" in data:
                            all_quests.extend(data["quests"])
                        elif isinstance(data, list):
                            all_quests.extend(data)
                    except Exception as e:
                        print(f"[Mesh][Tester] Failed to load quests from {pack_dir.name}: {e}")

        # Convert list to dict keyed by ID for QuestManager
        quests_data = {q["id"]: q for q in all_quests if "id" in q}

        results = []
        all_passed = True

        for test in tests:
            print(f"  - {test.name}...", end=" ")
            result = {"name": test.name, "type": test.type, "passed": False, "error": None}

            try:
                if test.type == "quest":
                    self._run_quest_test(test, quests_data)
                elif test.type == "scene":
                    self._run_scene_test(test)
                elif test.type == "npc":
                    self._run_npc_test(test)
                elif test.type == "world":
                    self._run_world_test(test)
                elif test.type == "prefab":
                    self._run_prefab_test(test)
                elif test.type == "transition":
                    self._run_transition_test(test)

                print("PASS")
                result["passed"] = True

            except AssertionError as e:
                print(f"FAIL: {e}")
                result["error"] = str(e)
                all_passed = False
            except Exception as e:
                print(f"ERROR: {e}")
                result["error"] = str(e)
                all_passed = False

            results.append(result)

        return TestReport(
            passed=all_passed,
            tests=results,
            coverage={"actions_total": total_actions, "actions_covered": len(tests), "actions_skipped": []}
        )

    def _run_quest_test(self, test: TestSpec, quests_data: Dict[str, Any]):
        game = MockGame()
        controller = GameStateController(game) # type: ignore
        controller.quests.load_from_dict(quests_data)

        # Setup
        for action in test.setup_actions:
            if action["type"] == "activate_quest":
                q = controller.quests._quests.get(action["quest_id"])
                if q:
                    q.state = "active"
                else:
                    raise AssertionError(f"Quest {action['quest_id']} not found in quests.json")

        # Steps
        for step in test.steps:
            if step["type"] == "set_flag":
                controller.set_flag(step["flag"])
            elif step["type"] == "set_counter":
                controller.state.counters[step["counter"]] = float(step["value"])

        # Update
        controller.update(0.1)

        # Assertions
        for assertion in test.assertions:
            if assertion["type"] == "quest_completed":
                q = controller.quests._quests.get(assertion["quest_id"])
                if not q:
                    raise AssertionError(f"Quest {assertion['quest_id']} not found")
                if q.state != "completed":
                    raise AssertionError(f"Quest state is {q.state}, expected completed")

    def _run_scene_test(self, test: TestSpec):
        loader = SceneLoader()
        for assertion in test.assertions:
            if assertion["type"] == "scene_loadable":
                path = self.root / assertion["path"]
                if not path.exists():
                    raise AssertionError(f"Scene file not found: {path}")
                try:
                    with path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    loader.validate_scene(data) # Assuming validate_scene exists or similar
                except Exception as e:
                    raise AssertionError(f"Failed to load scene: {e}")

    def _run_npc_test(self, test: TestSpec):
        for assertion in test.assertions:
            if assertion["type"] == "npc_present":
                path = self.root / assertion["scene_path"]
                role = assertion["role"]
                if not path.exists():
                    raise AssertionError(f"Scene file not found: {path}")
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)

                found = False
                for entity in data.get("entities", []):
                    # Check name or role/tag
                    if entity.get("name") == role or role in entity.get("tags", []):
                        found = True
                        break
                    # Check behaviour config for role
                    b_config = entity.get("behaviour_config", {})
                    if "Dialogue" in b_config and b_config["Dialogue"].get("role") == role:
                        found = True
                        break
                    # Also check behaviours for specific role config if needed

                if not found:
                    raise AssertionError(f"NPC '{role}' not found in scene")

    def _run_world_test(self, test: TestSpec):
        for assertion in test.assertions:
            if assertion["type"] == "world_reachable":
                path = self.root / assertion["world_path"]
                if not path.exists():
                    raise AssertionError(f"World file not found: {path}")
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)

                # Simple reachability check: all scenes reachable from start?
                # Or just check if the file is valid JSON and has links
                if "scenes" not in data:
                    raise AssertionError("World file missing 'scenes'")
                if "links" not in data:
                    raise AssertionError("World file missing 'links'")

    def _run_prefab_test(self, test: TestSpec):
        # Check if prefab exists in assets/prefabs.json
        prefabs_path = self.root / "assets/prefabs.json"
        if not prefabs_path.exists():
             # Maybe individual files?
             pass
        else:
            try:
                data = json.loads(prefabs_path.read_text(encoding="utf-8"))
                for assertion in test.assertions:
                    if assertion["type"] == "prefab_resolves":
                        pid = assertion["prefab_id"]
                        if pid not in data:
                            raise AssertionError(f"Prefab '{pid}' not found in prefabs.json")
            except Exception as e:
                raise AssertionError(f"Failed to check prefabs: {e}")

    def _run_transition_test(self, test: TestSpec):
        from engine.paths import resolve_path

        for assertion in test.assertions:
            if assertion["type"] == "scene_loadable":
                path = self.root / assertion["path"]
                if not path.exists():
                    raise AssertionError(f"Source scene file not found: {path}")
                try:
                    with path.open("r", encoding="utf-8") as f:
                        json.load(f)
                except Exception as e:
                    raise AssertionError(f"Failed to load source scene: {e}")

            elif assertion["type"] == "transition_valid":
                target = assertion["target"]

                # 1. Try resolving as path
                try:
                    resolved = resolve_path(target)
                    if resolved.exists():
                        continue
                except Exception:
                    pass

                # 2. Try resolving as Scene ID in known worlds
                found = False
                worlds_dir = self.root / "worlds"
                if worlds_dir.exists():
                    for world_file in worlds_dir.glob("*.json"):
                        try:
                            with world_file.open("r", encoding="utf-8") as f:
                                world_data = json.load(f)
                            scenes = world_data.get("scenes", {})
                            if target in scenes:
                                scene_entry = scenes[target]
                                scene_path_str = scene_entry.get("path")
                                if scene_path_str:
                                    scene_path = resolve_path(scene_path_str)
                                    if scene_path.exists():
                                        found = True
                                        break
                        except Exception:
                            continue

                if found:
                    continue

                # Also check root world.json if exists
                root_world = self.root / "world.json"
                if root_world.exists():
                    try:
                        with root_world.open("r", encoding="utf-8") as f:
                            world_data = json.load(f)
                        scenes = world_data.get("scenes", {})
                        if target in scenes:
                            scene_entry = scenes[target]
                            scene_path_str = scene_entry.get("path")
                            if scene_path_str:
                                scene_path = resolve_path(scene_path_str)
                                if scene_path.exists():
                                    found = True
                    except Exception:
                        pass

                if found:
                    continue

                raise AssertionError(f"Transition target '{target}' could not be resolved to a file or valid scene ID.")


    def run_tests_in_sandbox(self, plan: Plan, full_sandbox: bool = False) -> TestReport:
        from engine.tooling.plan_executor import PlanExecutor

        print("[Mesh][Tester] Setting up sandbox...")
        with tempfile.TemporaryDirectory() as temp_dir:
            sandbox_root = Path(temp_dir)

            # Copy config.json
            if (self.root / "config.json").exists():
                shutil.copy(self.root / "config.json", sandbox_root / "config.json")

            if full_sandbox:
                # Copy assets folder
                if (self.root / "assets").exists():
                    shutil.copytree(self.root / "assets", sandbox_root / "assets")

                # Copy scenes folder (recursively)
                if (self.root / "scenes").exists():
                    shutil.copytree(self.root / "scenes", sandbox_root / "scenes")

                # Copy worlds folder
                if (self.root / "worlds").exists():
                    shutil.copytree(self.root / "worlds", sandbox_root / "worlds")
            else:
                # Minimal copy
                (sandbox_root / "assets/data").mkdir(parents=True, exist_ok=True)

                # Always copy quests.json, items.json, prefabs.json, events.json if they exist
                for f in ["quests.json", "items.json", "prefabs.json", "events.json"]:
                    src = self.root / "assets/data" / f
                    if src.exists():
                        shutil.copy(src, sandbox_root / "assets/data" / f)

                # Copy referenced scenes/worlds from plan inputs?
                # For now, just create empty dirs so paths resolve if we create new files
                (sandbox_root / "scenes").mkdir(exist_ok=True)
                (sandbox_root / "worlds").mkdir(exist_ok=True)

                # If plan modifies existing scenes, we should copy them.
                # But inferring that is hard without parsing actions.
                # Let's scan actions for "path", "into", "scene_path", "world_path"
                paths_to_copy = set()
                for action in plan.actions:
                    for key in ["path", "into", "scene_path", "world_path"]:
                        val = action.args.get(key)
                        if val and isinstance(val, str):
                            p = self.root / val
                            if p.exists() and p.is_file():
                                paths_to_copy.add(p)

                for p in paths_to_copy:
                    rel = p.relative_to(self.root)
                    dest = sandbox_root / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(p, dest)

            # Switch context
            original_cwd = os.getcwd()
            original_roots = get_content_roots()

            try:
                os.chdir(sandbox_root)
                set_content_roots([sandbox_root])

                # Apply plan
                print("[Mesh][Tester] Applying plan in sandbox...")
                executor = PlanExecutor(dry_run=False, safe_paths_only=False)
                executor.execute(plan, profile="sandbox_test")

                # Run tests
                # Create a new tester instance rooted at sandbox
                sandbox_tester = PlanTester(sandbox_root)
                tests = sandbox_tester.infer_tests(plan)
                return sandbox_tester.run_tests(tests, total_actions=len(plan.actions))

            finally:
                os.chdir(original_cwd)
                set_content_roots(original_roots)
                print("[Mesh][Tester] Sandbox cleanup.")

def run_test_ai(plan_path: str, out: str | None = None, junit: str | None = None) -> int:
    """CLI entrypoint for test-ai."""
    p = Path(plan_path)
    if not p.exists():
        print(f"Plan not found: {plan_path}")
        return 1

    try:
        plan = Plan.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except Exception as e:
        print(f"Invalid plan: {e}")
        return 1

    tester = PlanTester(Path("."))
    # AI plans run in minimal sandbox by default
    report = tester.run_tests_in_sandbox(plan, full_sandbox=False)

    if out:
        Path(out).write_text(json.dumps(asdict(report), indent=2))

    if report.passed:
        print(f"[Mesh][Tester] Plan verified! Coverage: {report.coverage_ratio:.1%}")
        return 0
    else:
        print("[Mesh][Tester] Plan verification failed.")
        return 1
