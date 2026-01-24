import unittest
import json
import tempfile
import shutil
from pathlib import Path
from engine.tooling.plan_tester import PlanTester
from engine.tooling.plan_types import Plan, Action

class TestPlanTestSandboxMinimal(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.test_dir.name)
        self.tester = PlanTester(self.root)
        
        # Setup environment
        (self.root / "config.json").write_text("{}")
        (self.root / "assets/data").mkdir(parents=True)
        (self.root / "assets/data/quests.json").write_text("{}")
        (self.root / "assets/sprites").mkdir(parents=True)
        (self.root / "assets/sprites/huge_file.png").write_text("data")
        (self.root / "scenes").mkdir()
        (self.root / "scenes/referenced.json").write_text("{}")
        (self.root / "scenes/ignored.json").write_text("{}")

    def tearDown(self):
        self.test_dir.cleanup()

    def test_minimal_sandbox_copy(self):
        # Plan references 'scenes/referenced.json'
        plan = Plan(wizard="test", version=1, inputs={}, actions=[
            Action(type="create_scene", args={"path": "scenes/new.json"}, description="New"),
            Action(type="place_npc", args={"into": "scenes/referenced.json", "role": "npc"}, description="Mod")
        ])
        
        # We need to hook into run_tests_in_sandbox to inspect the temp dir
        # But run_tests_in_sandbox uses a context manager for temp dir, so it's gone after return.
        # We can mock shutil.copy/copytree to verify calls.
        
        with unittest.mock.patch('shutil.copy') as mock_copy, \
             unittest.mock.patch('shutil.copytree') as mock_copytree, \
             unittest.mock.patch('engine.tooling.plan_tester.PlanTester.run_tests') as mock_run:
             
            mock_run.return_value = None # Don't care about result
            
            # Mock PlanExecutor to avoid actual execution errors
            with unittest.mock.patch('engine.tooling.plan_executor.PlanExecutor.execute'):
                self.tester.run_tests_in_sandbox(plan, full_sandbox=False)
            
            # Verify copytree was NOT called (minimal mode)
            mock_copytree.assert_not_called()
            
            # Verify essential files copied
            # config.json
            # assets/data/quests.json
            # scenes/referenced.json
            
            copied_sources = [str(call.args[0]) for call in mock_copy.call_args_list]
            
            self.assertTrue(any("config.json" in s for s in copied_sources))
            self.assertTrue(any("quests.json" in s for s in copied_sources))
            self.assertTrue(any("referenced.json" in s for s in copied_sources))
            
            # Verify ignored files NOT copied
            self.assertFalse(any("huge_file.png" in s for s in copied_sources))
            self.assertFalse(any("ignored.json" in s for s in copied_sources))

    def test_full_sandbox_copy(self):
        plan = Plan(wizard="test", version=1, inputs={}, actions=[])
        
        with unittest.mock.patch('shutil.copy') as mock_copy, \
             unittest.mock.patch('shutil.copytree') as mock_copytree, \
             unittest.mock.patch('engine.tooling.plan_tester.PlanTester.run_tests') as mock_run:
             
            mock_run.return_value = None
            
            with unittest.mock.patch('engine.tooling.plan_executor.PlanExecutor.execute'):
                self.tester.run_tests_in_sandbox(plan, full_sandbox=True)
            
            # Verify copytree WAS called for assets, scenes, worlds
            copied_sources = [str(call.args[0]) for call in mock_copytree.call_args_list]
            self.assertTrue(any("assets" in s for s in copied_sources))
            self.assertTrue(any("scenes" in s for s in copied_sources))
