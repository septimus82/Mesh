import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.perks import PerkManager


class TestPerkLoading(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.packs_dir = Path(self.test_dir) / "packs"
        self.packs_dir.mkdir()

        # Create a mock pack with perks
        self.pack_dir = self.packs_dir / "test_pack"
        self.pack_dir.mkdir()
        self.perks_file = self.pack_dir / "perks.json"

        data = {
            "perks": [
                {
                    "id": "test_perk",
                    "name": "Test Perk",
                    "description": "A test perk",
                    "effects": {"max_hp": 10.0}
                }
            ]
        }
        with open(self.perks_file, "w") as f:
            json.dump(data, f)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_load_perks_from_pack(self):
        # Mock resolve_path to return nothing for global perks
        with patch("engine.perks.resolve_path") as mock_resolve:
            mock_resolve.return_value = Path("non_existent")

            import os
            cwd = os.getcwd()
            os.chdir(self.test_dir)
            try:
                print(f"CWD: {os.getcwd()}")
                print(f"Packs dir exists: {Path('packs').exists()}")
                manager = PerkManager()
                manager.load_perks()

                perk = manager.get_perk("test_perk")
                print(f"Perk found: {perk}")
                self.assertIsNotNone(perk)
                self.assertEqual(perk.name, "Test Perk")
                self.assertEqual(perk.effects["max_hp"], 10.0)
            finally:
                os.chdir(cwd)

if __name__ == "__main__":
    unittest.main()
