import argparse
from typing import Any, Dict, List


def get_command_metadata(parser: argparse.ArgumentParser) -> List[Dict[str, Any]]:
    """Extract metadata from an argparse parser."""
    commands = []

    # Access the subparsers action
    subparsers_actions = [
        action for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]

    for subparsers_action in subparsers_actions:
        # Build help map from the parent action's choices
        help_map = {}
        if hasattr(subparsers_action, '_choices_actions'):
            for action in subparsers_action._choices_actions:
                help_map[action.dest] = action.help

        for choice, subparser in subparsers_action.choices.items():
            description = subparser.description
            if not description:
                description = help_map.get(choice, "")

            if not description:
                description = subparser.format_help().split('\n')[0].strip()

            cmd_data = {
                "name": choice,
                "description": description,
                "args": []
            }

            # Extract arguments
            for action in subparser._actions:
                if isinstance(action, argparse._HelpAction):
                    continue

                arg_data = {
                    "name": action.dest,
                    "flags": action.option_strings,
                    "help": action.help,
                    "required": action.required,
                    "default": str(action.default) if action.default is not None else None,
                    "type": str(action.type.__name__) if action.type else "str"
                }

                # Handle boolean flags
                if isinstance(action, argparse._StoreTrueAction) or isinstance(action, argparse._StoreFalseAction):
                    arg_data["type"] = "bool"

                cmd_data["args"].append(arg_data)

            commands.append(cmd_data)

    return sorted(commands, key=lambda x: x["name"])
