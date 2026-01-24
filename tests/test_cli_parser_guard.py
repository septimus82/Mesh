import unittest
import argparse
from mesh_cli import create_parser

class TestCLIParserGuard(unittest.TestCase):
    def setUp(self):
        self.parser = create_parser()
        # Extract subcommands
        self.subparsers_action = None
        for action in self.parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                self.subparsers_action = action
                break
        self.subcommands = self.subparsers_action.choices if self.subparsers_action else {}

    def test_core_subcommands_exist(self):
        """Ensure core subcommands are present."""
        core_commands = [
            "check",
            "docs",
            "wizard",
            "doctor",
            "dist",
            "plan",
        ]
        for cmd in core_commands:
            self.assertIn(cmd, self.subcommands, f"Missing core subcommand: {cmd}")

    def test_doctor_flags(self):
        """Ensure doctor command has --json flag."""
        doctor_parser = self.subcommands["doctor"]
        actions = {a.dest: a for a in doctor_parser._actions}
        self.assertIn("json", actions, "doctor command missing --json flag")

    def test_check_flags(self):
        """Ensure check command has --full flag."""
        check_parser = self.subcommands["check"]
        actions = {a.dest: a for a in check_parser._actions}
        self.assertIn("full", actions, "check command missing --full flag")

    def test_wizard_flags(self):
        """Ensure wizard command has key flags."""
        wizard_parser = self.subcommands["wizard"]
        actions = {a.dest: a for a in wizard_parser._actions}
        self.assertIn("apply", actions, "wizard command missing --apply flag")
        self.assertIn("plan", actions, "wizard command missing --plan flag")
        self.assertIn("profile", actions, "wizard command missing --profile flag")

    def test_docs_flags(self):
        """Ensure docs command has --verify flag."""
        docs_parser = self.subcommands["docs"]
        actions = {a.dest: a for a in docs_parser._actions}
        self.assertIn("verify", actions, "docs command missing --verify flag")

if __name__ == "__main__":
    unittest.main()
