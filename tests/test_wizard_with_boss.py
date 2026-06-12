import unittest

from engine.tooling.wizard_command import WizardContext, _plan_new_region


class TestWizardWithBoss(unittest.TestCase):
    def test_new_region_with_boss(self):
        """Test that new-region --with-boss generates a boss entity."""
        args = type("Args", (), {
            "subcommand": "new-region",
            "name_prefix": "test_region",
            "pack": "test_pack",
            "into_world": None,
            "profile": "safe",
            "with_boss": True,
            "with_puzzle": False,
            "scene": None,
            "npc_role": "quest_giver",
            "quest_type": "fetch",
            "template": None,
            "perks": None,
            "theme": None,
            "preset": None,
            "encounter_set": None,
            "difficulty": "normal"
        })()

        ctx = WizardContext(args)
        _plan_new_region(ctx)

        # Find create_scene action for dungeon
        dungeon_action = None
        for action in ctx.plan_actions:
            if action.type == "create_scene" and action.args.get("template") == "dungeon":
                dungeon_action = action
                break

        self.assertIsNotNone(dungeon_action, "Dungeon scene creation action not found")
        self.assertTrue(dungeon_action.args.get("with_boss"), "with_boss arg missing in action")
        self.assertEqual(dungeon_action.args.get("region_prefix"), "test_region")

if __name__ == "__main__":
    unittest.main()
