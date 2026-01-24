import argparse
from unittest.mock import MagicMock, patch
from engine.tooling.wizard_command import wizard_command

def test_wizard_adds_autowire_action_in_safe_profile():
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
        with_puzzle=False,
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
        actions = plan.actions
        
        # Check for auto_wire_transitions action
        autowire_actions = [a for a in actions if a.type == "auto_wire_transitions"]
        assert len(autowire_actions) == 1
        assert autowire_actions[0].args["world_path"] == "worlds/test.json"

def test_wizard_skips_autowire_in_fast_profile():
    args = argparse.Namespace(
        command="wizard",
        subcommand="new-region",
        name="TestRegion",
        name_prefix="TestRegion",
        pack="test_pack",
        into_world="worlds/test.json",
        world=None,
        link_from=None,
        profile="fast",
        plan=None,
        dry_run=True,
        apply=False,
        with_boss=False,
        with_puzzle=False,
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
        actions = plan.actions
        
        autowire_actions = [a for a in actions if a.type == "auto_wire_transitions"]
        assert len(autowire_actions) == 0
