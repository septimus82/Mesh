import unittest
import tomllib
from pathlib import Path
from engine.version import ENGINE_VERSION

class TestVersionConsistency(unittest.TestCase):
    def test_version_consistency(self):
        """Ensure pyproject.toml version matches engine.version.ENGINE_VERSION."""
        pyproject_path = Path("pyproject.toml")
        self.assertTrue(pyproject_path.exists(), "pyproject.toml not found")
        
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            
        project_version = data["project"]["version"]
        self.assertEqual(project_version, ENGINE_VERSION, 
                         f"Version mismatch: pyproject.toml ({project_version}) != engine/version.py ({ENGINE_VERSION})")
