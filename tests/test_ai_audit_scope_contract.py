from engine.ai_audit import build_audit_report


def test_ai_audit_full_scan_excludes_temp_artifact_and_fixture_trees() -> None:
    report = build_audit_report()

    scene_ids = [scene.scene_id.replace("\\", "/") for scene in report.scenes]
    assert scene_ids
    assert all("/.pytest-debug-temp/" not in scene_id and not scene_id.startswith(".pytest-debug-temp/") for scene_id in scene_ids)
    assert all("/.pytest-gate-deps/" not in scene_id and not scene_id.startswith(".pytest-gate-deps/") for scene_id in scene_ids)
    assert all("/artifacts/" not in scene_id and not scene_id.startswith("artifacts/") for scene_id in scene_ids)
    assert all("/tests/fixtures/" not in scene_id and not scene_id.startswith("tests/fixtures/") for scene_id in scene_ids)
