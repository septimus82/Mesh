import unittest
import json
from pathlib import Path

class TestPresetsNotDuplicated(unittest.TestCase):
    def test_presets_structure(self):
        config_path = Path("config.json")
        if not config_path.exists():
            self.skipTest("config.json not found")
            
        with open(config_path, "r", encoding="utf-8") as f:
            # json.load will overwrite duplicates, so we can't detect them easily with standard json.load
            # But we can check if the resulting dict has the expected keys.
            # To detect duplicates, we can parse it as text or use object_pairs_hook.
            
            def duplicate_check_hook(pairs):
                keys = set()
                result = {}
                for k, v in pairs:
                    if k in keys:
                        # This is a duplicate key in the same object
                        if k == "presets":
                            raise ValueError(f"Duplicate key found: {k}")
                    keys.add(k)
                    result[k] = v
                return result

            f.seek(0)
            try:
                data = json.load(f, object_pairs_hook=duplicate_check_hook)
            except ValueError as e:
                self.fail(str(e))
                
            self.assertIn("presets", data)
            presets = data["presets"]
            self.assertIn("ci-check", presets)
            # Check for other expected presets
            self.assertIn("encounter-ci", presets)

if __name__ == "__main__":
    unittest.main()
