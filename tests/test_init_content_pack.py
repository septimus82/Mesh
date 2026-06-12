import json
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.tooling import pack_commands
from tests.utils.args_factory import make_init_pack_args


class TestInitContentPack(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/temp_init_pack")
        self.test_dir.mkdir(exist_ok=True)

    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    @patch("engine.tooling.pack_commands.get_content_roots")
    def test_init_pack(self, mock_roots):
        mock_roots.return_value = [self.test_dir]

        args = make_init_pack_args(
            pack_id="test_pack",
            type="mod",
            wip=True
        )

        pack_commands.init_content_pack_command(args)

        pack_dir = self.test_dir / "test_pack"
        self.assertTrue(pack_dir.exists())
        self.assertTrue((pack_dir / "manifest.json").exists())
        self.assertTrue((pack_dir / "scenes").exists())

        manifest = json.loads((pack_dir / "manifest.json").read_text())
        self.assertEqual(manifest["id"], "test_pack")
        self.assertEqual(manifest["type"], "mod")
        self.assertTrue(manifest["wip"])

if __name__ == '__main__':
    unittest.main()
