import json
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.content_packs import Pack, load_pack, sort_packs, validate_pack_dependencies


class TestContentPacks(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.root = self.test_dir / "packs"
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def create_pack(self, folder_name, manifest_data=None):
        path = self.root / folder_name
        path.mkdir()
        if manifest_data:
            (path / "manifest.json").write_text(json.dumps(manifest_data))
        return path

    def test_load_implicit_pack(self):
        path = self.create_pack("my_mod")
        pack = load_pack(path)
        self.assertEqual(pack.id, "my_mod")
        self.assertTrue(pack.is_implicit)
        self.assertEqual(pack.type, "mod")

    def test_load_explicit_pack(self):
        data = {
            "id": "core_pack",
            "name": "Core",
            "version": "1.0.0",
            "type": "core",
            "requires": [{"id": "other", "min": "1.0"}]
        }
        path = self.create_pack("core", data)
        pack = load_pack(path)
        self.assertEqual(pack.id, "core_pack")
        self.assertFalse(pack.is_implicit)
        self.assertEqual(pack.type, "core")
        self.assertEqual(len(pack.requires), 1)
        self.assertEqual(pack.requires[0].id, "other")

    def test_sort_packs_simple(self):
        # A load_after B -> A overrides B -> A comes before B in list
        pA = Pack(id="A", root=Path("A"), load_after=["B"])
        pB = Pack(id="B", root=Path("B"))

        sorted_packs = sort_packs([pB, pA]) # Input order B, A
        # Expected: A, B
        self.assertEqual([p.id for p in sorted_packs], ["A", "B"])

    def test_sort_packs_cycle(self):
        # A load_after B, B load_after A -> Cycle
        pA = Pack(id="A", root=Path("A"), load_after=["B"])
        pB = Pack(id="B", root=Path("B"), load_after=["A"])

        sorted_packs = sort_packs([pA, pB])
        # Should fallback to input order or handle gracefully
        # Our implementation prints warning and returns input
        self.assertEqual(len(sorted_packs), 2)

    def test_validate_dependencies(self):
        pA = Pack(id="A", root=Path("A"), requires=[])
        pB = Pack(id="B", root=Path("B"), requires=[])
        # B requires A
        pB.requires.append(type("obj", (object,), {"id": "A", "min_version": None, "max_version": None}))

        errors = validate_pack_dependencies([pA, pB])
        self.assertEqual(len(errors), 0)

        # Missing dependency
        pC = Pack(id="C", root=Path("C"))
        pC.requires.append(type("obj", (object,), {"id": "MISSING", "min_version": None, "max_version": None}))

        errors = validate_pack_dependencies([pA, pB, pC])
        self.assertEqual(len(errors), 1)
        self.assertIn("requires missing pack 'MISSING'", errors[0])
