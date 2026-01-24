import unittest
import json
import os
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock
from engine.tooling.wizard_command import _plan_new_region, WizardContext

class TestMacroRegionWithPuzzle(unittest.TestCase):
    def test_macro_generates_puzzle_action(self):
        # Mock context
        args = SimpleNamespace(
            name_prefix="test_region",
            with_boss=True,
            with_puzzle=True,
            pack=None,
            profile="safe",
            into_world=None,
            template=None,
            perks=None,
            theme=None,
            preset=None,
            encounter_set=None,
            difficulty="normal"
        )
        
        ctx = WizardContext(args)
        ctx.root = Path(".")
        ctx.resolve_path = MagicMock(side_effect=lambda p: Path(p))
        
        _plan_new_region(ctx)
        
        # Check if add_puzzle_switch_door action was added
        actions = [a for a in ctx.plan_actions if a.type == "add_puzzle_switch_door"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].args["id_prefix"], "test_region_dungeon_puzzle")

from unittest.mock import MagicMock
