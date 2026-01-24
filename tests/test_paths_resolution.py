import unittest
import tempfile
import shutil
from pathlib import Path
from engine.paths import resolve_path, set_content_roots, get_content_roots

class TestPathsResolution(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.base_root = self.test_dir / "base"
        self.mod_root = self.test_dir / "mod"
        
        self.base_root.mkdir()
        self.mod_root.mkdir()
        
        # Create dummy files
        (self.base_root / "common.txt").write_text("base version")
        (self.base_root / "base_only.txt").write_text("base only")
        (self.mod_root / "common.txt").write_text("mod version")
        (self.mod_root / "mod_only.txt").write_text("mod only")
        
        # Save original roots
        self.original_roots = get_content_roots()

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        set_content_roots(self.original_roots)

    def test_resolve_priority(self):
        # Set roots: mod first, then base
        set_content_roots([self.mod_root, self.base_root])
        
        # Should find mod version of common file
        path = resolve_path("common.txt")
        self.assertEqual(path.read_text(), "mod version")
        
        # Should find base only file
        path = resolve_path("base_only.txt")
        self.assertEqual(path.read_text(), "base only")
        
        # Should find mod only file
        path = resolve_path("mod_only.txt")
        self.assertEqual(path.read_text(), "mod only")

    def test_resolve_fallback(self):
        # Set roots: base only
        set_content_roots([self.base_root])
        
        path = resolve_path("common.txt")
        self.assertEqual(path.read_text(), "base version")

    def test_resolve_nonexistent(self):
        set_content_roots([self.base_root])
        # Should return the path relative to the first root if not found anywhere
        path = resolve_path("does_not_exist.txt")
        self.assertEqual(path, self.base_root / "does_not_exist.txt")
        self.assertFalse(path.exists())
