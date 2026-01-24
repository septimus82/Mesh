import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from engine.prefabs import PrefabManager
from engine.content_packs import Pack

class TestVariantPackResolution(unittest.TestCase):
    def test_variant_override_order(self):
        """Ensure variants from higher priority packs override lower ones."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            # Create Pack A (Base)
            pack_a = root / "packs" / "pack_a"
            pack_a.mkdir(parents=True)
            (pack_a / "data").mkdir()
            
            variants_a = [
                {"id": "v1", "base": "p1", "overrides": {"hp": 10}},
                {"id": "v2", "base": "p1", "overrides": {"hp": 20}}
            ]
            (pack_a / "data" / "variant_patches.json").write_text(json.dumps(variants_a))
            
            # Create Pack B (Override)
            pack_b = root / "packs" / "pack_b"
            pack_b.mkdir(parents=True)
            (pack_b / "data").mkdir()
            
            # Pack B overrides v1, but leaves v2 alone
            variants_b = [
                {"id": "v1", "base": "p1", "overrides": {"hp": 99}}
            ]
            (pack_b / "data" / "variant_patches.json").write_text(json.dumps(variants_b))
            
            # Mock get_content_roots to return our temp root
            with patch("engine.prefabs.get_content_roots", return_value=[root]):
                # Mock discover_packs to return packs in correct order (A then B)
                # Assuming sort_packs works correctly, or we mock it.
                # Let's mock discover_packs to ensure we test the PrefabManager logic, not the discovery logic.
                
                # Pack objects
                p_a = Pack(id="pack_a", root=pack_a)
                p_b = Pack(id="pack_b", root=pack_b)
                
                # If B loads after A, list should be [A, B]
                with patch("engine.prefabs.discover_packs", return_value=[p_a, p_b]):
                    manager = PrefabManager()
                    manager.load()
                    
                    # Check v1 (should be from B)
                    v1 = manager._variants.get("v1")
                    self.assertIsNotNone(v1)
                    self.assertEqual(v1["overrides"]["hp"], 99)
                    
                    # Check v2 (should be from A)
                    v2 = manager._variants.get("v2")
                    self.assertIsNotNone(v2)
                    self.assertEqual(v2["overrides"]["hp"], 20)

    def test_variant_discovery_integration(self):
        """Test that discover_packs actually finds the packs."""
        from engine.content_packs import discover_packs
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "packs" / "pack_x").mkdir(parents=True)
            
            packs = discover_packs([root])
            pack_ids = [p.id for p in packs]
            
            self.assertIn("pack_x", pack_ids)
            # The root itself might be a pack (implicit)
            self.assertIn(root.name, pack_ids)
