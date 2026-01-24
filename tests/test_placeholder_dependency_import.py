import unittest
import sys
from unittest.mock import MagicMock

class TestPlaceholderDependencyImport(unittest.TestCase):
    def test_pillow_import(self):
        """Ensure Pillow (PIL) is importable, required for create_placeholder.py."""
        try:
            import PIL
            from PIL import Image, ImageDraw
        except ImportError:
            self.fail("Pillow is not installed or cannot be imported.")

    def test_create_placeholder_import(self):
        """Ensure create_placeholder.py can be imported (dependencies met)."""
        # Mock argparse to prevent script execution if it runs on import (it shouldn't, but safety first)
        with unittest.mock.patch('argparse.ArgumentParser.parse_args', return_value=MagicMock()):
             try:
                 from tooling import create_placeholder
             except ImportError as e:
                 self.fail(f"Failed to import create_placeholder: {e}")
