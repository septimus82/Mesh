import unittest
import tempfile
import shutil
from pathlib import Path
from engine.content_index import ContentIndex
from engine.paths import set_content_roots, get_content_roots

class TestContentIndex(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.root1 = self.test_dir / "root1"
        self.root2 = self.test_dir / "root2"
        self.root1.mkdir()
        self.root2.mkdir()
        
        # Create files
        (self.root1 / "unique1.txt").write_text("1")
        (self.root2 / "unique2.txt").write_text("2")
        (self.root1 / "common.txt").write_text("1")
        (self.root2 / "common.txt").write_text("2")
        
        self.original_roots = get_content_roots()

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        set_content_roots(self.original_roots)

    def test_index_build(self):
        # Root1 is higher priority
        roots = [self.root1, self.root2]
        index = ContentIndex(roots)
        index.build()
        
        # Check unique1
        entry = index.get_entry("unique1.txt")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.providing_root, self.root1)
        
        # Check unique2
        entry = index.get_entry("unique2.txt")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.providing_root, self.root2)
        
        # Check common (override)
        entry = index.get_entry("common.txt")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.providing_root, self.root1)
        self.assertIn(self.root2, entry.shadowed_roots)

    def test_resolve_via_index(self):
        roots = [self.root1, self.root2]
        index = ContentIndex(roots)
        
        path = index.resolve("common.txt")
        self.assertEqual(path, self.root1 / "common.txt")
        
        path = index.resolve("unique2.txt")
        self.assertEqual(path, self.root2 / "unique2.txt")
        
        path = index.resolve("missing.txt")
        self.assertIsNone(path)
