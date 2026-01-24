import unittest
from pathlib import Path

class TestCodeHygiene(unittest.TestCase):
    def test_no_silent_swallows_in_hotspots(self):
        """Ensure critical files do not contain silent 'except Exception' blocks."""
        
        critical_files = [
            "engine/scene_controller.py",
            "engine/content_audit.py",
            "engine/camera_controller.py",
            "engine/ui.py",
            "engine/input_controller.py",
        ]
        
        root = Path(__file__).parent.parent
        
        for rel_path in critical_files:
            path = root / rel_path
            if not path.exists():
                continue
                
            content = path.read_text(encoding="utf-8")
            
            # Check for 'except Exception: pass'
            self.assertNotIn("except Exception: pass", content, f"Found silent pass in {rel_path}")
            
            # Check for 'except Exception: return' (without logging)
            # This is harder to regex perfectly, but we can check for the literal string pattern
            # assuming standard formatting.
            # We'll just check for the most egregious 'pass' case for now as a sanity check.
            
            # Also check that we are importing logging
            self.assertIn("import logging", content, f"{rel_path} should import logging")
            self.assertIn("logger = logging.getLogger", content, f"{rel_path} should define a logger")

if __name__ == "__main__":
    unittest.main()
