import tomllib
import unittest
from pathlib import Path

from engine import __version__ as ENGINE_INIT_VERSION
from engine.tooling.project_index import build_project_index
from engine.version import ENGINE_VERSION
from mesh_cli.version_info import get_tool_version


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

    def test_single_version_source_is_shared_across_engine_and_cli(self):
        tool_version = get_tool_version()
        self.assertEqual(ENGINE_VERSION, ENGINE_INIT_VERSION)
        self.assertEqual(ENGINE_VERSION, tool_version)

    def test_project_index_reports_canonical_version(self):
        index = build_project_index(scenes_root="does_not_exist")
        self.assertEqual(index["engine"]["version"], get_tool_version())
