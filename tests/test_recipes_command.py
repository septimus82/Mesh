import unittest

from engine.tooling import recipes_command
from tests.utils.args_factory import make_recipes_args


class TestRecipesCommand(unittest.TestCase):
    def test_recipes_output(self):
        args = make_recipes_args()

        # Capture stdout
        import sys
        from io import StringIO
        captured_output = StringIO()
        sys.stdout = captured_output

        try:
            recipes_command.recipes_command(args)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        self.assertIn("Mesh Workflow Recipes", output)
        self.assertIn("Create New Scene", output)

if __name__ == '__main__':
    unittest.main()
