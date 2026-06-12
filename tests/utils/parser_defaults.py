import argparse
from unittest.mock import patch

from mesh_cli import create_parser


def get_default_args(command_parts: list[str], required_args: list[str] = None) -> argparse.Namespace:
    """
    Get default arguments for a command by parsing a minimal valid command line.
    
    Args:
        command_parts: List of command parts, e.g. ["release-check"] or ["plan", "test"]
        required_args: List of dummy values for required positional arguments.
    """
    parser = create_parser()
    argv = command_parts + (required_args or [])

    # We need to suppress stdout/stderr during parsing to avoid noise
    with patch('sys.stdout'), patch('sys.stderr'):
        try:
            args = parser.parse_args(argv)
            return args
        except SystemExit:
            raise ValueError(f"Could not parse defaults for {command_parts} with required_args={required_args}")
