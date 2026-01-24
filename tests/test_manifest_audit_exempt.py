import unittest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from engine.content_packs import load_pack, Pack
from engine.content_audit import ContentAuditor

class TestManifestAuditExempt(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/temp_manifest_exempt")
        self.test_dir.mkdir(exist_ok=True)
        
    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_load_pack_exempt(self):
        manifest = {
            "id": "test_pack",
            "audit_exempt": True,
            "wip": True,
            "audit_policy_override": {"max_unused_assets": 100}
        }
        
        pack_dir = self.test_dir / "test_pack"
        pack_dir.mkdir()
        (pack_dir / "manifest.json").write_text(json.dumps(manifest))
        
        pack = load_pack(pack_dir)
        
        self.assertTrue(pack.audit_exempt)
        self.assertTrue(pack.wip)
        self.assertEqual(pack.audit_policy_override["max_unused_assets"], 100)

    @patch("engine.content_audit.get_content_index")
    def test_auditor_auto_exempt(self, mock_get_index):
        # Setup mocks
        mock_index = MagicMock()
        mock_get_index.return_value = mock_index
        
        pack1 = Pack(id="pack1", root=Path("."), audit_exempt=True)
        pack2 = Pack(id="pack2", root=Path("."), audit_exempt=False)
        
        mock_index.packs = [pack1, pack2]
        mock_index.entries = {}
        
        auditor = ContentAuditor("worlds/main.json")
        
        # Mock internal methods to avoid real scanning
        auditor._scan_index = MagicMock()
        auditor._scan_definitions = MagicMock()
        auditor._scan_world = MagicMock()
        auditor._build_report = MagicMock()
        
        auditor.audit()
        
        # Verify _build_report was called with allow_packs containing pack1
        call_args = auditor._build_report.call_args
        allow_packs = call_args[0][1] # 2nd arg
        
        self.assertIn("pack1", allow_packs)
        self.assertNotIn("pack2", allow_packs)

if __name__ == '__main__':
    unittest.main()
