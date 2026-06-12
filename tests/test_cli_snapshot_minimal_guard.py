import unittest

from engine.tooling.cli_snapshot_command import extract_parser_info
from mesh_cli import create_parser


class TestCLISnapshotMinimalGuard(unittest.TestCase):
    def test_snapshot_structure(self):
        parser = create_parser()
        snapshot = extract_parser_info(parser)

        # Check top-level commands
        subcommands = snapshot.get("subcommands", {})
        required_commands = [
            "check", "docs", "wizard", "doctor", "dist",
            "release-check", "plan"
        ]

        for cmd in required_commands:
            self.assertIn(cmd, subcommands, f"Command '{cmd}' missing from CLI snapshot")

        # Check cli-smoke
        self.assertIn("cli-smoke", subcommands, "Command 'cli-smoke' missing from CLI snapshot")

        # Check plan subcommands
        plan_cmds = subcommands["plan"].get("subcommands", {})
        self.assertIn("lint", plan_cmds)
        self.assertIn("diff", plan_cmds)
        self.assertIn("test", plan_cmds)

if __name__ == "__main__":
    unittest.main()
