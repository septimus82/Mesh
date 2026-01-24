import unittest
import ast
import glob
import os

class TestNoMagicMockArgs(unittest.TestCase):
    def test_no_magicmock_args_in_tests(self):
        """Ensure tests do not use MagicMock() for 'args' variable."""
        test_files = glob.glob("tests/test_*.py")
        violations = []
        
        for file_path in test_files:
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    tree = ast.parse(f.read(), filename=file_path)
                except SyntaxError:
                    continue
                    
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id == "args":
                                # Check if value is MagicMock() call
                                if isinstance(node.value, ast.Call):
                                    func = node.value.func
                                    if isinstance(func, ast.Name) and func.id == "MagicMock":
                                        violations.append(f"{file_path}:{node.lineno}")
                                    elif isinstance(func, ast.Attribute) and func.attr == "MagicMock":
                                        violations.append(f"{file_path}:{node.lineno}")
                                        
        if violations:
            self.fail(f"Found MagicMock() assigned to 'args' in tests. Use ArgsFactory instead:\n" + "\n".join(violations))
