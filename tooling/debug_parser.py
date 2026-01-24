import argparse

import mesh_cli_v2

print("Imported mesh_cli_v2")
parser = mesh_cli_v2.create_parser()
print("Created parser")

# Navigate to wizard parser
# The main parser has subparsers action at index 0 (help) or 1 (subparsers)
subparsers_action = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)][0]
wizard_parser = subparsers_action.choices['wizard']

# The wizard parser has 'subcommand' argument
subcommand_action = [a for a in wizard_parser._actions if a.dest == 'subcommand'][0]
print(f"Choices: {subcommand_action.choices}")
