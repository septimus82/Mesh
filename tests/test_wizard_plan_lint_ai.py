import argparse
from unittest.mock import patch

from engine.tooling.plan_linter import lint_ai_plan
from engine.tooling.wizard_command import wizard_command


def test_wizard_generated_plans_pass_lint_ai():
    args = argparse.Namespace(
        command="wizard",
        subcommand="new-region",
        name="TestRegion",
        name_prefix="TestRegion",
        pack="test_pack",
        into_world="worlds/test.json",
        world=None,
        link_from=None,
        profile="safe",
        plan=None,
        dry_run=True,
        apply=False,
        with_boss=False,
        with_puzzle=True,
        template=None,
        perks=None,
        theme=None,
        preset=None,
        encounter_set=None,
        difficulty="normal",
        npc_role=None,
        quest_type=None,
        scene=None,
        vars=None,
        run=None,
        list=False,
    )

    with patch("engine.tooling.wizard_command._write_plan") as mock_write, patch("engine.tooling.wizard_command._print_plan") as mock_print:
        mock_write.return_value = None
        wizard_command(args)

        plan = mock_print.call_args[0][0]
        issues = lint_ai_plan(plan)

        assert issues == []
