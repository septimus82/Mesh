import argparse
import unittest
from unittest.mock import patch

from engine.tooling import wizard_command


class TestWizardPresetExpansion(unittest.TestCase):
    @patch("engine.tooling.wizard_command._load_config")
    def test_expand_preset(self, mock_load_config):
        mock_load_config.return_value = {
            "wizard_presets": {
                "mossy_ruins": {
                    "template": "ruins",
                    "theme": "moss",
                    "with_boss": True
                }
            }
        }

        args = argparse.Namespace(
            preset="mossy_ruins",
            template=None,
            theme=None,
            with_boss=False,
            with_puzzle=False,
            subcommand="new-region", # To avoid crash if it tries to run
            pack=None,
            name_prefix="test",
            dry_run=True, # Don't execute
            plan=None,
            apply=False,
            scene=None,
            into_world=None,
            link_from=None,
            profile="safe",
            npc_role=None,
            quest_type=None,
            vars=None,
            run=None,
            list=False
        )

        # We can call _expand_preset directly if we import it, or verify via wizard_command side effects
        # But wizard_command runs the whole thing.
        # Let's access the private function for unit testing.
        wizard_command._expand_preset(args)

        self.assertEqual(args.template, "ruins")
        self.assertEqual(args.theme, "moss")
        self.assertTrue(args.with_boss)

    @patch("engine.tooling.wizard_command._load_config")
    def test_preset_override(self, mock_load_config):
        mock_load_config.return_value = {
            "wizard_presets": {
                "mossy_ruins": {
                    "template": "ruins",
                    "theme": "moss"
                }
            }
        }

        args = argparse.Namespace(
            preset="mossy_ruins",
            template="deep-dungeon", # Override
            theme=None,
            with_boss=False,
            with_puzzle=False
        )

        wizard_command._expand_preset(args)

        self.assertEqual(args.template, "deep-dungeon") # Should keep override
        self.assertEqual(args.theme, "moss")

if __name__ == "__main__":
    unittest.main()
