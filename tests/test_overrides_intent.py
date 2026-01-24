import unittest
import tempfile
import shutil
from pathlib import Path
from engine.content_index import ContentIndex
from engine.paths import set_content_roots, get_content_roots

class TestOverridesIntent(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.root_core = self.test_dir / "core"
        self.root_mod = self.test_dir / "mod"
        self.root_core.mkdir()
        self.root_mod.mkdir()
        
        # Create core pack
        (self.root_core / "manifest.json").write_text('{"id": "core", "type": "core"}')
        (self.root_core / "texture.png").write_text("core")
        
        # Create mod pack
        (self.root_mod / "manifest.json").write_text('{"id": "mod", "type": "mod", "load_after": ["core"], "overrides": ["*.png"]}')
        (self.root_mod / "texture.png").write_text("mod")
        
        self.original_roots = get_content_roots()

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        set_content_roots(self.original_roots)

    def test_override_detection(self):
        # Mod overrides Core
        # Mod declares override "*.png"
        
        roots = [self.root_mod, self.root_core] # Config order
        # But sort_packs will ensure Mod comes before Core because of load_after
        
        index = ContentIndex(roots)
        index.build()
        
        entry = index.get_entry("texture.png")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.providing_pack_id, "mod")
        self.assertIn("core", entry.shadowed_pack_ids)
        
        # Check intent logic (simulated)
        import fnmatch
        mod_pack = [p for p in index.packs if p.id == "mod"][0]
        declared = False
        for pattern in mod_pack.overrides:
            if fnmatch.fnmatch(entry.key, pattern):
                declared = True
                break
        self.assertTrue(declared)

    def test_undeclared_override(self):
        # Mod overrides Core but NO declaration
        (self.root_mod / "manifest.json").write_text('{"id": "mod", "type": "mod", "load_after": ["core"], "overrides": []}')
        
        roots = [self.root_mod, self.root_core]
        index = ContentIndex(roots)
        index.build()
        
        entry = index.get_entry("texture.png")
        
        mod_pack = [p for p in index.packs if p.id == "mod"][0]
        declared = False
        for pattern in mod_pack.overrides:
            if fnmatch.fnmatch(entry.key, pattern):
                declared = True
                break
        self.assertFalse(declared)
